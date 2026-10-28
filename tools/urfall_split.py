"""Split the UR Fall sequences into "tune" (used to find thresholds) and "test" (scored once at the end).

Whole sequences go to one side (frames of one video never sit on both sides). Per group, a fixed random
draw with a recorded seed (counts for the 61 sequences of 2026-10-28):
  fall_stand    odd fall-XX: standing, then falling        9 tune / 6 test
  fall_chair    even fall-XX: sitting on a chair, falling   9 tune / 6 test
  adl_normal    adl-XX without frames labelled lying (1)   9 tune / 6 test
  adl_lying     adl-XX with frames labelled lying (1)      8 tune / 8 test
(UR Fall's even-numbered falls start on a chair: none of them has a standing frame, see the standing
reference table in summary_android.md; the two kinds are split separately so neither side gets only one.)
The result is written once to eval_output/urfall_features/split.csv and then kept: running again does not
redraw (use --force only to start over on purpose, e.g. with new sequences, and write the reason with --reason;
it goes to split_history.md).

Usage (from the project root): venv\\Scripts\\python.exe tools\\urfall_split.py
"""
import argparse
import csv
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tools.urfall_record import DEFAULT_DATASET, sequences  # noqa: E402
from tools.urfall_score import load_labels  # noqa: E402

SEED = 20261028   # 한 번 정해 고정 (바꾸면 다른 나눔이 됨)
TUNE_COUNT = {"fall_stand": 9, "fall_chair": 9, "adl_normal": 9, "adl_lying": 8}
OUT = os.path.join(ROOT, "eval_output", "urfall_features", "split.csv")
HISTORY = os.path.join(ROOT, "eval_output", "urfall_features", "split_history.md")


def group_of(seq, labels):
    if seq.startswith("fall"):
        return "fall_chair" if int(seq.split("-")[1]) % 2 == 0 else "fall_stand"
    return "adl_lying" if 1 in labels.get(seq, {}).values() else "adl_normal"


def make_split(names, labels, seed=SEED):
    """[(sequence, group, split)] sorted by name; per group TUNE_COUNT drawn at random as tune, the rest test."""
    groups = {}
    for n in sorted(names):
        groups.setdefault(group_of(n, labels), []).append(n)
    rng = random.Random(seed)
    out = []
    for g in sorted(groups):
        members = groups[g]
        if TUNE_COUNT[g] >= len(members):
            raise SystemExit(f"[split] {g}: 영상 {len(members)}개로는 찾는 용 {TUNE_COUNT[g]}개 + 시험용을 만들 수 없음")
        tune = set(rng.sample(members, TUNE_COUNT[g]))
        out += [(n, g, "tune" if n in tune else "test") for n in members]
    return sorted(out)


def main():
    parser = argparse.ArgumentParser(description="Fixed tune/test split of UR Fall sequences")
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--force", action="store_true", help="draw again even if split.csv exists (on purpose only)")
    parser.add_argument("--reason", default="", help="why the split is drawn (required with --force)")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if os.path.exists(OUT) and not args.force:
        raise SystemExit(f"[split] 이미 있음 (고정): {OUT}. 다시 뽑으려면 --force --reason \"이유\"")
    if os.path.exists(OUT) and not args.reason.strip():
        raise SystemExit("[split] 다시 뽑을 때는 --reason 으로 이유를 적어야 합니다")
    names = [n for n, _ in sequences(args.dataset)]
    rows = make_split(names, load_labels(args.dataset))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="") as fp:
        w = csv.writer(fp)
        w.writerow(["sequence", "group", "split", "seed"])
        for n, g, s in rows:
            w.writerow([n, g, s, SEED])
    import datetime
    with open(HISTORY, "a", encoding="utf-8") as fp:
        tune = [n for n, _, s in rows if s == "tune"]
        fp.write(f"\n## {datetime.datetime.now():%Y-%m-%d %H:%M} 나눔 (seed {SEED}, 영상 {len(rows)}개)\n"
                 f"- 이유: {args.reason.strip() or '처음 나눔'}\n- 종류별 찾는 용 개수: {TUNE_COUNT}\n"
                 f"- 찾는 용: {', '.join(tune)}\n- 시험용: {', '.join(n for n, _, s in rows if s == 'test')}\n")
    for n, g, s in rows:
        print(f"{n}\t{g}\t{s}")
    print(f"[split] 저장: {OUT}, 기록: {HISTORY}")


if __name__ == "__main__":
    main()
