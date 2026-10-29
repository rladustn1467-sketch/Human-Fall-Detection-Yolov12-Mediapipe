"""Stage 4-6: score fall rule v2 (fall_logic/v2.py, docs/fall_rule_v2.md) ONCE on the TEST sequences.

1. If the result file already exists, stop: the test sequences are scored only once (no option to redo).
2. Self-check before reading any test sequence: on the TUNE sequences the streaming rule must give exactly the
   same outcome per sequence as the offline search (tools/rule_search.py) with the same values; otherwise stop.
3. Test sequences of UR Fall and CAUCAFall (android features): per sequence hit / miss / false alarm with the
   same scoring as the search, the legacy rule on the same sequences (first fall frame in the pose log), and the
   falls where the person is hardly visible after the fall start (< UNSEEN_SHARE of the frames with a person)
   marked separately and shown in both totals (all falls, and falls with the person visible).

Usage: venv\\Scripts\\python.exe tools\\rule_test.py
Output: eval_output/rule_test_android.md and .csv
"""
import csv
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fall_logic.v2 import FallRuleV2, Params  # noqa: E402
from tools import pose_log  # noqa: E402
from tools import rule_search as rs  # noqa: E402

PIPELINE = "android"
OUT = os.path.join(ROOT, "eval_output", f"rule_test_{PIPELINE}")
LOGS = {"urfall": os.path.join(ROOT, "eval_output", "urfall_android"),
        "caucafall": os.path.join(ROOT, "eval_output", "caucafall", "android")}
UNSEEN_SHARE = 0.30       # 4-4 대안 1 과 같은 기준 (규칙 결과가 아니라 관절 검출만 보고 정함)


def v2_alarm(seq, params):
    rule = FallRuleV2(params)
    for t, a1, h3, b1, c1 in seq["frames"]:
        rule.update(t, a1, h3, b1, c1)
    return rule.alarm


def offline_outcomes(seqs, p):
    cache = {}
    for k, seq in enumerate(seqs):
        cache[("low", k, p.low_angle, p.low_head)] = rs.low_flags(seq, p.low_angle, p.low_head)
    return rs.evaluate(seqs, cache, p.low_angle, p.low_head, p.wide_box, p.drop_speed, p.stay_seconds,
                       p.drop_after, p.drop_frames, p.drop_window)


def unseen(seq):
    if seq["kind"] != "fall":
        return False
    idx = [i for i, t in enumerate(seq["t"]) if t >= seq["fall_start"] - rs.EARLY_TOLERANCE_S]
    return sum(seq["has"][i] for i in idx) / max(len(idx), 1) < UNSEEN_SHARE


def legacy_alarm(seq):
    _, frames = pose_log.read_log(os.path.join(LOGS[seq["source"]], seq["sequence"] + ".jsonl"))
    return next((r["now"] for r in frames if r["legacy"]["fall_detected"]), None)


