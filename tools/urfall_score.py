"""Event-level scoring of a fall engine on UR Fall pose logs (made by tools/urfall_record.py).

Ground truth: the per-frame labels in datasets/urfall/features/urfall-cam0-{falls,adls}.csv
(column 3: -1 = not lying, 0 = falling, 1 = lying on the ground).

Alerts: the engine's per-frame result turned into alerts the way the app does it (dashboard
update_statistics / Android FallPipeline): a fallen person ID gives an alert unless the same ID
gave one less than 5 s before. Each alert would be one fall event sent to the server.

Scoring, per sequence:
  fall-XX  hit when an alert comes at or after the fall start (first label-0 frame) minus 0.5 s;
           alerts before that are early false alarms; more alerts after the hit are repeats
           (the server keeps one open incident per home, so repeats do not reach the family twice).
           delay = first hit time - fall start, and - first lying frame.
  adl-XX   every alert is a false alarm; it is also noted whether it came during frames the
           dataset labels as lying (someone lying down on purpose).
Summary: recall (fall sequences hit / fall sequences), false alarms (count, per minute of ADL video),
precision = hits / (hits + false alarms), F1.

Engines: "legacy" = fall_logic.LegacyFallLogic (same as models/fall_detector.py and the Android app).
The replayed legacy result is also checked against what the original detector recorded in the log.

Usage (from the project root): venv\\Scripts\\python.exe tools\\urfall_score.py [--engine legacy]
Writes eval_output/urfall/score_<engine>.md and .csv and prints the table.
"""
import argparse
import csv
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fall_logic.legacy import LegacyFallLogic  # noqa: E402
from tools import pose_log  # noqa: E402
from tools.urfall_record import DEFAULT_DATASET, DEFAULT_OUT_DIR, FPS  # noqa: E402

ALERT_COOLDOWN_SECONDS = 5.0     # 대시보드 fall_cooldown, Android FallPipeline.FALL_COOLDOWN_SECONDS
EARLY_TOLERANCE_SECONDS = 0.5    # 정답 표시의 '넘어지는 중' 시작보다 이만큼 이른 알림까지는 맞힌 것으로 봄
LABEL_FILES = ("urfall-cam0-falls.csv", "urfall-cam0-adls.csv")


def load_labels(dataset):
    """{sequence: {frame number (1-based): label}} from the dataset's feature CSVs (no header)."""
    labels = {}
    for name in LABEL_FILES:
        with open(os.path.join(dataset, "features", name), encoding="utf-8") as fp:
            for row in csv.reader(fp):
                if row:
                    labels.setdefault(row[0], {})[int(row[1])] = int(row[2])
    return labels


class LegacyEngine:
    """Per-frame fallen IDs from fall_logic.LegacyFallLogic, checked against the recorded original."""

    name = "legacy"

    def __init__(self, header):
        self.logic = LegacyFallLogic(angle_threshold=header["angle_threshold"])
        self.mismatches = 0

    def step(self, record):
        boxes = [tuple(b) for b in record["boxes"]]
        landmarks = [None if lms is None else [tuple(lm) for lm in lms] for lms in record["landmarks"]]
        falls, fall_data, _ = self.logic.update(record["now"], boxes, landmarks)
        if (bool(falls) != record["legacy"]["fall_detected"]
                or [int(v) for v in fall_data["fallen_ids"]] != record["legacy"]["fallen_ids"]):
            self.mismatches += 1
        return fall_data["fallen_ids"] if falls else []


ENGINES = {"legacy": LegacyEngine}


def alerts_for(frames, engine):
    """[(frame index 0-based, time s)] of alerts, with the app's 5 s per-ID cooldown."""
    last, out = {}, []
    for record in frames:
        now = record["now"]
        new = [pid for pid in engine.step(record)
               if pid not in last or now - last[pid] > ALERT_COOLDOWN_SECONDS]
        for pid in new:
            last[pid] = now
        out.extend((record["index"], now) for _ in new)   # 앱도 새로 넘어진 사람마다 하나씩 보냄
    return out


def score_sequence(seq, frames, labels, engine):
    alerts = alerts_for(frames, engine)
    lab = labels.get(seq, {})
    row = {"sequence": seq, "kind": "fall" if seq.startswith("fall") else "adl",
           "frames": len(frames), "labeled": len(lab), "alerts": len(alerts),
           "hit": "", "early": 0, "repeats": 0, "delay_fall_s": "", "delay_lying_s": "",
           "false_alarms": 0, "fa_while_lying": 0, "persons_max": max((len(r["boxes"]) for r in frames), default=0),
           "no_pose_frames": sum(1 for r in frames if not any(r["landmarks"]))}
    # 정답이 '바닥에 누움'(1)인 프레임에서 사람을 찾았는지: 상자(YOLO 또는 관절 범위) / 관절
    lying = [r for r in frames if lab.get(r["index"] + 1) == 1]
    row["lying_frames"] = len(lying)
    row["lying_box"] = sum(1 for r in lying if r["boxes"])
    row["lying_pose"] = sum(1 for r in lying if any(r["landmarks"]))
    # 정답은 1부터, 기록의 index 는 0부터
    fall_start = min((f for f, v in lab.items() if v == 0), default=None)
    lying_start = min((f for f, v in lab.items() if v == 1), default=None)
    if row["kind"] == "fall":
        if fall_start is None:
            raise SystemExit(f"[score] {seq}: 정답에 '넘어지는 중'(0) 프레임이 없음")
        start_t = (fall_start - 1) / FPS
        hits = [t for _, t in alerts if t >= start_t - EARLY_TOLERANCE_SECONDS]
        row["early"] = len(alerts) - len(hits)
        row["false_alarms"] = row["early"]
        row["hit"] = bool(hits)
        if hits:
            row["repeats"] = len(hits) - 1
            row["delay_fall_s"] = round(hits[0] - start_t, 2)
            if lying_start is not None:
                row["delay_lying_s"] = round(hits[0] - (lying_start - 1) / FPS, 2)
    else:
        row["false_alarms"] = len(alerts)
        row["fa_while_lying"] = sum(1 for i, _ in alerts if lab.get(i + 1) == 1)
    return row


