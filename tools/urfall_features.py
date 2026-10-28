"""Per-frame fall features for UR Fall pose logs, as a CSV (stage 2 of docs/rules_from_papers.md planning).

Input: the pose logs made by tools/urfall_record.py (PC: YOLO + MediaPipe) or tools/urfall_record_android.py
(Android: MediaPipe only). Nothing is run on the images again: boxes and landmarks come from the logs.
Every landmark is turned back into frame pixels (x1 + x * box width, y1 + y * box height), so the features
are measured in the picture itself, not in box-relative fractions (the legacy rule's distortion).
A joint counts only when its visibility is at least 0.5; a feature that needs a missing joint is left empty.

One CSV row per frame and person. A frame with nobody found still gets one row (person_count 0, features
empty), so time without a person can be counted.

Columns (angles in degrees, lengths in pixels, "torso" = shoulder midpoint to hip midpoint distance):
  pipeline, sequence, kind, frame (1-based, = dataset label frame), time_s, label (-1/0/1, empty when the
  dataset has no label for the frame), person_count, person, main (1 = the person with the largest joint extent
  in that frame), key_visible (visible joints among nose, shoulders, hips, knees, ankles: 0..9),
  torso_px, box_w, box_h,
  A1_body_angle_shoulder    line shoulder mid -> ankle mid vs horizontal, 0 = lying flat, 90 = upright (Ali p.95)
  A2_body_angle_head        line nose -> ankle mid vs horizontal (Chen p.8)
  B1_box_ratio              person box width / height (PC: YOLO box, Android: joint extent + 10 %) (Chen p.9, Omobot p.5)
  B2_joint_ratio            width / height of the visible joints' extent (same definition in both pipelines)
  C1_descent_025            downward speed of the hip midpoint over 0.25 s, in torso lengths per second (Chen p.7)
  C2_descent_050            the same over 0.5 s
  E1_torso_leg_angle        angle at the hip between hip->shoulder and hip->knee, 180 = straight (Mali p.3;
                            the paper does not say which of the two angle conventions it uses)
  E2_torso_ratio            torso now / torso in the first second of the sequence (Mali p.2-3 "height ratio")
  E3_shoulder_above_ankle   (ankle mid y - shoulder mid y) / torso, how far the shoulders are above the feet (Omobot p.5)
  E3_hip_above_ankle        (ankle mid y - hip mid y) / torso (Omobot p.5)
  E4_motion                 mean movement of the visible key joints since the previous frame, torso lengths per second
                            (ElderFallGuard p.5 "motion drop"; the paper gives no formula)
  H1_head_drop              (nose y now - nose y when standing) / standing height: 0 = as high as when standing,
                            about 1 = the head came down by a whole body height (Mali p.3, Ali p.94 "head-floor distance")
  H2_hip_drop               the same for the hip midpoint
  H3_head_above_ankle       (ankle mid y - nose y) / torso, joints of this frame only (no standing reference):
                            about 2-3 when standing or sitting upright, about 0 when the head is at foot level
                            (head-floor idea of Mali p.3 / Ali p.94, measured like Omobot's E3 p.5)
The standing reference (H1, H2) is taken from the video only, not from the dataset labels: the main person's
"upright" frames (A1 >= 70 deg, torso-leg angle E1 >= 150 deg so that sitting is left out, nose, hip and an ankle
visible) within the first 3 seconds after the person first appears; at least 5 such frames, medians of nose y,
hip y and standing height (ankle mid y - nose y). If there are fewer, the first 15 upright frames anywhere in the
sequence are used ("fallback"); with none at all, H1 and H2 stay empty. Because the camera does not move, the same
place on the floor keeps the same y; walking towards or away from the camera does move y a little (a known limit).
Speeds and motion use the main person of both frames (UR Fall has one real person; the Android pipeline
sometimes adds a phantom second one, which "main" leaves out) and the torso of the earlier frame.
The stand-up check (D) is a rule over time and is computed from these columns in a later stage, not here.

Also writes a per-sequence summary (empty cells, frames without a person, by label) and a few check
pictures with the joints and values drawn on the dataset frame.

Usage (from the project root, inside the detection venv):
  venv\\Scripts\\python.exe tools\\urfall_features.py --pipeline android
  venv\\Scripts\\python.exe tools\\urfall_features.py --pipeline pc
Output: eval_output/urfall_features/features_<pipeline>.csv, summary_<pipeline>.md, check_<pipeline>/*.png
"""
import argparse
import csv
import math
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tools import pose_log  # noqa: E402
from tools.urfall_record import DEFAULT_DATASET, FPS  # noqa: E402
from tools.urfall_score import load_labels  # noqa: E402

