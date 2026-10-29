"""Stage 4-2: how each feature is distributed in falls vs everyday actions (tune sequences only).

Input (eval_output/urfall_features/): features_<pipeline>.csv (tools/urfall_features.py), split.csv
(tools/urfall_split.py) and adl_tags.csv (everyday-action segments of the tune ADL sequences, checked by the
user). Only rows of the main person in "tune" sequences are used; test sequences are never read.

Groups (one per frame):
  fall_before / fall_falling / fall_lying   fall sequences by dataset label -1 / 0 / 1
  walk_stand, bend, squat, kneel_floor, sit_chair, sit_bed, lie_bed (lying down on / lying on a bed or sofa),
  lie_floor (getting down on / lying on the floor on purpose), get_up                  everyday segments
For every feature: count, empty share and percentiles per group, and the AUC of "fall frame vs everyday
frame" for the fall phase the feature is meant for (posture features: fall_lying, speed and motion features:
fall_falling). AUC = chance that a random fall frame has a larger value than a random everyday frame:
0.5 = the feature does not tell them apart, near 1 or near 0 = it does (near 0 means "smaller in falls").

Usage (from the project root, inside the detection venv):
  venv\\Scripts\\python.exe tools\\urfall_distributions.py --pipeline android
Output: eval_output/urfall_features/dist_<pipeline>.md and dist_<pipeline>/<feature>.png
"""
import argparse
import bisect
import csv
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tools.urfall_features import FEATURES, OUT_DIR  # noqa: E402

# 일상 동작 표시(adl_tags.csv)의 동작 → 분석 그룹
ACTION_GROUP = {
    "walk": "walk_stand", "stand": "walk_stand", "bend": "bend", "squat": "squat", "kneel_floor": "kneel_floor",
    "sit_down": "sit_chair", "sit_chair": "sit_chair", "sit_bed": "sit_bed",
    "lie_down": "lie_bed", "lie_bed": "lie_bed", "lie_down_floor": "lie_floor", "lie_floor": "lie_floor",
    "get_up": "get_up",
}
FALL_GROUPS = ("fall_before", "fall_falling", "fall_lying")
ADL_GROUPS = ("walk_stand", "bend", "squat", "kneel_floor", "sit_chair", "sit_bed", "lie_bed", "lie_floor", "get_up")
GROUP_KO = {"fall_before": "낙상 전", "fall_falling": "넘어지는 중", "fall_lying": "낙상 후 누움",
            "walk_stand": "걷기·서기", "bend": "숙이기", "squat": "쪼그리기", "kneel_floor": "무릎 꿇기",
            "sit_chair": "의자 앉기", "sit_bed": "침대·소파 앉기", "lie_bed": "침대·소파 눕기",
            "lie_floor": "바닥 엎드리기·눕기", "get_up": "일어나는 중"}
# 특징이 잡으려는 낙상 단계: 속도·움직임은 넘어지는 순간, 나머지는 넘어진 뒤 자세
FALL_PHASE_OF = {f: ("fall_falling" if f.startswith(("C1", "C2", "E4")) else "fall_lying") for f in FEATURES}
PERCENTILES = (5, 25, 50, 75, 95)


def load_tags(path):
    """{sequence: [(start, end, action)]} sorted by start."""
    tags = {}
    with open(path, encoding="utf-8") as fp:
        for r in csv.DictReader(fp):
            tags.setdefault(r["sequence"], []).append((int(r["start_frame"]), int(r["end_frame"]), r["action"]))
    for v in tags.values():
        v.sort()
    return tags


def group_of(row, tags):
    """Analysis group of one CSV row, or None (fall frame without label, untagged ADL frame)."""
    if row["kind"] == "fall":
        return {"-1": "fall_before", "0": "fall_falling", "1": "fall_lying"}.get(str(row["label"]))
    segs = tags.get(row["sequence"], [])
    f = int(row["frame"])
    i = bisect.bisect_right([s[0] for s in segs], f) - 1
    if i >= 0 and segs[i][0] <= f <= segs[i][1]:
        return ACTION_GROUP.get(segs[i][2])
    return None


