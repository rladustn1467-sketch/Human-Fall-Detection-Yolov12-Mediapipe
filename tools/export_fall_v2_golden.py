"""Export golden cases for the Java port of fall rule v2 (V2Features + FallRuleV2, mobile/.../detect/).

From the Android-style pose logs (tools/urfall_record_android.py, tools/caucafall_record.py) it writes, per
sequence: the frame times, PoseBridge boxes and landmarks (x, y, visibility rounded to 6 decimals), and what the
Python code gives for exactly those rounded inputs: the main person's A1, H3, B1, C1 per frame
(tools/urfall_features.py, timing="time" like the app) and the alarm time of fall_logic.v2.FallRuleV2.
Besides the full logs there are cases with frames left out (tools/v2_uneven_frames.py patterns), as when a phone
camera drops frames. The JVM test replays them.

  python tools/export_fall_v2_golden.py --small mobile/android/app/src/test/resources/fall_rule_v2_golden.json
      a few sequences chosen to cover the rule's paths (kept in git for the unit test)
  python tools/export_fall_v2_golden.py --all eval_output/fall_rule_v2_golden_all.json
      every recorded sequence of both datasets, full and with uneven frames (not in git; the JVM test reads it
      when FALL_V2_GOLDEN_ALL is set)
"""
import argparse
import json
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fall_logic.v2 import FallRuleV2, Params  # noqa: E402
from tools import pose_log  # noqa: E402
from tools.urfall_features import sequence_rows  # noqa: E402
from tools.v2_uneven_frames import SEED, every_other_jitter, random_40, stalls  # noqa: E402

LOGS = {"urfall": os.path.join(ROOT, "eval_output", "urfall_android"),
        "caucafall": os.path.join(ROOT, "eval_output", "caucafall", "android")}
# 규칙의 여러 경로: (A)로 잡힘, (B)로 잡힘, 놓침, 침대 눕기 오탐, 사람 2명, 사람이 안 보임, 천장 카메라
SMALL = ("fall-02", "fall-13", "adl-10", "adl-04", "fall-cfS03-forward", "fall-cfS04-sitting",
         "adl-cfS10-kneel", "fall-cfS08-forward")
# 프레임을 뺀 경우: (영상, 버리는 방식)
SMALL_UNEVEN = (("fall-02", every_other_jitter), ("fall-cfS03-forward", stalls), ("adl-10", random_40))
FEATS = ("A1_body_angle_shoulder", "H3_head_above_ankle", "B1_box_ratio", "C1_descent_025")


def case(name, header, frames, label=None):
    fps = header.get("fps") or 30
    rounded, out_frames = [], []
    for r in frames:
        lms = [None if not lm else [[round(p[0], 6), round(p[1], 6), 0.0, round(p[3], 6)] for p in lm] for lm in r["landmarks"]]
        rounded.append({"index": r["index"], "now": r["now"], "boxes": r["boxes"], "landmarks": lms})
        out_frames.append({"t": r["now"], "boxes": r["boxes"],
                           "lms": [None if lm is None else [[p[0], p[1], p[3]] for p in lm] for lm in lms]})
    rows = sequence_rows("android", name, rounded, {}, fps=fps, timing="time")
    by_frame = {}
    for row in rows:
        if row["person"] == "" or row["main"] == 1:
            by_frame[row["frame"]] = [None if row[f] == "" else row[f] for f in FEATS]
    expected = [by_frame[r["index"] + 1] for r in rounded]
    rule = FallRuleV2(Params())
    for r, e in zip(rounded, expected):
        rule.update(r["now"], *e)
    return {"name": label or name, "fps": fps, "frames": out_frames, "expected": expected, "alarm": rule.alarm}


def main():
    parser = argparse.ArgumentParser(description="Golden cases for the Java fall rule v2")
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--small", metavar="OUT")
    g.add_argument("--all", metavar="OUT")
    args = parser.parse_args()
    out = args.small or args.all
    names = []
    for src, d in LOGS.items():
        for n in sorted(os.listdir(d)):
            if n.endswith(".jsonl") and (args.all or n[:-6] in SMALL):
                names.append((n[:-6], os.path.join(d, n)))
    cases = []
    for name, path in names:
        header, frames = pose_log.read_log(path)
        cases.append(case(name, header, frames))
        patterns = [p for n, p in SMALL_UNEVEN if n == name] if args.small else [every_other_jitter]
        for pattern in patterns:
            kept = pattern(frames, random.Random(SEED))
            cases.append(case(name, header, kept, f"{name} ({pattern.__name__})"))
    with open(out, "w", encoding="utf-8") as fp:
        json.dump({"params": vars(Params()) if hasattr(Params(), "__dict__") else str(Params()), "cases": cases}, fp,
                  separators=(",", ":"))
    alarms = sum(1 for c in cases if c["alarm"] is not None)
    print(f"{len(cases)}개 영상, {sum(len(c['frames']) for c in cases)}프레임, 알림 {alarms}개 → {out} ({os.path.getsize(out) // 1024}KB)")


if __name__ == "__main__":
    main()
