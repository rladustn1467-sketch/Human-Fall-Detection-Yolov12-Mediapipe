"""Pose log round trip and replay comparison (tools/pose_log.py), without any model or video."""
import json
import math
import os
import tempfile
import unittest

from fall_logic.legacy import LegacyFallLogic
from tests.pose_builders import FAR_BOX, LYING_HEAD_LEFT, STANDING_FRONT, TALL_BOX, WIDE_BOX
from tools import pose_log

# 원본 기록 대신, 같은 흐름을 LegacyFallLogic으로 만들어 기록 형식과 비교 기능만 확인
FRAMES = [
    (0.0, [WIDE_BOX], [STANDING_FRONT]),
    (0.033, [WIDE_BOX], [LYING_HEAD_LEFT]),
    (0.066, [WIDE_BOX, FAR_BOX], [LYING_HEAD_LEFT, None]),
    (0.1, [TALL_BOX], [STANDING_FRONT]),
]


def build_log(path, angle_threshold=45):
    logic = LegacyFallLogic(angle_threshold=angle_threshold)
    with open(path, "w", encoding="utf-8") as fp:
        pose_log.write_line(fp, pose_log.make_header(source="synthetic", angle_threshold=angle_threshold, clock="video"))
        for index, (now, boxes, poses) in enumerate(FRAMES):
            detected, data, features = logic.update(now, boxes, poses)
            pose_log.write_line(fp, pose_log.make_frame(index, now, boxes, poses, detected, data, features))


class PoseLogTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "poses.jsonl")
        build_log(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def rewrite_frame(self, index, change):
        with open(self.path, encoding="utf-8") as fp:
            lines = fp.read().splitlines()
        record = json.loads(lines[index + 1])
        change(record)
        lines[index + 1] = json.dumps(record)
        with open(self.path, "w", encoding="utf-8") as fp:
            fp.write("\n".join(lines) + "\n")

    def test_round_trip_replays_identically(self):
        header, frames = pose_log.read_log(self.path)
        self.assertEqual(header["angle_threshold"], 45)
        self.assertEqual(len(frames), len(FRAMES))
        result = pose_log.replay(header, frames)
        self.assertEqual(result["mismatches"], [])
        self.assertEqual(result["legacy_fall_frames"], 1)
        self.assertEqual(result["module_fall_frames"], 1)

    def test_changed_decision_is_reported(self):
        self.rewrite_frame(1, lambda r: r["legacy"].update(fallen_ids=[], fall_detected=False))
        result = pose_log.replay(*pose_log.read_log(self.path))
        self.assertEqual([index for index, _ in result["mismatches"]], [1])
        self.assertTrue(any("fallen_ids" in d for d in result["mismatches"][0][1]))

    def test_changed_feature_is_reported(self):
        self.rewrite_frame(0, lambda r: r["legacy"]["features"][0].update(angle=1.0))
        result = pose_log.replay(*pose_log.read_log(self.path))
        self.assertEqual(len(result["mismatches"]), 1)
        self.assertIn("angle", result["mismatches"][0][1][0])

    def test_missing_pose_is_kept_as_null(self):
        _, frames = pose_log.read_log(self.path)
        self.assertIsNone(frames[2]["landmarks"][1])
        self.assertIsNone(frames[2]["legacy"]["features"][1])

    def test_not_a_pose_log(self):
        with open(self.path, "w", encoding="utf-8") as fp:
            fp.write('{"type": "frame"}\n')
        with self.assertRaises(ValueError):
            pose_log.read_log(self.path)


class SameValueTest(unittest.TestCase):
    def test_nan_equals_nan(self):
        self.assertTrue(pose_log.same_value({"a": [math.nan]}, {"a": [math.nan]}))

    def test_bool_is_not_int(self):
        self.assertFalse(pose_log.same_value(True, 1))

    def test_int_zero_equals_float_zero(self):
        # 원본 특징값의 속도 기본값은 정수 0
        self.assertTrue(pose_log.same_value(0, 0.0))


if __name__ == "__main__":
    unittest.main()
