"""Fall rule v2: a time rule over per-frame posture features, frame by frame (streaming).

Found on the tune sequences of UR Fall and CAUCAFall (tools/rule_search.py, docs/fall_rule_v2.md); the legacy
single-frame rule (fall_logic/legacy.py) stays unchanged next to it.

Input per frame (the main person's features in frame pixels, from tools/urfall_features.py; None = not available):
  a1  body line angle against the horizontal (0 = lying flat, 90 = upright)        A1_body_angle_shoulder
  h3  how far the head is above the ankles, in torso lengths                       H3_head_above_ankle
  b1  person box width / height                                                    B1_box_ratio
  c1  downward hip speed over 0.25 s, torso lengths per second                     C1_descent_025
Rule:
  low  = a1 < low_angle or h3 < low_head
  wide = low or b1 > wide_box
  (A) fast drop:   the speed smoothed over 3 consecutive values (median) is >= drop_speed, and within drop_window
                   seconds after that frame at least drop_frames frames are wide (drop_after = "wide") or low
  (B) stays down:  wide frames for stay_seconds in a row; up to gap_seconds without any value (person not found)
                   do not break the run, a frame with values that is not wide does
  fall = (A) or (B)
The smoothing needs the next value, so the speed of a frame is judged one frame later (one frame of delay).
Pure Python, no other packages, so it can be ported to the Android app like LegacyFallLogic.
"""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Params:
    low_angle: float = 40.0       # 도
    low_head: float = 0.3         # 몸통 길이
    wide_box: float = 1.5         # 상자 가로/세로
    drop_speed: float = 2.0       # 몸통 길이/초 (math.inf = (A) 끔)
    drop_after: str = "wide"      # "wide" 또는 "low"
    drop_frames: int = 3
    drop_window: float = 1.0      # 초
    stay_seconds: float = 1.0     # 초 (math.inf = (B) 끔)
    gap_seconds: float = 1.0      # 초


def _median3(a, b, c):
    vals = sorted(x for x in (a, b, c) if x is not None)
    if not vals:
        return None
    n = len(vals)
    return vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2


class FallRuleV2:
    """Feed frames in time order with update(); it returns the alarm time (seconds) once, or None."""

    def __init__(self, params=Params()):
        self.p = params
        self.alarm = None
        self._c = []                 # 최근 3개 속도 (평활용)
        self._t = []
        self._pending = []           # (A): [(시작 시각, 넓게 본 낮은 자세 프레임 수)]
        self._run_start = None       # (B)
        self._run_last = None

    def _is_low(self, a1, h3):
        return (a1 is not None and a1 < self.p.low_angle) or (h3 is not None and h3 < self.p.low_head)

    def update(self, t, a1=None, h3=None, b1=None, c1=None):
        """One frame. Returns the alarm time when the rule fires on this frame (only the first time), else None."""
        p = self.p
        low = self._is_low(a1, h3)
        wide = low or (b1 is not None and b1 > p.wide_box)
        has_value = a1 is not None or h3 is not None or b1 is not None
        fired = []

        # (A) 이번 프레임이 지난 하락 후보들의 확인 프레임이 되는지
        check = wide if p.drop_after == "wide" else low
        still = []
        for start, n in self._pending:
            if t - start > p.drop_window:
                continue
            if check:
                n += 1
                if n >= p.drop_frames:
                    fired.append(t)
                    continue
            still.append((start, n))
        self._pending = still
        # 한 프레임 늦게: 직전 프레임의 평활 속도 (직전·전전·지금 값의 중앙값)
        self._c.append(c1)
        self._t.append(t)
        if len(self._c) >= 2:
            prev = self._c[-2]
            if prev is not None and p.drop_speed != math.inf:
                before = self._c[-3] if len(self._c) >= 3 else None
                s = _median3(before, prev, c1)
                if s is not None and s >= p.drop_speed:
                    start = self._t[-2]
                    n = 1 if check and t - start <= p.drop_window else 0   # 지금 프레임은 그 뒤 첫 프레임
                    if n >= p.drop_frames:
                        fired.append(t)
                    else:
                        self._pending.append((start, n))
        self._c = self._c[-3:]
        self._t = self._t[-3:]

        # (B) 넓게 본 낮은 자세 유지
        if wide:
            if self._run_start is None or t - self._run_last > p.gap_seconds:
                self._run_start = t
            self._run_last = t
            if p.stay_seconds != math.inf and self._run_last - self._run_start >= p.stay_seconds:
                fired.append(t)
        elif has_value:
            self._run_start = None

        if fired and self.alarm is None:
            self.alarm = min(fired)
            return self.alarm
        return None