LOG_DIRS = {"pc": os.path.join(ROOT, "eval_output", "urfall"),
            "android": os.path.join(ROOT, "eval_output", "urfall_android")}
OUT_DIR = os.path.join(ROOT, "eval_output", "urfall_features")

VIS_MIN = 0.5                       # 이보다 흐린 관절은 쓰지 않음
NOSE, L_SH, R_SH, L_HIP, R_HIP, L_KNEE, R_KNEE, L_ANK, R_ANK = 0, 11, 12, 23, 24, 25, 26, 27, 28
KEY = (NOSE, L_SH, R_SH, L_HIP, R_HIP, L_KNEE, R_KNEE, L_ANK, R_ANK)
MIN_JOINTS_FOR_EXTENT = 5           # B2 를 계산하려면 보이는 관절이 이만큼은 있어야 함
REFERENCE_SECONDS = 1.0             # E2 의 기준 몸통 길이: 시퀀스 첫 1초의 중앙값
DESCENT_WINDOWS = (("C1_descent_025", 0.25), ("C2_descent_050", 0.5))
# 서 있을 때 기준 (H1, H2): 영상에서만 잡음 (정답 표시는 쓰지 않음)
UPRIGHT_MIN_BODY_ANGLE = 70.0       # 몸 선이 거의 세로
UPRIGHT_MIN_TORSO_LEG = 150.0       # 다리가 펴짐 (의자에 앉은 경우를 뺌)
STANDING_WINDOW_SECONDS = 3.0       # 사람이 처음 보인 뒤 이 시간 안의 서 있는 프레임
STANDING_MIN_FRAMES = 5
STANDING_FALLBACK_FRAMES = 15       # 앞부분에 부족하면 영상 전체에서 처음 나오는 서 있는 프레임 이만큼

COLUMNS = ("pipeline", "sequence", "kind", "frame", "time_s", "label", "person_count", "person", "main",
           "key_visible", "torso_px", "box_w", "box_h",
           "A1_body_angle_shoulder", "A2_body_angle_head", "B1_box_ratio", "B2_joint_ratio",
           "C1_descent_025", "C2_descent_050",
           "E1_torso_leg_angle", "E2_torso_ratio", "E3_shoulder_above_ankle", "E3_hip_above_ankle", "E4_motion",
           "H1_head_drop", "H2_hip_drop", "H3_head_above_ankle")
FEATURES = COLUMNS[13:]


# ---- 기하 계산 (순수 파이썬, 단위 시험 대상) ----

def to_pixels(box, landmarks):
    """Box-relative landmarks -> [(x, y, visibility)] in frame pixels (same for both pipelines' logs)."""
    x1, y1, x2, y2 = box
    w, h = x2 - x1, y2 - y1
    return [(x1 + lm[0] * w, y1 + lm[1] * h, lm[3]) for lm in landmarks]


def visible(points, i):
    return points[i][2] >= VIS_MIN


def midpoint(points, a, b):
    """Midpoint of the visible ones of joints a and b (one visible: that joint; none: None)."""
    seen = [points[i] for i in (a, b) if visible(points, i)]
    if not seen:
        return None
    return (sum(p[0] for p in seen) / len(seen), sum(p[1] for p in seen) / len(seen))


def line_angle(p, q):
    """Angle of the line p-q against the horizontal, 0..90 degrees (direction does not matter)."""
    if p is None or q is None:
        return None
    dx, dy = abs(q[0] - p[0]), abs(q[1] - p[1])
    if dx == 0 and dy == 0:
        return None
    return math.degrees(math.atan2(dy, dx))


