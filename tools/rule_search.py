"""Stage 4-4: search the thresholds of a two-part time rule on the TUNE sequences of UR Fall and CAUCAFall.

Rule (main person of each frame, features from tools/urfall_features.py, android pipeline by default):
  low(t)  = A1 < a  or  H3 < h                         (body line flat, or head down at foot level)
  wide(t) = low(t)  or  B1 > b                          (also: person box wider than tall)
  A "fast drop":  smoothed C1 (median of 3 consecutive values) >= v, and within w seconds after it at least
                  k frames are low (A_after = "low") or wide (A_after = "wide") → alarm at the last of those frames
  B "stays down": wide frames for at least T seconds in a row; frames without a value for at most GAP_S do not
                  break the run, a frame with values that is not wide does → alarm T seconds after the run starts
  alarm = A or B (a part can be switched off: v = off or T = off)
Scoring per sequence, like tools/urfall_score.py: a fall sequence is hit when an alarm comes at or after the
fall start (first label-0 frame) minus 0.5 s; an earlier alarm in a fall sequence and any alarm in an everyday
sequence is a false alarm (one per sequence here: the app sends one event and the server keeps one incident).
Choice (decided with the user before looking): recall >= 90 % over the tune falls of both datasets, then the
fewest false alarms; ties: higher recall, then the simpler rule, then the larger values of T and v.
Test sequences are never read.

Usage: venv\\Scripts\\python.exe tools\\rule_search.py [--pipeline android]
Output: eval_output/rule_search_<pipeline>.md (+ .csv of every combination)
"""
import argparse
import csv
import itertools
import math
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCES = {"urfall": os.path.join(ROOT, "eval_output", "urfall_features"),
           "caucafall": os.path.join(ROOT, "eval_output", "caucafall")}
OUT = os.path.join(ROOT, "eval_output")

DROP_WINDOW_S = 1.0
DROP_LOW_FRAMES = 3
GAP_S = 1.0
EARLY_TOLERANCE_S = 0.5
MIN_RECALL = 0.90
OFF = math.inf
GRID = {
    "a": (20, 25, 30, 35, 40),                    # 몸 선 각도 (도)
    "h": (0.3, 0.5, 0.7, 1.0),                    # 머리가 발목보다 위 (몸통 길이)
    "b": (1.0, 1.2, 1.5, OFF),                    # 상자 가로/세로 (OFF = 쓰지 않음)
    "v": (1.5, 2.0, 3.0, 4.0, 5.0, OFF),          # 하강 속도 (몸통 길이/초)
    "T": (1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, OFF),  # 바닥 유지 시간 (초)
    "after": ("low", "wide"),                     # (A) 내려간 뒤 확인하는 자세
    "k": (1, 2, 3),                               # (A) 그 자세가 나와야 하는 프레임 수
    "w": (1.0, 1.5),                              # (A) 확인 시간 (초)
}


def num(x):
    return None if x == "" else float(x)


def load(pipeline, split="tune"):
    """[{source, sequence, kind, fall_start, frames: [(t, a1, h3, b1, c1)]}] of the sequences of one split side."""
    out = []
    for src, base in SOURCES.items():
        with open(os.path.join(base, "split.csv"), encoding="utf-8") as fp:
            tune = {r["sequence"] for r in csv.DictReader(fp) if r["split"] == split}
        seqs = {}
        with open(os.path.join(base, f"features_{pipeline}.csv"), encoding="utf-8") as fp:
            for r in csv.DictReader(fp):
                if r["sequence"] not in tune or (r["person"] != "" and r["main"] != "1"):
                    continue
                s = seqs.setdefault(r["sequence"], {"frames": [], "fall_start": None})
                t = float(r["time_s"])
                s["frames"].append((t, num(r["A1_body_angle_shoulder"]), num(r["H3_head_above_ankle"]),
                                    num(r["B1_box_ratio"]), num(r["C1_descent_025"])))
                if r["label"] == "0" and s["fall_start"] is None:
                    s["fall_start"] = t
        for name, s in sorted(seqs.items()):
            s["frames"].sort()
            out.append({"source": src, "sequence": name, "kind": "fall" if name.startswith("fall") else "adl",
                        "fall_start": s["fall_start"], "frames": s["frames"]})
    return out


def smooth(values):
    """Median of each value with its neighbours (3 consecutive present values); None stays None."""
    out = []
    for i, v in enumerate(values):
        if v is None:
            out.append(None)
            continue
        win = [x for x in values[max(0, i - 1):i + 2] if x is not None]
        out.append(statistics.median(win))
    return out


def prepare(seq):
    f = seq["frames"]
    seq["t"] = [x[0] for x in f]
    seq["c1s"] = smooth([x[4] for x in f])
    seq["has"] = [x[1] is not None or x[2] is not None or x[3] is not None for x in f]
    return seq


