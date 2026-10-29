"""fall_logic/v2.py: the streaming rule on made-up frame series (30 fps)."""
import math
import unittest

from fall_logic.v2 import FallRuleV2, Params

FPS = 30
UP = dict(a1=85.0, h3=2.5, b1=0.4, c1=0.0)            # 서 있음
DOWN = dict(a1=10.0, h3=0.0, b1=2.5, c1=0.0)          # 바닥에 누움


def run(frames, params=Params()):
    rule = FallRuleV2(params)
    for i, f in enumerate(frames):
        rule.update(i / FPS, **f)
    return rule.alarm


class StayDownTest(unittest.TestCase):
    def test_down_for_one_second_fires_and_short_does_not(self):
        self.assertIsNone(run([UP] * 30 + [DOWN] * 25 + [UP] * 30))           # 0.83초만 누움
        self.assertAlmostEqual(run([UP] * 30 + [DOWN] * 40), (30 + 30) / FPS)  # 누운 지 1.0초째 프레임

    def test_short_gap_without_person_does_not_break_but_a_standing_frame_does(self):
        nobody = dict(a1=None, h3=None, b1=None, c1=None)
        self.assertIsNotNone(run([DOWN] * 20 + [nobody] * 20 + [DOWN] * 15))  # 안 보인 0.67초는 이어짐
        self.assertIsNone(run([DOWN] * 20 + [UP] + [DOWN] * 20))              # 서 있는 프레임이 끊음
        self.assertIsNone(run([DOWN] * 10 + [nobody] * 40 + [DOWN] * 25))     # 1.3초 안 보이면 새로 시작

    def test_wide_box_alone_counts_as_down(self):
        self.assertIsNotNone(run([dict(a1=80.0, h3=2.0, b1=1.6, c1=0.0)] * 40))  # 위에서 본 모습: 상자만 가로로 김
        self.assertIsNone(run([dict(a1=80.0, h3=2.0, b1=1.4, c1=0.0)] * 40))


class FastDropTest(unittest.TestCase):
    no_stay = Params(stay_seconds=math.inf)

    def test_drop_then_three_wide_frames(self):
        drop = dict(a1=60.0, h3=1.5, b1=0.8, c1=3.0)
        frames = [UP] * 10 + [drop] * 3 + [DOWN] * 5
        self.assertAlmostEqual(run(frames, self.no_stay), 15 / FPS)          # 하락 뒤 세 번째 누운 프레임

    def test_single_speed_glitch_is_smoothed_away(self):
        spike = dict(UP, c1=9.0)                                              # 한 프레임만 튐
        self.assertIsNone(run([UP] * 10 + [spike] + [UP] * 2 + [DOWN] * 5 + [UP] * 30, self.no_stay))

    def test_drop_without_lying_afterwards_does_not_fire(self):
        drop = dict(a1=70.0, h3=1.8, b1=0.6, c1=3.0)
        self.assertIsNone(run([UP] * 10 + [drop] * 3 + [UP] * 40, self.no_stay))   # 빠르게 앉기 등

    def test_lying_too_late_after_the_drop(self):
        drop = dict(a1=70.0, h3=1.8, b1=0.6, c1=3.0)
        self.assertIsNone(run([UP] * 10 + [drop] * 3 + [UP] * 40 + [DOWN] * 5, self.no_stay))


class ParamsTest(unittest.TestCase):
    def test_chosen_values(self):
        # docs/fall_rule_v2.md 의 값 (2026-10-29 대안 1)
        self.assertEqual(Params(), Params(40.0, 0.3, 1.5, 2.0, "wide", 3, 1.0, 1.0, 1.0))


if __name__ == "__main__":
    unittest.main()
