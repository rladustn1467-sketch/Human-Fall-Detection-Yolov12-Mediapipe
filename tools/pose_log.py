"""Pose log format (JSON Lines) and replay comparison, shared by record_poses.py and replay_compare.py.

A log holds what FallDetector saw and decided, frame by frame, without any image:
  line 1   {"type": "header", "format": "fall-pose-log", "version": 1, "angle_threshold": ..., ...}
  line 2+  {"type": "frame", "index": n, "now": t,
            "boxes": [[x1, y1, x2, y2], ...],                 frame pixels (ints)
            "landmarks": [[[x, y, z, v] x33] | null, ...],     crop-normalized, one per box
            "legacy": {"fall_detected", "fall_type", "person_count",
                       "person_ids", "fallen_ids", "features": [dict | null, ...]}}
Replaying the boxes, landmarks and times through LegacyFallLogic must give the same "legacy" values.
This module only needs the standard library and fall_logic (no cv2, torch or mediapipe).
"""
import json
import math

from fall_logic.legacy import LegacyFallLogic

FORMAT = "fall-pose-log"
VERSION = 1
# 비교하는 fall_data 항목 (person_boxes는 입력 그대로라 따로 비교, critical_points는 항상 빈 목록)
COMPARED_KEYS = ("fall_detected", "fall_type", "person_count", "person_ids", "fallen_ids")


def to_plain(value):
    """JSON round trip: tuples become lists, floats keep their exact value (repr round-trips)."""
    return json.loads(json.dumps(value))


def boxes_to_json(boxes):
    # 원본 박스 좌표는 numpy 정수라 int로 바꿔 저장
    return [[int(v) for v in box] for box in boxes]


def landmarks_to_json(landmarks):
    return None if landmarks is None else [[float(v) for v in lm] for lm in landmarks]


def make_header(**fields):
    header = {"type": "header", "format": FORMAT, "version": VERSION}
    header.update(fields)
    return header


def make_frame(index, now, boxes, landmarks_list, falls_detected, fall_data, features_list):
    return {
        "type": "frame",
        "index": index,
        "now": now,
        "boxes": boxes_to_json(boxes),
        "landmarks": [landmarks_to_json(lms) for lms in landmarks_list],
        "legacy": {
            "fall_detected": bool(falls_detected),
            "fall_type": fall_data["fall_type"],
            "person_count": int(fall_data["person_count"]),
            "person_ids": [int(v) for v in fall_data["person_ids"]],
            "fallen_ids": [int(v) for v in fall_data["fallen_ids"]],
            "features": [None if f is None else to_plain(f) for f in features_list],
        },
    }


def write_line(fp, record):
    fp.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_log(path):
    """Return (header, frames). Raises ValueError for a file that is not a pose log."""
    header, frames = None, []
    with open(path, encoding="utf-8") as fp:
        for number, line in enumerate(fp, 1):
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if number == 1:
                if record.get("type") != "header" or record.get("format") != FORMAT:
                    raise ValueError(f"{path}: 낙상 자세 기록 파일이 아닙니다 (첫 줄 header 없음)")
                if record.get("version") != VERSION:
                    raise ValueError(f"{path}: 지원하지 않는 기록 버전 {record.get('version')}")
                header = record
            elif record.get("type") == "frame":
                frames.append(record)
    if header is None:
        raise ValueError(f"{path}: 빈 파일입니다")
    return header, frames


def same_value(a, b):
    """Exact equality where NaN equals NaN (MediaPipe can, in principle, give NaN values)."""
    if isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b):
        return True
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same_value(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same_value(x, y) for x, y in zip(a, b))
    if isinstance(a, bool) or isinstance(b, bool):
        # True == 1 이 되지 않도록 참/거짓은 종류까지 같아야 함
        return type(a) is type(b) and a == b
    return a == b


def compare_frame(record, falls_detected, fall_data, features):
    """List of differences between a recorded frame and the replayed result (empty if identical)."""
    legacy = record["legacy"]
    replayed = {
        "fall_detected": bool(falls_detected),
        "fall_type": fall_data["fall_type"],
        "person_count": fall_data["person_count"],
        "person_ids": list(fall_data["person_ids"]),
        "fallen_ids": list(fall_data["fallen_ids"]),
    }
    diffs = [f"{key}: 기존 {legacy[key]!r} / 새 모듈 {replayed[key]!r}"
             for key in COMPARED_KEYS if not same_value(legacy[key], replayed[key])]
    if fall_data["fall_detected"] != bool(falls_detected):
        diffs.append("새 모듈의 fall_data['fall_detected']와 반환값이 다름")
    if boxes_to_json(fall_data["person_boxes"]) != record["boxes"]:
        diffs.append("person_boxes가 입력과 다름")
    replayed_features = [None if f is None else to_plain(f) for f in features]
    for i, (old, new) in enumerate(zip(legacy["features"], replayed_features)):
        if same_value(old, new):
            continue
        if old is None or new is None:
            diffs.append(f"사람 {i}번 특징값: 기존 {'없음' if old is None else '있음'} / 새 모듈 {'없음' if new is None else '있음'}")
        else:
            keys = sorted(k for k in set(old) | set(new) if not same_value(old.get(k), new.get(k)))
            diffs.append(f"사람 {i}번 특징값 다름: {', '.join(keys)}")
    if len(legacy["features"]) != len(replayed_features):
        diffs.append(f"특징값 개수: 기존 {len(legacy['features'])} / 새 모듈 {len(replayed_features)}")
    return diffs


def replay(header, frames):
    """Run the frames through a fresh LegacyFallLogic and compare.

    Returns a dict: frames, mismatches [(index, [diff, ...]), ...], legacy_fall_frames, module_fall_frames.
    """
    logic = LegacyFallLogic(angle_threshold=header["angle_threshold"])
    mismatches = []
    legacy_falls = module_falls = 0
    for record in frames:
        boxes = [tuple(box) for box in record["boxes"]]
        landmarks = [None if lms is None else [tuple(lm) for lm in lms] for lms in record["landmarks"]]
        falls_detected, fall_data, features = logic.update(record["now"], boxes, landmarks)
        legacy_falls += bool(record["legacy"]["fall_detected"])
        module_falls += bool(falls_detected)
        diffs = compare_frame(record, falls_detected, fall_data, features)
        if diffs:
            mismatches.append((record["index"], diffs))
    return {"frames": len(frames), "mismatches": mismatches,
            "legacy_fall_frames": legacy_falls, "module_fall_frames": module_falls}