def angle_at(vertex, a, b):
    """Angle a-vertex-b in degrees (0..180)."""
    if vertex is None or a is None or b is None:
        return None
    v1 = (a[0] - vertex[0], a[1] - vertex[1])
    v2 = (b[0] - vertex[0], b[1] - vertex[1])
    n1, n2 = math.hypot(*v1), math.hypot(*v2)
    if n1 == 0 or n2 == 0:
        return None
    c = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)))
    return math.degrees(math.acos(c))


def distance(p, q):
    return None if p is None or q is None else math.hypot(q[0] - p[0], q[1] - p[1])


def person_geometry(box, landmarks):
    """Per-person values of one frame (no history needed). Missing parts are None."""
    pts = to_pixels(box, landmarks)
    sh, hip = midpoint(pts, L_SH, R_SH), midpoint(pts, L_HIP, R_HIP)
    knee, ank = midpoint(pts, L_KNEE, R_KNEE), midpoint(pts, L_ANK, R_ANK)
    nose = (pts[NOSE][0], pts[NOSE][1]) if visible(pts, NOSE) else None
    torso = distance(sh, hip)
    if torso is not None and torso < 1.0:
        torso = None                                   # 몸통이 한 점으로 겹침: 잣대로 쓸 수 없음
    vis_all = [(p[0], p[1]) for p in pts if p[2] >= VIS_MIN]
    extent = None
    if len(vis_all) >= MIN_JOINTS_FOR_EXTENT:
        xs, ys = [p[0] for p in vis_all], [p[1] for p in vis_all]
        extent = (max(xs) - min(xs), max(ys) - min(ys))
    bw, bh = box[2] - box[0], box[3] - box[1]
    g = {
        "key_visible": sum(1 for i in KEY if visible(pts, i)),
        "torso_px": torso, "box_w": bw, "box_h": bh,
        "A1_body_angle_shoulder": line_angle(sh, ank),
        "A2_body_angle_head": line_angle(nose, ank),
        "B1_box_ratio": bw / bh if bh > 0 else None,
        "B2_joint_ratio": extent[0] / extent[1] if extent and extent[1] > 0 else None,
        "E1_torso_leg_angle": angle_at(hip, sh, knee),
        "E3_shoulder_above_ankle": (ank[1] - sh[1]) / torso if ank and sh and torso else None,
        "E3_hip_above_ankle": (ank[1] - hip[1]) / torso if ank and hip and torso else None,
        "H3_head_above_ankle": (ank[1] - nose[1]) / torso if ank and nose and torso else None,
    }
    # 시간에 걸친 계산에 쓰는 값 (CSV 칸 아님)
    g["_hip"], g["_nose"], g["_ankle"] = hip, nose, ank
    g["_key_points"] = {i: (pts[i][0], pts[i][1]) for i in KEY if visible(pts, i)}
    g["_extent_area"] = extent[0] * extent[1] if extent else 0.0
    return g


def descent_speed(hip_now, hip_before, torso_before, dt):
    """Downward speed of the hip midpoint in torso lengths per second (image y grows downward)."""
    if hip_now is None or hip_before is None or not torso_before or dt <= 0:
        return None
    return (hip_now[1] - hip_before[1]) / torso_before / dt


def is_upright(g):
    """Standing frame for the reference: body line near vertical, legs straight, nose, hip and an ankle visible."""
    a, e = g["A1_body_angle_shoulder"], g["E1_torso_leg_angle"]
    return (a is not None and a >= UPRIGHT_MIN_BODY_ANGLE and e is not None and e >= UPRIGHT_MIN_TORSO_LEG
            and g["_nose"] is not None and g["_hip"] is not None and g["_ankle"] is not None)


