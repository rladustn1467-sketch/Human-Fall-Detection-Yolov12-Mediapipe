"""Side-by-side check: the unchanged FallDetector.process_frame vs fall_logic.LegacyFallLogic.

The original class is used as is, except that its two model calls are replaced on the instance
(detect_person returns scripted boxes, analyze_pose returns scripted landmarks and calls the
original calculate_pose_features) and the `time` name inside models.fall_detector is patched
to a fake clock. The model is never loaded (__init__ is skipped) and no file is changed.

Needs the detection venv (models/fall_detector.py imports torch, ultralytics, mediapipe, cv2);
skipped elsewhere.
"""
import unittest
from types import SimpleNamespace
from unittest import mock

from fall_logic.legacy import LegacyFallLogic
from tests.pose_builders import (FAR_BOX, LYING_HEAD_LEFT, STANDING_BACK, STANDING_FRONT, TALL_BOX,
                                 WIDE_BOX, WIDE_BOX_SHIFTED)

try:
    import numpy as np
    from models import fall_detector as fd_mod
    IMPORT_ERROR = None
except Exception as e:  # 감지용 venv가 아니면 건너뜀
    np = fd_mod = None
    IMPORT_ERROR = f"{type(e).__name__}: {e}"


def make_original_detector(angle_threshold):
    """FallDetector with the same attributes __init__ sets, without loading YOLO or MediaPipe models."""
    det = fd_mod.FallDetector.__new__(fd_mod.FallDetector)
    det.person_class_id = 0
    det.confidence = 0.5
    det.mp_pose = fd_mod.mp.solutions.pose  # process_frame은 POSE_CONNECTIONS만 사용 (그리기)
    det.fall_threshold = 0.4
    det.angle_threshold = angle_threshold
    det.prev_poses = []
    det.fall_detected = False
    det.fall_start_time = None
    det.fall_cooldown = 3
    det.fall_types = {"step_and_fall": False, "slip_and_fall": False,
                      "trip_and_fall": False, "stump_and_fall": False}
    det.motion_history = []
    det.next_person_id = 1
    det.person_trackers = {}
    det.fallen_person_ids = set()
    return det


def yolo_like_box(box):
    # detect_person과 같은 방식: box.xyxy[0].cpu().numpy().astype(int) 를 풀어서 만든 튜플
    x1, y1, x2, y2 = np.array(box, dtype=np.float32).astype(int)
    return (x1, y1, x2, y2)


def run_side_by_side(script, angle_threshold=45):
    """script: [(now, [box, ...], [landmarks or None, ...]), ...]. Returns per-frame (original, module)."""
    det = make_original_detector(angle_threshold)
    logic = LegacyFallLogic(angle_threshold=angle_threshold)
    clock = {"now": 0.0}
    pending = {"boxes": [], "poses": []}
    captured = []

    def detect_person(frame):
        return pending["boxes"]

    def analyze_pose(frame, person_box):
        landmarks = pending["poses"].pop(0)
        result = (None, None) if landmarks is None else (landmarks, det.calculate_pose_features(landmarks))
        captured.append(result[1])
        return result

    det.detect_person = detect_person
    det.analyze_pose = analyze_pose
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    results = []
    with mock.patch.object(fd_mod, "time", SimpleNamespace(time=lambda: clock["now"])), \
            np.errstate(divide="ignore", invalid="ignore"):
        for now, boxes, poses in script:
            clock["now"] = now
            pending["boxes"] = [yolo_like_box(b) for b in boxes]
            pending["poses"] = list(poses)
            captured.clear()
            _, original_detected, original_data = det.process_frame(frame)
            original = (original_detected, plain_fall_data(original_data), list(captured))
            module_detected, module_data, module_features = logic.update(now, [tuple(b) for b in boxes], list(poses))
            module = (module_detected, plain_fall_data(module_data), module_features)
            results.append((original, module))
    return results, det, logic


def plain_fall_data(fall_data):
    data = dict(fall_data)
    data["person_boxes"] = [[int(v) for v in box] for box in fall_data["person_boxes"]]
    data["person_ids"] = [int(v) for v in fall_data["person_ids"]]
    data["fallen_ids"] = [int(v) for v in fall_data["fallen_ids"]]
    return data


# 여러 상황을 한 흐름으로: 낙상, 중복, 재낙상(놓침), 관절 없음, 두 사람, 만료, 같은 ID 공유, 넓이 0 박스
SCRIPT = [
    (0.0, [WIDE_BOX], [LYING_HEAD_LEFT]),
    (0.1, [WIDE_BOX], [LYING_HEAD_LEFT]),
    (0.2, [WIDE_BOX], [STANDING_FRONT]),
    (0.3, [WIDE_BOX], [LYING_HEAD_LEFT]),
    (0.4, [WIDE_BOX, FAR_BOX], [LYING_HEAD_LEFT, None]),
    (1.0, [], []),
    (5.3, [], []),
    (5.5, [], []),
    (6.0, [WIDE_BOX], [LYING_HEAD_LEFT]),
    (6.1, [WIDE_BOX, WIDE_BOX_SHIFTED], [LYING_HEAD_LEFT, LYING_HEAD_LEFT]),
    (6.2, [TALL_BOX, FAR_BOX], [STANDING_FRONT, LYING_HEAD_LEFT]),
    (6.3, [TALL_BOX, FAR_BOX], [STANDING_BACK, STANDING_FRONT]),
    (6.4, [TALL_BOX, (5, 5, 5, 5)], [STANDING_FRONT, None]),
    (6.5, [TALL_BOX, (5, 5, 5, 5)], [LYING_HEAD_LEFT, None]),
] + [(7.0 + i / 10, [TALL_BOX], [STANDING_FRONT if i % 3 else LYING_HEAD_LEFT]) for i in range(20)]


@unittest.skipIf(fd_mod is None, f"감지용 venv가 아니라 원본 FallDetector를 불러올 수 없음 ({IMPORT_ERROR})")
class ParityTest(unittest.TestCase):
    def assert_same(self, results):
        for index, (original, module) in enumerate(results):
            with self.subTest(frame=index):
                self.assertEqual(module[0], original[0], "falls_detected")
                self.assertEqual(module[1], original[1], "fall_data")
                self.assertEqual(module[2], original[2], "features")

    def test_script_default_threshold(self):
        results, det, logic = run_side_by_side(SCRIPT)
        self.assert_same(results)
        self.assertEqual(logic.fallen_person_ids, det.fallen_person_ids)
        self.assertEqual(logic.tracker.next_person_id, det.next_person_id)
        self.assertEqual(logic.prev_poses, det.prev_poses)
        self.assertEqual(
            {pid: ([int(v) for v in t["box"]], t["last_seen"]) for pid, t in logic.tracker.person_trackers.items()},
            {pid: ([int(v) for v in t["box"]], t["last_seen"]) for pid, t in det.person_trackers.items()})

    def test_script_other_thresholds(self):
        for threshold in (30, 85):
            with self.subTest(angle_threshold=threshold):
                results, _, _ = run_side_by_side(SCRIPT, angle_threshold=threshold)
                self.assert_same(results)

    def test_script_actually_contains_falls(self):
        # 비교가 의미 있도록 낙상 판정이 실제로 일어나는 흐름인지 확인
        results, _, _ = run_side_by_side(SCRIPT)
        self.assertGreaterEqual(sum(original[0] for original, _ in results), 3)


if __name__ == "__main__":
    unittest.main()