def percentile(sorted_values, p):
    if not sorted_values:
        return None
    k = (len(sorted_values) - 1) * p / 100
    lo, hi = int(k), min(int(k) + 1, len(sorted_values) - 1)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (k - lo)


def auc(positives, negatives):
    """P(random positive > random negative) + 0.5 * P(equal), by ranks (Mann-Whitney). None if a side is empty."""
    if not positives or not negatives:
        return None
    allv = sorted([(v, 1) for v in positives] + [(v, 0) for v in negatives])
    rank_sum, i = 0.0, 0
    while i < len(allv):
        j = i
        while j < len(allv) and allv[j][0] == allv[i][0]:
            j += 1
        mid = (i + 1 + j) / 2                     # 같은 값은 평균 순위
        rank_sum += mid * sum(1 for k in range(i, j) if allv[k][1] == 1)
        i = j
    n1, n0 = len(positives), len(negatives)
    return (rank_sum - n1 * (n1 + 1) / 2) / (n1 * n0)


def collect(features_csv, split_csv, tags):
    """{group: {"frames": n, feature: [values]}} for main-person rows of tune sequences (+ frames without a person)."""
    with open(split_csv, encoding="utf-8") as fp:
        tune = {r["sequence"] for r in csv.DictReader(fp) if r["split"] == "tune"}
    data = {g: {"frames": 0, "nobody": 0, **{f: [] for f in FEATURES}} for g in FALL_GROUPS + ADL_GROUPS}
    with open(features_csv, encoding="utf-8") as fp:
        for r in csv.DictReader(fp):
            if r["sequence"] not in tune:
                continue
            g = group_of(r, tags)
            if g is None:
                continue
            if r["person"] == "":                 # 사람 없는 프레임
                data[g]["frames"] += 1
                data[g]["nobody"] += 1
                continue
            if r["main"] != "1":
                continue
            data[g]["frames"] += 1
            for f in FEATURES:
                if r[f] != "":
                    data[g][f].append(float(r[f]))
    for g in data:
        for f in FEATURES:
            data[g][f].sort()
    return data, sorted(tune)


def report(pipeline, data, tune):
    out = [f"# 4-2 특징 분포: {pipeline} (찾는 용 영상 {len(tune)}개만, 주 인물 기준)", "",
           "## 그룹별 프레임 수", "", "| 그룹 | 프레임 | 사람 없음 |", "|---|---|---|"]
    for g in FALL_GROUPS + ADL_GROUPS:
        d = data[g]
        out.append(f"| {GROUP_KO[g]} ({g}) | {d['frames']} | {d['nobody']} ({100 * d['nobody'] / max(d['frames'], 1):.0f}%) |")
    out += ["", "## 구분력 (AUC): 낙상 프레임 vs 일상 동작 프레임", "",
            "0.5 = 못 가름. 1에 가까움 = 낙상에서 더 큼, 0에 가까움 = 낙상에서 더 작음. "
            "자세 특징은 '낙상 후 누움', 속도·움직임(C1, C2, E4)은 '넘어지는 중'과 비교. |0.5와의 차이| ≥ 0.4 이면 **굵게**", "",
            "| 특징 | 비교한 낙상 단계 | " + " | ".join(GROUP_KO[g] for g in ADL_GROUPS) + " | 일상 전체 |",
            "|" + "---|" * (len(ADL_GROUPS) + 3)]
    for f in FEATURES:
        phase = FALL_PHASE_OF[f]
        cells = []
        for g in ADL_GROUPS + ("all",):
            neg = [v for gg in ADL_GROUPS for v in data[gg][f]] if g == "all" else data[g][f]
            a = auc(data[phase][f], neg)
            cells.append("-" if a is None else (f"**{a:.2f}**" if abs(a - 0.5) >= 0.4 else f"{a:.2f}"))
        out.append(f"| {f} | {GROUP_KO[phase]} | " + " | ".join(cells) + " |")
    out += ["", "## 특징별 분포 (값이 있는 프레임 수, 빈칸 비율, 백분위수 5·25·50·75·95%)", ""]
    for f in FEATURES:
        out += [f"### {f}", "", "| 그룹 | 값 있음 | 빈칸 | p5 | p25 | p50 | p75 | p95 |", "|---|---|---|---|---|---|---|---|"]
        for g in FALL_GROUPS + ADL_GROUPS:
            v, n = data[g][f], data[g]["frames"]
            ps = [percentile(v, p) for p in PERCENTILES]
            out.append(f"| {GROUP_KO[g]} | {len(v)} | {100 * (n - len(v)) / max(n, 1):.0f}% | "
                       + " | ".join("-" if p is None else f"{p:.2f}" for p in ps) + " |")
        out.append("")
    return "\n".join(out) + "\n"


