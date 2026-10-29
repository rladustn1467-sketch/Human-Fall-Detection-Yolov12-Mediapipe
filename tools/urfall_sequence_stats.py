"""Stage 4-3: one row of representative values per tune sequence (a fall rule works over time, not per frame).

From features_<pipeline>.csv (main person of tune sequences only, see split.csv):
  c1_max, c2_max        fastest downward hip speed (torso lengths/s) over 0.25 s / 0.5 s
  low_any               any frame in a low posture (A1 < LOW_ANGLE degrees)
  low_run_s             longest time in a low posture; frames without a person (or without A1) for at most
                        GAP_S seconds in between do not break the run (lying people are often not found)
  descent_s             shortest time from a frame with an up posture (H3 >= UP_H3: standing or sitting) to a
                        later low-posture frame: how fast the person got from up to down
  down_speed_c1         the largest C1 in the DESCENT_LOOKBACK_S seconds before that first low frame
The groups: fall_stand / fall_chair (odd / even fall-XX), adl_normal, adl_lying_bed (adl-10, 11, 21, 22 on a bed
or sofa), adl_lying_floor (adl-32..35, getting down on the floor on purpose), from split.csv and adl_tags.csv.
The cut-offs here (30 deg, 1.5, 1 s) only describe the data; they are not the rule's thresholds.

Usage: venv\\Scripts\\python.exe tools\\urfall_sequence_stats.py --pipeline android
Output: eval_output/urfall_features/seqstats_<pipeline>.md and .csv
"""
import argparse
import csv
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tools.urfall_features import OUT_DIR as URFALL_DIR  # noqa: E402
from tools.urfall_distributions import load_tags  # noqa: E402

BASE = {"urfall": URFALL_DIR, "caucafall": os.path.join(ROOT, "eval_output", "caucafall")}
LOW_ANGLE = 30.0          # 몸 선이 이보다 눕혀지면 '낮은 자세' (설명용 기준)
UP_H3 = 1.5               # 머리가 발목보다 몸통 1.5배 이상 위 = 서 있거나 앉아 있음 (설명용 기준)
GAP_S = 1.0               # 이 시간 이하로 사람이 안 보여도 낮은 자세가 이어진 것으로 봄
DESCENT_LOOKBACK_S = 2.0
FLOOR_ADL_ACTIONS = ("lie_floor", "lie_down_floor")
BED_ADL_ACTIONS = ("lie_bed", "lie_down")
LOW_H3 = 0.5              # 머리가 발목 높이 근처 (넓게 본 낮은 자세)
LOW_B1 = 1.0              # 사람 상자가 세로보다 가로가 김 (넓게 본 낮은 자세)
SETTLE_S = (1.0, 3.0)     # 처음 낮은 자세가 된 뒤 이 구간(초)의 움직임 = '넘어진 뒤 멈췄나'
COLUMNS = ("sequence", "group", "frames", "person_share", "c1_max", "c2_max", "low_any", "low_run_s",
           "low_run_wide_s", "descent_s", "down_speed_c1", "motion_after")


def num(v):
    return None if v in ("", None) else float(v)


def adl_group(seq, tags):
    actions = {a for _, _, a in tags.get(seq, [])}
    if actions & set(FLOOR_ADL_ACTIONS):
        return "adl_lying_floor"
    if actions & set(BED_ADL_ACTIONS):
        return "adl_lying_bed"
    return "adl_normal"


def longest_run(times, low, has_value):
    """Longest time (s) of consecutive low frames; a gap of at most GAP_S without a value does not break it."""
    dt = statistics.median(b - a for a, b in zip(times, times[1:])) if len(times) > 1 else 0.0
    best, start, last_low = 0.0, None, None
    for t, is_low, v in zip(times, low, has_value):
        if is_low:
            if start is None or t - last_low > GAP_S:
                start = t
            last_low = t
            best = max(best, last_low - start + dt)
        elif v and start is not None:
            start = None                                    # 값이 있는데 낮지 않음 = 끊김
    return best


def sequence_values(frames):
    """frames: [(time_s, a1, h3, c1, c2, b1, e4)] for every frame of one sequence in order (None = no value)."""
    times = [f[0] for f in frames]
    low = [f[1] is not None and f[1] < LOW_ANGLE for f in frames]
    # 넓게 본 낮은 자세: 각도, 머리 높이, 상자 비율 중 하나라도 (천장 카메라에서 각도가 놓치는 경우)
    wide = [lo or (f[2] is not None and f[2] < LOW_H3) or (f[5] is not None and f[5] > LOW_B1) for lo, f in zip(low, frames)]
    up = [f[2] is not None and f[2] >= UP_H3 for f in frames]
    out = {"person_share": sum(1 for f in frames if f[1] is not None or f[2] is not None) / max(len(frames), 1),
           "c1_max": max((f[3] for f in frames if f[3] is not None), default=None),
           "c2_max": max((f[4] for f in frames if f[4] is not None), default=None),
           "low_any": any(low)}
    # 낮은 자세가 이어진 가장 긴 시간 (값이 없는 짧은 틈은 이어진 것으로)
    out["low_run_s"] = longest_run(times, low, [f[1] is not None for f in frames])
    out["low_run_wide_s"] = longest_run(times, wide, [f[1] is not None or f[2] is not None or f[5] is not None for f in frames])
    first_wide = next((t for t, w in zip(times, wide) if w), None)
    after = [f[6] for f in frames if f[6] is not None and first_wide is not None
             and first_wide + SETTLE_S[0] <= f[0] <= first_wide + SETTLE_S[1]]
    out["motion_after"] = statistics.median(after) if after else None
    # 서 있거나 앉은 자세 → 낮은 자세까지 가장 짧은 시간
    last_up, descent, first_low_t = None, None, None
    for t, is_up, is_low in zip(times, up, low):
        if is_up:
            last_up = t
        if is_low and last_up is not None:
            d = t - last_up
            if descent is None or d < descent:
                descent, first_low_t = d, t
    out["descent_s"] = descent
    out["down_speed_c1"] = (max((f[3] for f in frames if f[3] is not None and first_low_t - DESCENT_LOOKBACK_S <= f[0] <= first_low_t),
                                default=None) if first_low_t is not None else None)
    return out