def low_flags(seq, a, h):
    return [(x[1] is not None and x[1] < a) or (x[2] is not None and x[2] < h) for x in seq["frames"]]


def drop_alarm(seq, low, v, k=DROP_LOW_FRAMES, w=DROP_WINDOW_S):
    """First alarm time of part A, or None."""
    if v == OFF:
        return None
    t, c = seq["t"], seq["c1s"]
    for i, ci in enumerate(c):
        if ci is None or ci < v:
            continue
        n = 0
        for j in range(i + 1, len(t)):
            if t[j] - t[i] > w:
                break
            if low[j]:
                n += 1
                if n >= k:
                    return t[j]
    return None


def runs(seq, wide):
    """[(start, end)] of wide runs with the GAP_S rule."""
    t, has = seq["t"], seq["has"]
    out, start, last = [], None, None
    for ti, w, hv in zip(t, wide, has):
        if w:
            if start is None or ti - last > GAP_S:
                if start is not None:
                    out.append((start, last))
                start = ti
            last = ti
        elif hv and start is not None:
            out.append((start, last))
            start = None
    if start is not None:
        out.append((start, last))
    return out


def stay_alarm(run_list, T):
    if T == OFF:
        return None
    for s, e in run_list:
        if e - s >= T:
            return s + T
    return None


def outcome(seq, alarm):
    """('hit' | 'miss' | 'fa' | 'ok', delay or None)."""
    if seq["kind"] == "fall":
        if alarm is None:
            return "miss", None
        if seq["fall_start"] is not None and alarm < seq["fall_start"] - EARLY_TOLERANCE_S:
            return "fa_early", None
        return "hit", alarm - (seq["fall_start"] or 0)
    return ("fa", None) if alarm is not None else ("ok", None)


def evaluate(seqs, cache, a, h, b, v, T, after="low", kk=DROP_LOW_FRAMES, w=DROP_WINDOW_S):
    res = []
    for k, seq in enumerate(seqs):
        low = cache[("low", k, a, h)]
        wide = cache.get(("wide", k, a, h, b))
        if wide is None:
            wide = [lo or (x[3] is not None and x[3] > b) for lo, x in zip(low, seq["frames"])]
            cache[("wide", k, a, h, b)] = wide
            cache[("runs", k, a, h, b)] = runs(seq, wide)
        times = [x for x in (drop_alarm(seq, low if after == "low" else wide, v, kk, w), stay_alarm(cache[("runs", k, a, h, b)], T))
                 if x is not None]
        res.append(outcome(seq, min(times) if times else None))
    return res


def summarize(seqs, res):
    falls = [r for s, r in zip(seqs, res) if s["kind"] == "fall"]
    adls = [r for s, r in zip(seqs, res) if s["kind"] == "adl"]
    hits = sum(1 for r in falls if r[0] == "hit")
    fa = sum(1 for r in adls if r[0] == "fa") + sum(1 for r in falls if r[0] == "fa_early")
    delays = [r[1] for r in falls if r[0] == "hit"]
    return {"recall": hits / len(falls), "hits": hits, "falls": len(falls), "fa": fa, "adls": len(adls),
            "delay": statistics.median(delays) if delays else None}


