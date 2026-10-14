"""Legacy features and posture rule: expected values worked out from the formulas in
FallDetector.calculate_pose_features / process_frame (models/fall_detector.py), not new thresholds."""
import unittest

from fall_logic.features import compute_legacy_features
from fall_logic.rules import is_legacy_fall_posture
from tests.pose_builders import LYING_HEAD_LEFT, STANDING_BACK, STANDING_FRONT, make_landmarks


class StandingFrontTest(unittest.TestCase):
    """Facing the camera: the aspect-ratio width is negative and replaced by 0.0001 (known issue P3)."""

    def setUp(self):
        self.history = []
        self.f = compute_legacy_features(STANDING_FRONT, self.history, now=12.5)

    def test_angle_is_vertical(self):
        self.assertEqual(self.f["angle"], 0.0)

    def test_negative_width_is_clamped(self):
        # 폭 = max(x12, x24, x26, x28) - min(x11, x23, x25, x27) = 0.4375 - 0.5625 = -0.125 -> 0.0001
        self.assertEqual(self.f["aspect_ratio"], 0.75 / 0.0001)

    def test_other_values(self):
        self.assertEqual(self.f["height"], 0.75)
        self.assertEqual((self.f["mid_shoulder_x"], self.f["mid_shoulder_y"]), (0.5, 0.25))
        self.assertEqual((self.f["mid_hip_x"], self.f["mid_hip_y"]), (0.5, 0.5))
        self.assertEqual(self.f["shoulder_pos"], (0.5, 0.25))
        self.assertEqual(self.f["hip_pos"], (0.5, 0.5))
        self.assertEqual(self.f["feet_pos"], (0.5, 0.875))
        self.assertEqual(self.f["shoulder_to_hip_distance"], 0.25)
        self.assertEqual(self.f["hip_to_feet_distance"], 0.375)
        self.assertEqual(self.f["timestamp"], 12.5)

    def test_no_history_means_zero_motion(self):
        for key in ("velocity_y", "velocity_x", "acceleration", "jerk"):
            self.assertEqual(self.f[key], 0)

    def test_appended_to_history(self):
        self.assertEqual(self.history, [self.f])

    def test_not_a_fall(self):
        self.assertFalse(is_legacy_fall_posture(self.f, 45))


class StandingBackTest(unittest.TestCase):
    def test_aspect_ratio_with_positive_width(self):
        f = compute_legacy_features(STANDING_BACK, [], now=0)
        # 폭 0.625 - 0.375 = 0.25, 높이 0.875 - 0.125 = 0.75
        self.assertEqual(f["aspect_ratio"], 3.0)
        self.assertEqual(f["angle"], 0.0)
        self.assertFalse(is_legacy_fall_posture(f, 45))


class LyingTest(unittest.TestCase):
    def setUp(self):
        self.f = compute_legacy_features(LYING_HEAD_LEFT, [], now=0)

    def test_angle_is_horizontal(self):
        # 어깨 중점 (0.25, 0.5) -> 엉덩이 중점 (0.5, 0.5): atan2(0.25, 0) = 90도
        self.assertAlmostEqual(self.f["angle"], 90.0, places=9)

    def test_aspect_ratio(self):
        # 폭 0.875 - 0.25 = 0.625, 높이 0.5625 - 0.4375 = 0.125
        self.assertAlmostEqual(self.f["aspect_ratio"], 0.2, places=12)
        self.assertEqual(self.f["height"], 0.0)

    def test_is_a_fall_with_default_threshold(self):
        self.assertTrue(is_legacy_fall_posture(self.f, 45))

    def test_threshold_changes_the_result(self):
        # 기준 각도는 angle_threshold + 10
        self.assertTrue(is_legacy_fall_posture(self.f, 30))
        self.assertFalse(is_legacy_fall_posture(self.f, 85))


