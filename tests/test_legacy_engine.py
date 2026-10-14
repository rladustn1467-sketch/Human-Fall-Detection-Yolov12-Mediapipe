"""LegacyFallLogic state handling: tracking, duplicate prevention and fall_data structure,
including the known issues that the legacy mode must keep (P4 re-fall, P5 shared history, P6 duplicate IDs)."""
import math
import unittest

from fall_logic.legacy import LegacyFallLogic
from fall_logic.tracker import LegacyIouTracker
from tests.pose_builders import (FAR_BOX, LYING_HEAD_LEFT, STANDING_FRONT, TALL_BOX, WIDE_BOX,
                                 WIDE_BOX_SHIFTED)

# 원본 process_frame이 돌려주는 fall_data의 키 (대시보드·서버 쪽이 쓰는 구조)
FALL_DATA_KEYS = {"person_count", "fall_detected", "fall_type", "person_boxes",
                  "critical_points", "person_ids", "fallen_ids"}


class FallDataStructureTest(unittest.TestCase):
    def test_first_fall(self):
        logic = LegacyFallLogic()
        detected, data, features = logic.update(0.0, [WIDE_BOX], [LYING_HEAD_LEFT])
        self.assertTrue(detected)
        self.assertEqual(set(data), FALL_DATA_KEYS)
        self.assertEqual(data["person_count"], 1)
        self.assertTrue(data["fall_detected"])
        self.assertEqual(data["fall_type"], "slip_and_fall")  # 원본에서 항상 이 값
        self.assertEqual(data["person_boxes"], [WIDE_BOX])
        self.assertEqual(data["critical_points"], [])
        self.assertEqual(data["person_ids"], [1])
        self.assertEqual(data["fallen_ids"], [1])
        self.assertEqual(len(features), 1)

    def test_no_people(self):
        detected, data, features = LegacyFallLogic().update(0.0, [], [])
        self.assertFalse(detected)
        self.assertEqual(data["person_count"], 0)
        self.assertIsNone(data["fall_type"])
        self.assertEqual((data["person_ids"], data["fallen_ids"], features), ([], [], []))

    def test_mismatched_input_lengths(self):
        with self.assertRaises(ValueError):
            LegacyFallLogic().update(0.0, [WIDE_BOX], [])


class DuplicatePreventionTest(unittest.TestCase):
    def test_same_person_still_lying_is_not_reported_again(self):
        logic = LegacyFallLogic()
        logic.update(0.0, [WIDE_BOX], [LYING_HEAD_LEFT])
        detected, data, _ = logic.update(0.1, [WIDE_BOX], [LYING_HEAD_LEFT])
        self.assertFalse(detected)
        self.assertEqual(data["person_ids"], [1])
        self.assertEqual(data["fallen_ids"], [])
        self.assertIsNone(data["fall_type"])

    def test_refall_while_visible_is_missed(self):
        # 알려진 문제 P4: 일어났다가 다시 누워도 같은 ID는 다시 판정하지 않음
        logic = LegacyFallLogic()
        logic.update(0.0, [WIDE_BOX], [LYING_HEAD_LEFT])
        logic.update(0.2, [WIDE_BOX], [STANDING_FRONT])
        detected, _, _ = logic.update(0.4, [WIDE_BOX], [LYING_HEAD_LEFT])
        self.assertFalse(detected)
        self.assertEqual(logic.fallen_person_ids, {1})

    def test_returning_before_expiry_keeps_the_id(self):
        logic = LegacyFallLogic()
        logic.update(0.0, [WIDE_BOX], [LYING_HEAD_LEFT])
        detected, data, _ = logic.update(4.9, [WIDE_BOX], [LYING_HEAD_LEFT])
        self.assertFalse(detected)
        self.assertEqual(data["person_ids"], [1])


class ExpiryTest(unittest.TestCase):
    """A tracker unseen for more than 5 s is removed, and its ID leaves the fallen set."""

    def setUp(self):
        self.logic = LegacyFallLogic()
        self.logic.update(0.0, [WIDE_BOX], [LYING_HEAD_LEFT])
        self.logic.update(1.0, [], [])

    def test_exactly_five_seconds_is_kept(self):
        self.logic.update(5.0, [], [])
        self.assertEqual(self.logic.fallen_person_ids, {1})
        self.assertIn(1, self.logic.tracker.person_trackers)

    def test_after_five_seconds_a_new_fall_gets_a_new_id(self):
        self.logic.update(5.5, [], [])
        self.assertEqual(self.logic.fallen_person_ids, set())
        self.assertEqual(self.logic.tracker.person_trackers, {})
        detected, data, _ = self.logic.update(6.0, [WIDE_BOX], [LYING_HEAD_LEFT])
        self.assertTrue(detected)
        self.assertEqual(data["fallen_ids"], [2])