def standing_reference(main_geo, times):
    """(reference dict or None). main_geo: the main person's geometry per frame (None = nobody), times in s."""
    first = next((t for g, t in zip(main_geo, times) if g is not None), None)
    if first is None:
        return None
    upright = [(k, g) for k, g in enumerate(main_geo) if g is not None and is_upright(g)]
    chosen = [(k, g) for k, g in upright if times[k] - first <= STANDING_WINDOW_SECONDS]
    source = "start"
    if len(chosen) < STANDING_MIN_FRAMES:
        chosen, source = upright[:STANDING_FALLBACK_FRAMES], "fallback"
    if not chosen:
        return None
    nose_y = statistics.median(g["_nose"][1] for _, g in chosen)
    hip_y = statistics.median(g["_hip"][1] for _, g in chosen)
    height = statistics.median(g["_ankle"][1] - g["_nose"][1] for _, g in chosen)
    if height <= 0:
        return None
    return {"source": source, "frames": [k + 1 for k, _ in chosen], "nose_y": nose_y, "hip_y": hip_y,
            "height": height}


def drop(point, ref_y, height):
    """How far a point came down since standing, in standing heights (image y grows downward)."""
    return None if point is None else (point[1] - ref_y) / height


def motion(points_now, points_before, torso_before, dt):
    """Mean movement of the key joints visible in both frames, in torso lengths per second."""
    if not points_now or not points_before or not torso_before or dt <= 0:
        return None
    common = [i for i in points_now if i in points_before]
    if not common:
        return None
    moved = statistics.fmean(distance(points_now[i], points_before[i]) for i in common)
    return moved / torso_before / dt


# ---- 시퀀스 처리 ----

def sequence_rows(pipeline, seq, frames, labels, references=None):
    """CSV rows for one sequence (list of dicts). references: optional dict, filled with this sequence's
    standing reference (for the summary)."""
    kind = "fall" if seq.startswith("fall") else "adl"
    lab = labels.get(seq, {})
    per_frame = []            # 프레임마다 [(person index, geometry)]
    for r in frames:
        people = []
        for i, (box, lms) in enumerate(zip(r["boxes"], r["landmarks"])):
            if lms:
                people.append((i, person_geometry(box, lms)))
        per_frame.append(people)
    main = [max(p, key=lambda x: x[1]["_extent_area"])[0] if p else None for p in per_frame]
    main_geo = [dict(p)[m] if m is not None else None for p, m in zip(per_frame, main)]

    torsos = [g["torso_px"] for g, r in zip(main_geo, frames) if g and g["torso_px"] and r["now"] < REFERENCE_SECONDS]
    reference_torso = statistics.median(torsos) if torsos else None
    standing = standing_reference(main_geo, [r["now"] for r in frames])
    if references is not None:
        references[seq] = standing

    rows = []
    for k, (r, people) in enumerate(zip(frames, per_frame)):
        frame_no = r["index"] + 1
        base = {"pipeline": pipeline, "sequence": seq, "kind": kind, "frame": frame_no,
                "time_s": round(r["now"], 4), "label": lab.get(frame_no, ""),
                "person_count": len(r["boxes"])}
        if not people:
            rows.append({**base, "person": "", "main": "", **{c: "" for c in COLUMNS[9:]}})
            continue
        for idx, g in people:
            row = {**base, "person": idx, "main": int(idx == main[k])}
            for c in ("key_visible", "torso_px", "box_w", "box_h", "A1_body_angle_shoulder", "A2_body_angle_head",
                      "B1_box_ratio", "B2_joint_ratio", "E1_torso_leg_angle", "E3_shoulder_above_ankle",
                      "E3_hip_above_ankle", "H3_head_above_ankle"):
                row[c] = g[c]
            row["E2_torso_ratio"] = (g["torso_px"] / reference_torso
                                     if g["torso_px"] and reference_torso else None)
            if standing:
                row["H1_head_drop"] = drop(g["_nose"], standing["nose_y"], standing["height"])
                row["H2_hip_drop"] = drop(g["_hip"], standing["hip_y"], standing["height"])
            # 시간 특징은 주 인물만 (이전 프레임의 주 인물과 비교)
            for col, seconds in DESCENT_WINDOWS:
                back = round(seconds * FPS)
                prev = main_geo[k - back] if idx == main[k] and k - back >= 0 else None
                row[col] = (descent_speed(g["_hip"], prev["_hip"], prev["torso_px"], back / FPS)
                            if prev else None)
            prev1 = main_geo[k - 1] if idx == main[k] and k >= 1 else None
            row["E4_motion"] = motion(g["_key_points"], prev1["_key_points"], prev1["torso_px"], 1 / FPS) if prev1 else None
            rows.append({c: ("" if row.get(c) is None else row[c]) for c in COLUMNS})
    return rows