def main():
    parser = argparse.ArgumentParser(description="Threshold search for the two-part fall rule (tune sequences)")
    parser.add_argument("--pipeline", choices=("android", "pc"), default="android")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    seqs = [prepare(s) for s in load(args.pipeline)]
    cache = {}
    for k, seq in enumerate(seqs):
        for a in GRID["a"]:
            for h in GRID["h"]:
                cache[("low", k, a, h)] = low_flags(seq, a, h)
    results = []
    for a, h, b, v, T, after, kk, w in itertools.product(*GRID.values()):
        if v == OFF and T == OFF:
            continue
        if v == OFF and (after, kk, w) != ("low", 1, 1.0):
            continue                                       # (A) 를 끄면 (A) 의 세부 설정은 의미 없음: 한 번만
        res = evaluate(seqs, cache, a, h, b, v, T, after, kk, w)
        s = summarize(seqs, res)
        results.append({"a": a, "h": h, "b": b, "v": v, "T": T, "after": after, "k": kk, "w": w, **s, "res": res})

    def key(r):
        simple = (r["v"] == OFF) + (r["T"] == OFF) + (r["b"] == OFF)
        return (r["fa"], -r["recall"], -simple, -(r["T"] if r["T"] != OFF else 99), -(r["v"] if r["v"] != OFF else 99))
    ok = sorted((r for r in results if r["recall"] >= MIN_RECALL), key=key)
    best = ok[0] if ok else max(results, key=lambda r: (r["recall"], -r["fa"]))

    fmt = lambda x: "끔" if x == OFF else f"{x:g}"  # noqa: E731
    fmt_delay = lambda d: "-" if d is None else f"{d:.1f}"  # noqa: E731
    lines = [f"# 4-4 기준값 찾기: {args.pipeline} (찾는 용 영상만)", "",
             f"- 찾는 용: 낙상 {best['falls']}개, 일상 {best['adls']}개 (UR Fall + CAUCAFall), 조합 {len(results)}개 시험",
             f"- 원칙: 재현율 ≥ {MIN_RECALL:.0%} 중 오탐이 가장 적은 조합 (같으면 재현율 높은 것, 단순한 것, T·v 가 큰 것)",
             f"- 조건을 만족한 조합: {len(ok)}개", "",
             "## 고른 조합", "",
             f"- 낮은 자세: 각도 A1 < **{fmt(best['a'])}°** 또는 머리 높이 H3 < **{fmt(best['h'])}**",
             f"- 넓게 본 낮은 자세: 위 조건 또는 상자 비율 B1 > **{fmt(best['b'])}**",
             f"- (A) 빠르게 내려감: 하강 속도 ≥ **{fmt(best['v'])}** 몸통/초 뒤 **{best['w']:g}초** 안에 "
             f"{'낮은 자세' if best['after'] == 'low' else '넓게 본 낮은 자세'} **{best['k']}프레임**",
             f"- (B) 바닥에 있음 유지: 넓게 본 낮은 자세 **{fmt(best['T'])}초** 이상",
             f"- 결과: 재현율 {best['hits']}/{best['falls']} = {best['recall']:.0%}, 오탐 {best['fa']}/{best['adls']}, "
             f"감지 지연 중앙값 {best['delay']:.1f}초 (넘어지기 시작부터)" if best["delay"] is not None else "", ""]
    for src in SOURCES:
        idx = [i for i, s in enumerate(seqs) if s["source"] == src]
        sub = summarize([seqs[i] for i in idx], [best["res"][i] for i in idx])
        lines.append(f"- {src}: 재현율 {sub['hits']}/{sub['falls']} = {sub['recall']:.0%}, 오탐 {sub['fa']}/{sub['adls']}"
                     + (f", 지연 중앙값 {sub['delay']:.1f}초" if sub["delay"] is not None else ""))
    lines += ["", "놓친 낙상: " + (", ".join(s["sequence"] for s, r in zip(seqs, best["res"]) if r[0] in ("miss", "fa_early")) or "없음"),
              "오탐이 난 일상 동작: " + (", ".join(s["sequence"] for s, r in zip(seqs, best["res"]) if r[0] == "fa") or "없음"), "",
              "## 조건을 만족한 상위 15개", "", "| a | h | b | v | T | A 확인 자세 | k | w | 재현율 | 오탐 | 지연(초) |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in ok[:15]:
        lines.append(f"| {fmt(r['a'])} | {fmt(r['h'])} | {fmt(r['b'])} | {fmt(r['v'])} | {fmt(r['T'])} | {r['after']} | {r['k']} | {r['w']:g} | "
                     f"{r['hits']}/{r['falls']} | {r['fa']} | {fmt_delay(r['delay'])} |")
    lines += ["", "## 비교: 한 부분만 쓰는 경우 (각자 원칙대로 고른 것)", ""]
    for name, cond in (("(A)만", lambda r: r["T"] == OFF), ("(B)만", lambda r: r["v"] == OFF)):
        cand = sorted((r for r in results if cond(r) and r["recall"] >= MIN_RECALL), key=key)
        top = cand[0] if cand else max((r for r in results if cond(r)), key=lambda r: (r["recall"], -r["fa"]))
        lines.append(f"- {name}: a {fmt(top['a'])}, h {fmt(top['h'])}, b {fmt(top['b'])}, v {fmt(top['v'])}, T {fmt(top['T'])} → "
                     f"재현율 {top['hits']}/{top['falls']} = {top['recall']:.0%}, 오탐 {top['fa']}/{top['adls']}"
                     + ("" if cand else " (재현율 90%를 넘는 조합 없음: 재현율 가장 높은 것)"))
    text = "\n".join(lines) + "\n"
    with open(os.path.join(OUT, f"rule_search_{args.pipeline}.md"), "w", encoding="utf-8") as fp:
        fp.write(text)
    with open(os.path.join(OUT, f"rule_search_{args.pipeline}.csv"), "w", encoding="utf-8", newline="") as fp:
        w = csv.writer(fp)
        w.writerow(["a", "h", "b", "v", "T", "after", "k", "w", "recall", "hits", "falls", "false_alarms", "adls", "delay_s"])
        for r in results:
            w.writerow([r["a"], r["h"], r["b"], r["v"], r["T"], r["after"], r["k"], r["w"], f"{r['recall']:.3f}", r["hits"], r["falls"], r["fa"], r["adls"],
                        "" if r["delay"] is None else f"{r['delay']:.2f}"])
    print(text)


if __name__ == "__main__":
    main()