class MissingPoseTest(unittest.TestCase):
    def test_person_without_landmarks_gets_an_id_but_no_features(self):
        logic = LegacyFallLogic()
        detected, data, features = logic.update(0.0, [WIDE_BOX], [None])
        self.assertFalse(detected)
        self.assertEqual(data["person_ids"], [1])
        self.assertEqual(features, [None])
        self.assertEqual(logic.prev_poses, [])


class MultiplePeopleTest(unittest.TestCase):
    def test_only_the_lying_person_is_reported(self):
        logic = LegacyFallLogic()
        detected, data, _ = logic.update(0.0, [TALL_BOX, FAR_BOX], [STANDING_FRONT, LYING_HEAD_LEFT])
        self.assertTrue(detected)
        self.assertEqual(data["person_ids"], [1, 2])
        self.assertEqual(data["fallen_ids"], [2])

    def test_history_is_shared_between_people(self):
        # 알려진 문제 P5: 두 번째 사람의 속도가 첫 번째 사람의 자세와 비교됨
        logic = LegacyFallLogic()
        _, _, features = logic.update(0.0, [TALL_BOX, FAR_BOX], [STANDING_FRONT, LYING_HEAD_LEFT])
        self.assertEqual(features[0]["velocity_y"], 0)
        self.assertEqual(features[1]["velocity_y"], 0.25)  # 0.5 - 0.25 (서 있는 사람의 어깨)
        self.assertEqual(len(logic.prev_poses), 2)

    def test_two_boxes_can_share_one_id(self):
        # 알려진 문제 P6: 매칭이 일대일이 아님. 두 번째 박스도 IoU 0.818로 ID 1에 매칭
        logic = LegacyFallLogic()
        logic.update(0.0, [(0, 0, 100, 100)], [STANDING_FRONT])
        detected, data, _ = logic.update(0.1, [(0, 0, 100, 100), (10, 0, 110, 100)],
                                         [LYING_HEAD_LEFT, LYING_HEAD_LEFT])
        self.assertEqual(data["person_ids"], [1, 1])
        self.assertTrue(detected)
        self.assertEqual(data["fallen_ids"], [1])

    def test_tracker_created_in_the_same_frame_is_a_candidate(self):
        logic = LegacyFallLogic()
        logic.update(0.0, [(0, 0, 100, 100)], [STANDING_FRONT])
        _, data, _ = logic.update(0.1, [(200, 0, 300, 100), (210, 0, 310, 100)],
                                  [STANDING_FRONT, STANDING_FRONT])
        self.assertEqual(data["person_ids"], [2, 2])

    def test_moved_box_keeps_its_id(self):
        logic = LegacyFallLogic()
        logic.update(0.0, [WIDE_BOX], [STANDING_FRONT])
        _, data, _ = logic.update(0.1, [WIDE_BOX_SHIFTED], [STANDING_FRONT])
        self.assertEqual(data["person_ids"], [1])


class TrackerTest(unittest.TestCase):
    def test_degenerate_boxes_never_match(self):
        # 넓이 0인 박스끼리는 합집합이 0: 원본(numpy 정수)은 nan이 되어 매칭되지 않음
        tracker = LegacyIouTracker()
        tracker.update([(5, 5, 5, 5)], 0.0)
        box_to_id, _ = tracker.update([(5, 5, 5, 5)], 0.1)
        self.assertEqual(box_to_id, {0: 2})

    def test_iou_must_exceed_threshold(self):
        tracker = LegacyIouTracker()
        tracker.update([(0, 0, 100, 100)], 0.0)
        # 겹침 50x100=5000, 합집합 15000 -> IoU 0.333 > 0.3 -> 같은 사람
        self.assertEqual(tracker.update([(50, 0, 150, 100)], 0.1)[0], {0: 1})
        # 겹침 30x100=3000, 합집합 17000 -> IoU 0.176 -> 새 사람
        self.assertEqual(tracker.update([(120, 0, 220, 100)], 0.2)[0], {0: 2})

    def test_nan_comparison_assumption(self):
        self.assertFalse(math.nan > 0.3)


if __name__ == "__main__":
    unittest.main()