def main():
    parser = argparse.ArgumentParser(description="Per-sequence representative values (tune sequences only)")
    parser.add_argument("--pipeline", choices=("android", "pc"), default="android")
    parser.add_argument("--source", choices=("urfall", "caucafall"), default="urfall")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    OUT_DIR = BASE[args.source]
    with open(os.path.join(OUT_DIR, "split.csv"), encoding="utf-8") as fp:
        split = {r["sequence"]: r for r in csv.DictReader(fp)}
    tune = {s for s, r in split.items() if r["split"] == "tune"}
    tags = load_tags(os.path.join(OUT_DIR, "adl_tags.csv"))
    per_seq = {}
    with open(os.path.join(OUT_DIR, f"features_{args.pipeline}.csv"), encoding="utf-8") as fp:
        for r in csv.DictReader(fp):
            if r["sequence"] not in tune or (r["person"] != "" and r["main"] != "1"):
                continue
            per_seq.setdefault(r["sequence"], []).append(
                (float(r["time_s"]), num(r["A1_body_angle_shoulder"]), num(r["H3_head_above_ankle"]),
                 num(r["C1_descent_025"]), num(r["C2_descent_050"]), num(r["B1_box_ratio"]), num(r["E4_motion"])))
    rows = []
    for seq in sorted(per_seq):
        g = split[seq]["group"] if seq.startswith("fall") else adl_group(seq, tags)
        rows.append({"sequence": seq, "group": g, "frames": len(per_seq[seq]), **sequence_values(per_seq[seq])})

    def f(v, d=2):
        return "-" if v is None else (("예" if v else "아니오") if isinstance(v, bool) else f"{v:.{d}f}")

    order = ("fall_stand", "fall_chair", "fall_cf", "adl_normal", "adl_lying_bed", "adl_lying_floor")
    lines = [f"# 4-3 영상별 대표값: {args.source} {args.pipeline} (찾는 용 영상만)", "",
             f"낮은 자세 = A1 < {LOW_ANGLE:g}°, 넓게 본 낮은 자세 = A1 < {LOW_ANGLE:g}° 또는 H3 < {LOW_H3:g} 또는 B1 > {LOW_B1:g}, "
             f"위 자세 = H3 ≥ {UP_H3:g} (설명용 기준, 규칙의 기준값 아님). 사람이 {GAP_S:g}초 이하로 안 보이면 낮은 자세가 "
             f"이어진 것으로 셈. 넘어진 뒤 움직임 = 처음 넓게 본 낮은 자세가 된 뒤 {SETTLE_S[0]:g}~{SETTLE_S[1]:g}초의 E4 중앙값", "",
             "## 그룹별 요약 (중앙값, 범위)", "",
             "| 그룹 | 영상 | 낮은 자세가 나온 영상 | 낮은 자세 최대 지속 (초) | 넓게 본 낮은 자세 최대 지속 (초) | 최대 하강 속도 C1 | 넘어진 뒤 움직임 E4 |",
             "|---|---|---|---|---|---|---|"]

    def summary(vals):
        vals = [v for v in vals if v is not None]
        return "-" if not vals else f"{statistics.median(vals):.2f} ({min(vals):.2f}~{max(vals):.2f})"
    for g in order:
        rs = [r for r in rows if r["group"] == g]
        if not rs:
            continue
        lines.append(f"| {g} | {len(rs)} | {sum(1 for r in rs if r['low_any'])} | {summary([r['low_run_s'] for r in rs])} | "
                     f"{summary([r['low_run_wide_s'] for r in rs])} | {summary([r['c1_max'] for r in rs])} | "
                     f"{summary([r['motion_after'] for r in rs])} |")
    lines += ["", "## 영상별", "", "| " + " | ".join(COLUMNS) + " |", "|" + "---|" * len(COLUMNS)]
    for g in order:
        for r in (r for r in rows if r["group"] == g):
            lines.append("| " + " | ".join(str(r[c]) if c in ("sequence", "group", "frames") else f(r[c]) for c in COLUMNS) + " |")
    text = "\n".join(lines) + "\n"
    out = os.path.join(OUT_DIR, f"seqstats_{args.pipeline}")
    with open(out + ".md", "w", encoding="utf-8") as fp:
        fp.write(text)
    with open(out + ".csv", "w", encoding="utf-8", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    print(text)


if __name__ == "__main__":
    main()