class MotionTest(unittest.TestCase):
    """Velocity/acceleration/jerk per call (time_diff = 1), shoulder midpoint only."""

    def test_velocity_against_previous_pose(self):
        history = []
        compute_legacy_features(STANDING_FRONT, history, now=0)
        f = compute_legacy_features(LYING_HEAD_LEFT, history, now=1)
        self.assertEqual(f["velocity_y"], 0.25)   # 0.5 - 0.25
        self.assertEqual(f["velocity_x"], -0.25)  # 0.25 - 0.5
        self.assertEqual(f["acceleration"], 0)
        self.assertEqual(f["jerk"], 0)

    def test_acceleration_needs_two_previous_poses(self):
        history = []
        for now in (0, 1):
            compute_legacy_features(STANDING_FRONT, history, now)
        f = compute_legacy_features(LYING_HEAD_LEFT, history, now=2)
        self.assertEqual(f["acceleration"], 0.25)
        self.assertEqual(f["jerk"], 0)

    def test_jerk_needs_three_previous_poses(self):
        history = []
        for now in (0, 1, 2):
            compute_legacy_features(STANDING_FRONT, history, now)
        f = compute_legacy_features(LYING_HEAD_LEFT, history, now=3)
        self.assertEqual(f["acceleration"], 0.25)
        self.assertEqual(f["jerk"], 0.25)

    def test_history_is_capped_at_15(self):
        history = []
        for now in range(20):
            compute_legacy_features(STANDING_FRONT, history, now)
        self.assertEqual(len(history), 15)
        self.assertEqual(history[0]["timestamp"], 5)


class MissingLandmarksTest(unittest.TestCase):
    def test_empty_list(self):
        history = []
        self.assertIsNone(compute_legacy_features([], history, now=0))
        self.assertEqual(history, [])

    def test_too_few_landmarks(self):
        # 28번(오른쪽 발목)이 없으면 None (원본의 key_landmarks 개수 확인)
        history = []
        self.assertIsNone(compute_legacy_features(STANDING_FRONT[:28], history, now=0))
        self.assertEqual(history, [])

    def test_visibility_is_ignored(self):
        # 가시성 0인 관절도 그대로 사용 (알려진 문제 P7)
        hidden = make_landmarks({i: lm[:2] for i, lm in enumerate(LYING_HEAD_LEFT)}, visibility=0.0)
        self.assertEqual(compute_legacy_features(hidden, [], now=0)["aspect_ratio"],
                         compute_legacy_features(LYING_HEAD_LEFT, [], now=0)["aspect_ratio"])


class RuleBoundaryTest(unittest.TestCase):
    """abs(angle) >= angle_threshold + 10 and aspect_ratio < 1.5 (defaults: angle 0, aspect 2.0)."""

    def test_angle_boundary(self):
        self.assertTrue(is_legacy_fall_posture({"angle": 55.0, "aspect_ratio": 1.0}, 45))
        self.assertFalse(is_legacy_fall_posture({"angle": 54.999, "aspect_ratio": 1.0}, 45))

    def test_negative_angle_counts(self):
        self.assertTrue(is_legacy_fall_posture({"angle": -60.0, "aspect_ratio": 1.0}, 45))

    def test_upside_down_counts(self):
        self.assertTrue(is_legacy_fall_posture({"angle": 180.0, "aspect_ratio": 1.0}, 45))

    def test_aspect_boundary(self):
        self.assertFalse(is_legacy_fall_posture({"angle": 90.0, "aspect_ratio": 1.5}, 45))
        self.assertTrue(is_legacy_fall_posture({"angle": 90.0, "aspect_ratio": 1.4999}, 45))

    def test_negative_aspect_counts(self):
        # 발목이 머리보다 위에 있으면 높이가 음수 -> 1.5 미만
        self.assertTrue(is_legacy_fall_posture({"angle": 90.0, "aspect_ratio": -0.5}, 45))

    def test_missing_keys_use_original_defaults(self):
        self.assertFalse(is_legacy_fall_posture({"aspect_ratio": 0.1}, 45))  # angle 기본 0
        self.assertFalse(is_legacy_fall_posture({"angle": 90.0}, 45))         # aspect 기본 2.0


if __name__ == "__main__":
    unittest.main()
