"""tools/caucafall_prepare.py: OmniFall time segments → UR Fall-style frame labels and everyday-action tags."""
import unittest

from tools import caucafall_prepare as cp
from tools import urfall_features as uf

SEGS = [(0.0, 2.0, "standing"), (2.0, 3.0, "fall"), (3.0, 5.0, "fallen")]


class FrameLabelTest(unittest.TestCase):
    def test_fall_video(self):
        self.assertEqual(cp.frame_label(SEGS, 1.0), (-1, "standing"))
        self.assertEqual(cp.frame_label(SEGS, 2.5), (0, "fall"))
        self.assertEqual(cp.frame_label(SEGS, 4.0), (1, "fallen"))
        self.assertEqual(cp.frame_label(SEGS, 5.02), (1, "fallen"))       # 영상 끝: 마지막 구간을 이어 씀

    def test_lying_after_fall_counts_as_on_ground_only_in_fall_videos(self):
        segs = [(0.0, 2.0, "standing"), (2.0, 3.0, "fall"), (3.0, 5.0, "lying")]
        self.assertEqual(cp.frame_label(segs, 4.0, "fall"), (1, "lying"))
        self.assertEqual(cp.frame_label(segs, 4.0, "adl"), (-1, "lying"))   # 일상 동작의 눕기는 낙상 아님


class TagsTest(unittest.TestCase):
    def test_other_takes_the_activity(self):
        rows = [{"frame": i, "omnifall_class": c} for i, c in enumerate(["other"] * 3 + ["stand_up"] * 2, start=1)]
        self.assertEqual(cp.tags_from_frames("adl-cfS01-kneel", rows),
                         [("adl-cfS01-kneel", 1, 3, "kneel_floor", "other"), ("adl-cfS01-kneel", 4, 5, "get_up", "stand_up")])

    def test_classes_map_to_known_actions(self):
        from tools.urfall_distributions import ACTION_GROUP
        for action in set(cp.CLASS_TO_ACTION.values()) | set(cp.OTHER_BY_ACTIVITY.values()):
            self.assertIn(action, ACTION_GROUP)                           # 분포 도구가 아는 동작 이름만


class FpsTest(unittest.TestCase):
    def test_descent_window_uses_the_log_fps(self):
        from tests.test_urfall_features import person, standing
        frames = []
        for k in range(20):                                               # 20fps: 0.25초 = 5프레임
            box, lms = person(standing(top=100 + 10 * k))                 # 프레임마다 10px 씩 내려감
            frames.append({"index": k, "now": k / 20, "boxes": [list(box)], "landmarks": [lms]})
        rows = uf.sequence_rows("android", "fall-cf", frames, {}, fps=20)
        self.assertEqual(rows[4]["C1_descent_025"], "")                   # 5프레임 전이 없음
        self.assertAlmostEqual(rows[5]["C1_descent_025"], 50 / 100 / 0.25)   # 5프레임 × 10px / 몸통 100px / 0.25초


if __name__ == "__main__":
    unittest.main()
