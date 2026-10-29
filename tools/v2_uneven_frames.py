"""Fall rule v2 when frames arrive unevenly, as on a phone camera that drops frames it cannot keep up with.

Takes the Android-style pose logs of the TUNE videos only (the test videos were scored once, docs/fall_rule_v2.md),
removes frames in a few fixed (seeded) patterns, keeps the remaining frames' own times, and runs v2 twice:
  frames  the descent speed C1 counted in frames at the nominal rate (round(0.25 * fps) frames back, / 0.25 s),
          what the app would get when it assumes a steady rate
  time    C1 against the frame closest to 0.25 s before, divided by the real time between them
          (tools/urfall_features.py timing="time", V2Features in the app)
Both are the same on the full logs. Output: eval_output/v2_uneven_frames.md

  python tools/v2_uneven_frames.py
"""
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fall_logic.v2 import FallRuleV2, Params  # noqa: E402
from tools import pose_log  # noqa: E402
from tools.rule_search import load, outcome  # noqa: E402
from tools.urfall_features import sequence_rows  # noqa: E402

LOGS = {"urfall": os.path.join(ROOT, "eval_output", "urfall_android"),
        "caucafall": os.path.join(ROOT, "eval_output", "caucafall", "android")}
OUT = os.path.join(ROOT, "eval_output", "v2_uneven_frames.md")
FEATS = ("A1_body_angle_shoulder", "H3_head_above_ankle", "B1_box_ratio", "C1_descent_025")
SEED = 20261029


def keep_all(frames, rng):
    return frames


def every_other(frames, rng):
    return frames[::2]


def random_40(frames, rng):
    return [f for i, f in enumerate(frames) if i == 0 or rng.random() >= 0.4]


def stalls(frames, rng):
    """Mostly every frame, sometimes a stall of 3 to 8 frames in a row (about a third dropped)."""
    out, i = [], 0
    while i < len(frames):
        out.append(frames[i])
        i += 1 + (rng.randint(3, 8) if rng.random() < 0.08 else 0)
    return out


def every_other_jitter(frames, rng):
    """Half the rate with uneven gaps: after each kept frame skip 0, 1 or 2 frames."""
    out, i = [], 0
    while i < len(frames):
        out.append(frames[i])
        i += 1 + rng.choice((0, 1, 2))
    return out


PATTERNS = (("전체 (고른 간격)", keep_all), ("하나 걸러 (절반 속도)", every_other),
            ("절반 속도, 간격 불규칙", every_other_jitter), ("무작위 40% 버림", random_40),
            ("가끔 몇 프레임씩 멈춤", stalls))


def alarm(name, header, frames, timing):
    rows = sequence_rows("android", name, frames, {}, fps=header.get("fps") or 30, timing=timing)
    by = {r["frame"]: [None if r[f] == "" else r[f] for f in FEATS] for r in rows if r["person"] == "" or r["main"] == 1}
    rule = FallRuleV2(Params())
    for r in frames:
        rule.update(r["now"], *by[r["index"] + 1])
    return rule.alarm


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    seqs = load("android", "tune")
    logs = {}
    for s in seqs:
        logs[s["sequence"]] = pose_log.read_log(os.path.join(LOGS[s["source"]], s["sequence"] + ".jsonl"))
    falls = sum(1 for s in seqs if s["kind"] == "fall")
    adls = len(seqs) - falls
    lines = [f"# v2: 프레임이 고르지 않게 들어올 때 (찾는 용 영상 {len(seqs)}개: 낙상 {falls}, 일상 {adls})", "",
             "`tools/v2_uneven_frames.py`. 시험용 영상은 쓰지 않음. 오탐 = 일상 오탐 + 낙상 전 알림. "
             "'전체와 다름' = 같은 영상의 전체 프레임 결과(hit/miss/fa/ok)와 다른 영상 수.", "",
             "| 버리는 방식 | 남은 프레임 | C1 계산 | 재현율 | 오탐 | 전체와 다름 |", "|---|---|---|---|---|---|"]
    full = {}
    for title, pattern in PATTERNS:
        rng = random.Random(SEED)
        kept = {name: pattern(frames, rng) for name, (header, frames) in logs.items()}
        share = sum(len(v) for v in kept.values()) / sum(len(f) for _, f in logs.values())
        for timing in ("frames", "time"):
            res = {}
            for s in seqs:
                header = logs[s["sequence"]][0]
                res[s["sequence"]] = outcome(s, alarm(s["sequence"], header, kept[s["sequence"]], timing))[0]
            if pattern is keep_all:
                full[timing] = res
            hits = sum(1 for s in seqs if res[s["sequence"]] == "hit")
            fa = sum(1 for r in res.values() if r in ("fa", "fa_early"))
            ref = full.get("time") or full["frames"]   # 전체 프레임에서는 둘이 같음
            diff = sum(1 for k, r in res.items() if r != ref[k])
            lines.append(f"| {title} | {share:.0%} | {'프레임 수' if timing == 'frames' else '시각'} | "
                         f"{hits}/{falls} | {fa}/{adls} | {diff} |")
            print(lines[-1], flush=True)
    with open(OUT, "w", encoding="utf-8") as fp:
        fp.write("\n".join(lines) + "\n")
    print("→", OUT)


if __name__ == "__main__":
    main()