def totals(rows, key):
    falls = [r for r in rows if r["kind"] == "fall"]
    vis = [r for r in falls if not r["unseen"]]
    adls = [r for r in rows if r["kind"] == "adl"]
    hit = lambda rr: sum(1 for r in rr if r[key] == "hit")  # noqa: E731
    fa = sum(1 for r in adls if r[key] == "fa") + sum(1 for r in falls if r[key] == "fa_early")
    delays = [r[key + "_delay"] for r in falls if r[key] == "hit"]
    return {"hit": hit(falls), "falls": len(falls), "hit_vis": hit(vis), "vis": len(vis), "fa": fa, "adls": len(adls),
            "delay": statistics.median(delays) if delays else None}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if os.path.exists(OUT + ".md"):
        raise SystemExit(f"[test] 시험용 채점은 한 번만 합니다. 이미 결과가 있음: {OUT}.md")
    params = Params()

    # 1) 찾는 용으로 자기 확인 (시험용은 아직 읽지 않음)
    tune = [rs.prepare(s) for s in rs.load(PIPELINE, "tune")]
    off = offline_outcomes(tune, params)
    mismatch = [s["sequence"] for s, o in zip(tune, off) if rs.outcome(s, v2_alarm(s, params))[0] != o[0]]
    if mismatch:
        raise SystemExit(f"[test] 실시간 규칙과 오프라인 검색의 판정이 다름 ({len(mismatch)}개): {mismatch[:10]} - 시험용 채점 안 함")
    print(f"[test] 자기 확인: 찾는 용 {len(tune)}개 영상에서 판정 모두 같음")

    # 2) 시험용 (한 번)
    test = [rs.prepare(s) for s in rs.load(PIPELINE, "test")]
    rows = []
    for s in test:
        v2, v2d = rs.outcome(s, v2_alarm(s, params))
        lg, lgd = rs.outcome(s, legacy_alarm(s))
        rows.append({"source": s["source"], "sequence": s["sequence"], "kind": s["kind"], "unseen": unseen(s),
                     "v2": v2, "v2_delay": v2d, "legacy": lg, "legacy_delay": lgd})

    def line(name, t):
        d = "-" if t["delay"] is None else f"{t['delay']:.1f}초"
        return (f"| {name} | {t['hit']}/{t['falls']} ({t['hit'] / t['falls']:.0%}) | "
                f"{t['hit_vis']}/{t['vis']} ({t['hit_vis'] / max(t['vis'], 1):.0%}) | {t['fa']}/{t['adls']} ({t['fa'] / max(t['adls'], 1):.0%}) | {d} |")
    lines = ["# 4-6 시험용 영상 채점 (한 번만): 규칙 v2 vs 지금 방식", "",
             f"- 시험용: UR Fall + CAUCAFall, 낙상 {sum(1 for r in rows if r['kind'] == 'fall')}개, 일상 {sum(1 for r in rows if r['kind'] == 'adl')}개 ({PIPELINE} 방식 관절)",
             f"- 규칙 v2 값: {params}",
             f"- 사람이 거의 안 보이는 낙상 = 넘어지기 시작(−0.5초) 뒤 사람이 잡힌 프레임 {UNSEEN_SHARE:.0%} 미만. 숨기지 않고 '전체'에 포함, '보이는 낙상'에서만 뺌",
             f"- 오탐 = 일상 영상에서 알림이 난 영상 수 (+ 낙상 영상에서 넘어지기 전에 난 알림)", ""]
    for src in (None, "urfall", "caucafall"):
        sub = [r for r in rows if src is None or r["source"] == src]
        title = "전체" if src is None else src
        lines += [f"## {title}", "", "| 규칙 | 재현율 (전체 낙상) | 재현율 (보이는 낙상) | 오탐 (일상 영상) | 지연 중앙값 |",
                  "|---|---|---|---|---|", line("v2", totals(sub, "v2")), line("지금 방식 (legacy)", totals(sub, "legacy")), ""]
    unseen_rows = [r for r in rows if r["unseen"]]
    lines += ["## 사람이 거의 안 보이는 낙상 (따로 표시)", ""]
    lines += [f"- {r['sequence']}: v2 {r['v2']}, 지금 방식 {r['legacy']}" for r in unseen_rows] or ["- 없음"]
    lines += ["", "## 영상별", "", "| 영상 | 종류 | 사람 거의 안 보임 | v2 | v2 지연(초) | 지금 방식 | 지금 방식 지연(초) |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        f = lambda d: "-" if d is None else f"{d:.1f}"  # noqa: E731
        lines.append(f"| {r['sequence']} | {r['kind']} | {'예' if r['unseen'] else ''} | {r['v2']} | {f(r['v2_delay'])} | {r['legacy']} | {f(r['legacy_delay'])} |")
    text = "\n".join(lines) + "\n"
    with open(OUT + ".md", "w", encoding="utf-8") as fp:
        fp.write(text)
    with open(OUT + ".csv", "w", encoding="utf-8", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(text)


if __name__ == "__main__":
    main()
