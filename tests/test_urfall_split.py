"""tools/urfall_split.py: fixed, per-group tune/test split by whole sequence."""
import unittest

from tools import urfall_split as sp

LYING = (10, 11, 21, 22, 23) + tuple(range(30, 41))
NORMAL = tuple(range(1, 10)) + (12, 13, 14, 15, 16, 24)
NAMES = [f"fall-{i:02d}" for i in range(1, 31)] + [f"adl-{i:02d}" for i in NORMAL + LYING]
LABELS = {f"adl-{i:02d}": {1: 1} for i in LYING}   # 눕는 장면이 있는 일상 동작


class SplitTest(unittest.TestCase):
    def test_groups(self):
        self.assertEqual(sp.group_of("fall-07", LABELS), "fall_stand")   # 홀수: 서서 넘어짐
        self.assertEqual(sp.group_of("fall-08", LABELS), "fall_chair")   # 짝수: 의자에서 넘어짐
        self.assertEqual(sp.group_of("adl-30", LABELS), "adl_lying")
        self.assertEqual(sp.group_of("adl-03", LABELS), "adl_normal")

    def test_counts_per_group(self):
        rows = sp.make_split(NAMES, LABELS)
        count = {}
        for _, g, s in rows:
            count[(g, s)] = count.get((g, s), 0) + 1
        self.assertEqual(count, {("fall_stand", "tune"): 9, ("fall_stand", "test"): 6,
                                 ("fall_chair", "tune"): 9, ("fall_chair", "test"): 6,
                                 ("adl_normal", "tune"): 9, ("adl_normal", "test"): 6,
                                 ("adl_lying", "tune"): 8, ("adl_lying", "test"): 8})

    def test_each_sequence_once_and_fixed(self):
        rows = sp.make_split(NAMES, LABELS)
        self.assertEqual(sorted(n for n, _, _ in rows), sorted(NAMES))   # 한 영상은 한쪽에만
        self.assertEqual(rows, sp.make_split(list(reversed(NAMES)), LABELS))   # 같은 씨앗 = 같은 결과
        self.assertNotEqual(rows, sp.make_split(NAMES, LABELS, seed=1))


if __name__ == "__main__":
    unittest.main()