def summarize(rows, frames_adl):
    falls = [r for r in rows if r["kind"] == "fall"]
    hits = sum(1 for r in falls if r["hit"])
    fa = sum(r["false_alarms"] for r in rows)
    minutes = frames_adl / FPS / 60
    recall = hits / len(falls) if falls else 0.0
    precision = hits / (hits + fa) if hits + fa else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    delays = [r["delay_fall_s"] for r in falls if r["hit"]]
    return {"fall_sequences": len(falls), "hits": hits, "recall": recall,
            "adl_sequences": sum(1 for r in rows if r["kind"] == "adl"),
            "adl_with_alarm": sum(1 for r in rows if r["kind"] == "adl" and r["false_alarms"]),
            "false_alarms": fa, "adl_minutes": minutes,
            "fa_per_min": (sum(r["false_alarms"] for r in rows if r["kind"] == "adl") / minutes) if minutes else 0.0,
            "precision": precision, "f1": f1,
            "median_delay_s": sorted(delays)[len(delays) // 2] if delays else None}


COLUMNS = ("sequence", "kind", "frames", "labeled", "alerts", "hit", "early", "repeats", "delay_fall_s",
           "delay_lying_s", "false_alarms", "fa_while_lying", "persons_max", "no_pose_frames",
           "lying_frames", "lying_box", "lying_pose")


def main():
    parser = argparse.ArgumentParser(description="Score a fall engine on UR Fall pose logs")
    parser.add_argument("--engine", choices=sorted(ENGINES), default="legacy")
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--logs", default=DEFAULT_OUT_DIR)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    labels = load_labels(args.dataset)
    rows, mismatches, frames_adl = [], 0, 0
    for name in sorted(os.listdir(args.logs)):
        if not name.endswith(".jsonl"):
            continue
        seq = name[:-len(".jsonl")]
        header, frames = pose_log.read_log(os.path.join(args.logs, name))
        engine = ENGINES[args.engine](header)
        rows.append(score_sequence(seq, frames, labels, engine))
        mismatches += getattr(engine, "mismatches", 0)
        if seq.startswith("adl"):
            frames_adl += len(frames)
    if not rows:
        raise SystemExit("[score] 기록 파일이 없습니다. 먼저 tools/urfall_record.py 를 실행하세요")
    s = summarize(rows, frames_adl)

    lines = [f"# UR Fall 사건 단위 채점: {args.engine}", "",
             f"- 낙상 시퀀스 {s['fall_sequences']}개 중 알림 {s['hits']}개 → 재현율 {s['recall']:.2f}",
             f"- 일상 시퀀스 {s['adl_sequences']}개 중 오탐이 난 시퀀스 {s['adl_with_alarm']}개, "
             f"일상 영상 {s['adl_minutes']:.1f}분 동안 오탐 {sum(r['false_alarms'] for r in rows if r['kind'] == 'adl')}회 "
             f"({s['fa_per_min']:.2f}회/분)",
             f"- 오탐 합계(낙상 시퀀스의 이른 알림 포함) {s['false_alarms']}회 → 정밀도 {s['precision']:.2f}, F1 {s['f1']:.2f}",
             f"- 감지 지연 중앙값 (넘어지기 시작부터) {s['median_delay_s']} 초",
             f"- 누운 프레임(정답 1)에서 사람을 찾은 비율: 상자 {sum(r['lying_box'] for r in rows)}/{sum(r['lying_frames'] for r in rows)}, "
             f"관절 {sum(r['lying_pose'] for r in rows)}/{sum(r['lying_frames'] for r in rows)}",
             f"- 기록과 다시 돌린 결과가 다른 프레임: {mismatches}" + (" (원본 감지기와 같음)" if mismatches == 0 else " ← 확인 필요"),
             "", "| " + " | ".join(COLUMNS) + " |", "|" + "---|" * len(COLUMNS)]
    lines += ["| " + " | ".join(str(r[c]) for c in COLUMNS) + " |" for r in rows]
    text = "\n".join(lines) + "\n"
    print(text)
    out = os.path.join(args.logs, f"score_{args.engine}")
    with open(out + ".md", "w", encoding="utf-8") as fp:
        fp.write(text)
    with open(out + ".csv", "w", encoding="utf-8", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    print(f"[score] 저장: {out}.md, {out}.csv")


if __name__ == "__main__":
    main()
