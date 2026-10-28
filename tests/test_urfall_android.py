"""tools/urfall_record_android.py follows the app: same numbers as the Java tests in FrameMathTest."""
import unittest

import numpy as np

from fall_logic.legacy import LegacyFallLogic
from tools import urfall_record_android as ua


def pick(lut):
    return [int(lut[i]) for i in (0, 1, 10, 50, 100, 200, 255)]


def gray_frame(level):
    return np.full((2, 2, 3), level, dtype=np.uint8)


class LowLightTest(unittest.TestCase):
    def test_gamma_table_same_as_java(self):
        # FrameMathTest.gammaCurveMatchesThePc 의 기대값
        self.assertEqual(pick(ua.gamma_table(40.0, np)), [0, 20, 58, 121, 166, 228, 255])
        self.assertEqual(pick(ua.gamma_table(70.0, np)), [0, 6, 31, 88, 138, 217, 255])
        self.assertEqual(pick(ua.gamma_table(5.0, np)), [0, 21, 59, 122, 167, 228, 255])
        self.assertIsNone(ua.gamma_table(150.0, np))   # 이미 밝으면 바꾸지 않음

    def test_dark_frame_is_brightened_with_that_table(self):
        out, changed = ua.LowLight(np).process(gray_frame(40))
        self.assertTrue(changed)
        self.assertEqual(int(out[0, 0, 0]), int(ua.gamma_table(40.0, np)[40]))

    def test_hysteresis_same_as_java(self):
        # FrameMathTest.lowLightHysteresis: 40 → 보정, 87 → 계속, 112 → 해제, 87 → 다시 켜지지 않음
        ll = ua.LowLight(np)
        self.assertTrue(ll.process(gray_frame(40))[1])
        self.assertTrue(ll.process(gray_frame(87))[1])
        self.assertFalse(ll.process(gray_frame(112))[1])
        self.assertFalse(ll.process(gray_frame(87))[1])


class PoseBridgeTest(unittest.TestCase):
    def test_same_box_and_landmarks_as_java(self):
        # FrameMathTest.poseBridgeMakesBoxAndBoxRelativeLandmarks 와 같은 입력
        p = []
        for i in range(33):
            y = 0.45 if i % 3 == 0 else 0.60 if i % 3 == 1 else 0.52
            p.append([0.25 + 0.5 * i / 32.0, y, 0.0, 1.0])
        for i in (0, 11, 12, 23, 24, 25, 26, 27, 28):
            p[i][1] = 0.5 + 0.02 * (i % 2)
        boxes, landmarks = ua.pose_bridge([[tuple(q) for q in p], []], 640, 480)
        self.assertEqual(boxes, [(128, 208, 512, 296)])
        self.assertAlmostEqual(landmarks[0][0][0], (0.25 * 640 - 128) / (512 - 128.0), places=12)
        self.assertAlmostEqual(landmarks[0][0][1], (0.5 * 480 - 208) / (296 - 208.0), places=12)
        falls, _, _ = LegacyFallLogic().update(0, boxes, landmarks)
        self.assertTrue(falls)

    def test_shrink_like_the_app(self):
        import cv2
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        self.assertIs(ua.shrink(frame, cv2), frame)   # UR Fall 크기는 그대로
        self.assertEqual(ua.shrink(np.zeros((1080, 1920, 3), dtype=np.uint8), cv2).shape[:2], (360, 640))


if __name__ == "__main__":
    unittest.main()