def fmt(v):
    return f"{v:.4f}" if isinstance(v, float) else v


def summarize(rows):
    """Markdown summary: rows vs frames, frames without a person, empty feature cells of the main person."""
    by_seq = {}
    for r in rows:
        by_seq.setdefault(r["sequence"], []).append(r)
    lines = ["| 시퀀스 | 프레임 | 줄 | 사람 없음 | 주 인물 있음 | " + " | ".join(f"{f} 빈칸" for f in ("A1", "B2", "C1", "E4", "H3")) + " |",
             "|" + "---|" * 10]
    for seq, rs in sorted(by_seq.items()):
        frames = {r["frame"] for r in rs}
        mains = [r for r in rs if r["main"] == 1]
        nobody = sum(1 for r in rs if r["person_count"] == 0 or r["person"] == "")
        empty = [sum(1 for r in mains if r[c] == "") for c in
                 ("A1_body_angle_shoulder", "B2_joint_ratio", "C1_descent_025", "E4_motion", "H3_head_above_ankle")]
        lines.append(f"| {seq} | {len(frames)} | {len(rs)} | {nobody} | {len(mains)} | " + " | ".join(map(str, empty)) + " |")

    lines += ["", "정답 상태별 (주 인물 기준, 비율 = 값이 있는 프레임 / 그 상태의 전체 프레임)", "",
              "| 상태 | 프레임 | 주 인물 있음 | " + " | ".join(f"{f} 있음" for f in FEATURES) + " |",
              "|" + "---|" * (3 + len(FEATURES))]
    for state, name in (("-1", "-1 누워 있지 않음"), ("0", "0 넘어지는 중"), ("1", "1 바닥에 누움"), ("", "정답 없음")):
        frames = {(r["sequence"], r["frame"]) for r in rows if str(r["label"]) == state}
        if not frames:
            continue
        mains = [r for r in rows if str(r["label"]) == state and r["main"] == 1]
        cells = [f"{sum(1 for r in mains if r[f] != '')} ({100 * sum(1 for r in mains if r[f] != '') / len(frames):.0f}%)"
                 for f in FEATURES]
        lines.append(f"| {name} | {len(frames)} | {len(mains)} ({100 * len(mains) / len(frames):.0f}%) | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def reference_table(references):
    lines = ["서 있을 때 기준 (H1 머리 하강, H2 엉덩이 하강). start = 처음 보인 뒤 "
             f"{STANDING_WINDOW_SECONDS:g}초 안의 서 있는 프레임, fallback = 영상 전체에서 처음 나오는 서 있는 프레임 "
             f"{STANDING_FALLBACK_FRAMES}개, 없음 = H1·H2 빈칸", "",
             "| 시퀀스 | 방법 | 사용한 프레임 수 | 프레임 범위 | 머리 y | 엉덩이 y | 키(머리~발목, px) |", "|" + "---|" * 7]
    for seq, ref in sorted(references.items()):
        if not ref:
            lines.append(f"| {seq} | 없음 | 0 | | | | |")
            continue
        f = ref["frames"]
        lines.append(f"| {seq} | {ref['source']} | {len(f)} | {f[0]}~{f[-1]} | {ref['nose_y']:.0f} | "
                     f"{ref['hip_y']:.0f} | {ref['height']:.0f} |")
    return "\n".join(lines) + "\n"


# ---- 확인용 그림 ----
CHECK_SEQUENCES = ("fall-02", "fall-06", "adl-04", "adl-30")


def draw_checks(pipeline, rows, logs, dataset, out_dir):
    """For a few sequences: one frame per label state with the main person's joints and A1/B1/C1 drawn on it."""
    import cv2
    os.makedirs(out_dir, exist_ok=True)
    written = []
    for seq in CHECK_SEQUENCES:
        if seq not in logs:
            continue
        header, frames = logs[seq]
        for state in ("-1", "0", "1"):
            cand = [r for r in rows if r["sequence"] == seq and str(r["label"]) == state and r["main"] == 1
                    and r["A1_body_angle_shoulder"] != ""]
            if not cand:
                continue
            r = cand[len(cand) // 2]
            rec = frames[r["frame"] - 1]
            box, lms = rec["boxes"][r["person"]], rec["landmarks"][r["person"]]
            pts = to_pixels(box, lms)
            path = os.path.join(dataset, "rgb", f"{seq}-cam0-rgb", f"{seq}-cam0-rgb-{r['frame']:03d}.png")
            img = cv2.imread(path)
            if img is None:
                continue
            cv2.rectangle(img, (int(box[0]), int(box[1])), (int(box[2]), int(box[3])), (255, 200, 0), 1)
            for i in KEY:
                if pts[i][2] >= VIS_MIN:
                    cv2.circle(img, (int(pts[i][0]), int(pts[i][1])), 4, (0, 255, 0), -1)
            sh, ank = midpoint(pts, L_SH, R_SH), midpoint(pts, L_ANK, R_ANK)
            if sh and ank:
                cv2.line(img, (int(sh[0]), int(sh[1])), (int(ank[0]), int(ank[1])), (0, 0, 255), 2)
            text = [f"{seq} frame {r['frame']} label {state}",
                    f"A1 {float(r['A1_body_angle_shoulder']):.0f} deg",
                    f"B1 {float(r['B1_box_ratio']):.2f}  B2 " + (f"{float(r['B2_joint_ratio']):.2f}" if r['B2_joint_ratio'] != '' else '-'),
                    "C1 " + (f"{float(r['C1_descent_025']):.2f}" if r['C1_descent_025'] != '' else '-') + " torso/s"]
            for n, t in enumerate(text):
                cv2.putText(img, t, (8, 22 + 22 * n), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 3)
                cv2.putText(img, t, (8, 22 + 22 * n), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
            name = os.path.join(out_dir, f"{seq}_label{state}_f{r['frame']:03d}.png")
            cv2.imwrite(name, img)
            written.append(name)
    return written


def main():
    parser = argparse.ArgumentParser(description="Per-frame fall features CSV from UR Fall pose logs")
    parser.add_argument("--pipeline", choices=sorted(LOG_DIRS), default="android")
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--no-pictures", action="store_true")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    labels = load_labels(args.dataset)
    log_dir = LOG_DIRS[args.pipeline]
    logs, rows, references = {}, [], {}
    for name in sorted(os.listdir(log_dir)):
        if name.endswith(".jsonl"):
            seq = name[:-len(".jsonl")]
            logs[seq] = pose_log.read_log(os.path.join(log_dir, name))
            rows += sequence_rows(args.pipeline, seq, logs[seq][1], labels, references)
    if not rows:
        raise SystemExit(f"[features] {log_dir} 에 기록이 없습니다")

    os.makedirs(OUT_DIR, exist_ok=True)
    out_csv = os.path.join(OUT_DIR, f"features_{args.pipeline}.csv")
    with open(out_csv, "w", encoding="utf-8", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({c: fmt(r[c]) for c in COLUMNS})
    summary = (f"# 특징 CSV 요약: {args.pipeline}\n\n- CSV: {out_csv}\n- 시퀀스 {len(logs)}개, 줄 {len(rows)}개, "
               f"프레임 {sum(len(f) for _, f in logs.values())}개\n- 관절 신뢰도 기준 {VIS_MIN}, 시간 특징은 주 인물만\n\n"
               + summarize(rows) + "\n" + reference_table(references))
    out_md = os.path.join(OUT_DIR, f"summary_{args.pipeline}.md")
    with open(out_md, "w", encoding="utf-8") as fp:
        fp.write(summary)
    print(summary)
    if not args.no_pictures:
        pics = draw_checks(args.pipeline, rows, logs, args.dataset, os.path.join(OUT_DIR, f"check_{args.pipeline}"))
        print(f"[features] 확인용 그림 {len(pics)}장: {os.path.join(OUT_DIR, f'check_{args.pipeline}')}")
    print(f"[features] 저장: {out_csv}, {out_md}")


if __name__ == "__main__":
    main()
