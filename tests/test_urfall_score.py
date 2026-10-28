"""Scoring rules of tools/urfall_score.py on made-up frames (no dataset, no detector needed)."""
import unittest

from tools import urfall_score as us

FPS = us.FPS


class FakeEngine:
    """Returns the fallen IDs given per frame index."""

    def __init__(self, fallen_by_index):
        self.fallen = fallen_by_index

    def step(self, record):
        return self.fallen.get(record["index"], [])


def frames(n):
    return [{"index": i, "now": i / FPS, "boxes": [[0, 0, 10, 10]], "landmarks": [[[0, 0, 0, 1]]]} for i in range(n)]


def fall_labels(n, falling_from, lying_from):
    """1-based labels: -1 before falling_from, 0 until lying_from, 1 after."""
    return {f: (-1 if f < falling_from else 0 if f < lying_from else 1) for f in range(1, n + 1)}


class AlertTest(unittest.TestCase):
    def test_same_person_within_5s_is_one_alert(self):
        alerts = us.alerts_for(frames(400), FakeEngine({10: [1], 100: [1], 200: [1]}))
        self.assertEqual([i for i, _ in alerts], [10, 200])   # 100 은 3초 뒤라 묶임, 200 은 6.3초 뒤

    def test_each_new_person_is_an_alert(self):
        alerts = us.alerts_for(frames(20), FakeEngine({5: [1, 2]}))
        self.assertEqual(len(alerts), 2)


class FallSequenceTest(unittest.TestCase):
    labels = {"fall-99": fall_labels(150, falling_from=61, lying_from=91)}   # 넘어짐 2.0초, 누움 3.0초

    def score(self, fallen):
        return us.score_sequence("fall-99", frames(150), self.labels, FakeEngine(fallen))

    def test_hit_and_delay(self):
        r = self.score({100: [1]})   # 3.33초
        self.assertTrue(r["hit"])
        self.assertEqual((r["early"], r["false_alarms"], r["delay_fall_s"], r["delay_lying_s"]), (0, 0, 1.33, 0.33))

    def test_alert_just_before_fall_start_counts(self):
        self.assertTrue(self.score({50: [1]})["hit"])   # 넘어지기 0.37초 전: 허용 범위(0.5초) 안

    def test_early_alert_is_false_alarm_and_miss(self):
        r = self.score({10: [1]})
        self.assertEqual((r["hit"], r["early"], r["false_alarms"]), (False, 1, 1))

    def test_no_alert_is_miss(self):
        r = self.score({})
        self.assertEqual((r["hit"], r["delay_fall_s"]), (False, ""))


class AdlSequenceTest(unittest.TestCase):
    def test_every_alert_is_false_alarm(self):
        labels = {"adl-99": {f: (1 if 100 <= f <= 120 else -1) for f in range(1, 201)}}
        r = us.score_sequence("adl-99", frames(200), labels, FakeEngine({20: [1], 109: [2]}))
        self.assertEqual((r["false_alarms"], r["fa_while_lying"]), (2, 1))   # 109번 프레임 = 정답 110번(누움)

    def test_summary(self):
        rows = [{"kind": "fall", "hit": True, "false_alarms": 0, "delay_fall_s": 1.0},
                {"kind": "fall", "hit": False, "false_alarms": 1, "delay_fall_s": ""},
                {"kind": "adl", "hit": "", "false_alarms": 2, "delay_fall_s": ""}]
        s = us.summarize(rows, frames_adl=FPS * 60)
        self.assertEqual((s["hits"], s["false_alarms"], s["adl_with_alarm"]), (1, 3, 1))
        self.assertAlmostEqual(s["recall"], 0.5)
        self.assertAlmostEqual(s["precision"], 0.25)
        self.assertAlmostEqual(s["fa_per_min"], 2.0)


if __name__ == "__main__":
    unittest.main()
