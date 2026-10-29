"""tools/urfall_distributions.py: grouping of frames and the AUC separation score."""
import unittest

from tools import urfall_distributions as ud


class AucTest(unittest.TestCase):
    def test_perfect_none_and_reversed(self):
        self.assertEqual(ud.auc([3, 4, 5], [0, 1, 2]), 1.0)     # 낙상이 항상 더 큼
        self.assertEqual(ud.auc([0, 1], [5, 6]), 0.0)           # 낙상이 항상 더 작음
        self.assertEqual(ud.auc([1, 1], [1, 1]), 0.5)           # 같음 = 못 가름
        self.assertAlmostEqual(ud.auc([1, 3], [2]), 0.5)        # 반은 크고 반은 작음
        self.assertIsNone(ud.auc([], [1]))

    def test_percentile(self):
        self.assertEqual(ud.percentile([0, 10], 50), 5)
        self.assertEqual(ud.percentile([1, 2, 3, 4, 5], 0), 1)
        self.assertIsNone(ud.percentile([], 50))


class GroupTest(unittest.TestCase):
    tags = {"adl-99": [(1, 10, "walk"), (11, 20, "lie_down"), (21, 30, "lie_floor")]}

    def test_fall_by_label_and_adl_by_tag(self):
        g = lambda **r: ud.group_of({"kind": "adl", "sequence": "adl-99", "label": "", **r}, self.tags)  # noqa: E731
        self.assertEqual(g(frame="5"), "walk_stand")
        self.assertEqual(g(frame="15"), "lie_bed")               # 눕는 중도 침대·소파 그룹
        self.assertEqual(g(frame="30"), "lie_floor")
        self.assertIsNone(g(frame="31"))                          # 표시가 없는 프레임
        fall = lambda lab: ud.group_of({"kind": "fall", "sequence": "fall-99", "frame": "1", "label": lab}, {})  # noqa: E731
        self.assertEqual([fall("-1"), fall("0"), fall("1"), fall("")], ["fall_before", "fall_falling", "fall_lying", None])


if __name__ == "__main__":
    unittest.main()