HIST_GROUPS = ("fall_falling", "fall_lying", "walk_stand", "bend", "squat", "sit_chair", "lie_bed", "lie_floor")
HIST_COLORS = {"fall_falling": "#d62728", "fall_lying": "#8c1c13", "walk_stand": "#1f77b4", "bend": "#17becf",
               "squat": "#2ca02c", "sit_chair": "#9467bd", "lie_bed": "#ff7f0e", "lie_floor": "#e377c2"}
HIST_LABEL = {"fall_falling": "fall: falling", "fall_lying": "fall: lying", "walk_stand": "walk/stand",
              "bend": "bend", "squat": "squat", "sit_chair": "sit (chair)", "lie_bed": "lie (bed/sofa)",
              "lie_floor": "lie (floor, on purpose)"}


def histograms(data, out_dir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    os.makedirs(out_dir, exist_ok=True)
    for f in FEATURES:
        values = [v for g in HIST_GROUPS for v in data[g][f]]
        if not values:
            continue
        lo, hi = percentile(sorted(values), 1), percentile(sorted(values), 99)
        if lo == hi:
            continue
        fig, ax = plt.subplots(figsize=(9, 4.5))
        for g in HIST_GROUPS:
            v = [x for x in data[g][f] if lo <= x <= hi]
            if v:
                ax.hist(v, bins=40, range=(lo, hi), density=True, histtype="step", linewidth=1.6,
                        color=HIST_COLORS[g], label=f"{HIST_LABEL[g]} (n={len(data[g][f])})")
        ax.set_title(f"{f} (tune sequences, main person)")
        ax.set_xlabel(f)
        ax.set_ylabel("share of frames (density)")
        ax.legend(fontsize=8, ncol=2)
        fig.tight_layout()
        fig.savefig(os.path.join(out_dir, f"{f}.png"), dpi=110)
        plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description="Feature distributions of falls vs everyday actions (tune only)")
    parser.add_argument("--pipeline", choices=("android", "pc"), default="android")
    parser.add_argument("--source", choices=("urfall", "caucafall"), default="urfall",
                        help="caucafall: eval_output/caucafall (tools/caucafall_prepare.py, urfall_features --source caucafall)")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    base = OUT_DIR if args.source == "urfall" else os.path.join(ROOT, "eval_output", "caucafall")
    tags = load_tags(os.path.join(base, "adl_tags.csv"))
    data, tune = collect(os.path.join(base, f"features_{args.pipeline}.csv"), os.path.join(base, "split.csv"), tags)
    text = report(f"{args.source} {args.pipeline}", data, tune)
    out_md = os.path.join(base, f"dist_{args.pipeline}.md")
    with open(out_md, "w", encoding="utf-8") as fp:
        fp.write(text)
    histograms(data, os.path.join(base, f"dist_{args.pipeline}"))
    print(text.split("## 특징별 분포")[0])
    print(f"[dist] 저장: {out_md}, 그림: {os.path.join(base, f'dist_{args.pipeline}')}")


if __name__ == "__main__":
    main()
