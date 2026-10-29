"""Geometry of tools/urfall_features.py on made-up people (frame pixels, no dataset needed)."""
import math
import unittest

from tools import urfall_features as uf

FPS = uf.FPS


def person(points_px, box=(0, 0, 640, 480), vis=None):
    """Box-relative landmarks (33) for the given pixel points {index: (x, y)}; other joints invisible."""
    x1, y1, x2, y2 = box
    lms = [(0.0, 0.0, 0.0, 0.0)] * 33
    for i, (x, y) in points_px.items():
        v = 1.0 if vis is None else vis.get(i, 1.0)
        lms[i] = ((x - x1) / (x2 - x1), (y - y1) / (y2 - y1), 0.0, v)
    return box, lms


def standing(cx=300, top=100, h=300):
    """Upright person, head at top, feet at top + h (y grows downward)."""
    return {0: (cx, top), 11: (cx - 20, top + 40), 12: (cx + 20, top + 40), 23: (cx - 15, top + 140),
            24: (cx + 15, top + 140), 25: (cx - 15, top + 220), 26: (cx + 15, top + 220),
            27: (cx - 12, top + h), 28: (cx + 12, top + h)}


def lying(left=100, y=400, length=300):
    """Person lying flat across the picture, head on the left."""
    return {0: (left, y), 11: (left + 40, y - 20), 12: (left + 40, y + 20), 23: (left + 140, y - 15),
            24: (left + 140, y + 15), 25: (left + 220, y - 15), 26: (left + 220, y + 15),
            27: (left + length, y - 12), 28: (left + length, y + 12)}


class GeometryTest(unittest.TestCase):
    def test_pixels_back_from_box_fractions(self):
        box, lms = person({0: (150, 250)}, box=(100, 200, 300, 400))
        self.assertEqual(uf.to_pixels(box, lms)[0][:2], (150.0, 250.0))

    def test_upright_is_90_and_lying_is_0(self):
        g = uf.person_geometry(*person(standing()))
        self.assertAlmostEqual(g["A1_body_angle_shoulder"], 90.0, places=6)
        self.assertAlmostEqual(g["A2_body_angle_head"], 90.0, places=6)
        self.assertAlmostEqual(g["E1_torso_leg_angle"], 180.0, places=6)    # 몸이 곧게 펴짐
        g = uf.person_geometry(*person(lying()))
        self.assertAlmostEqual(g["A1_body_angle_shoulder"], 0.0, places=6)
        self.assertGreater(g["B2_joint_ratio"], 1)                       # 누우면 관절 범위가 가로로 김

    def test_angle_does_not_depend_on_box_shape(self):
        # 같은 사람을 다른 모양의 상자로 기록해도 픽셀 각도는 같음 (지금 방식의 왜곡이 없음)
        pts = {11: (200, 100), 12: (220, 100), 27: (300, 200), 28: (320, 200), 23: (250, 150), 24: (270, 150)}
        a = uf.person_geometry(*person(pts, box=(150, 50, 400, 250)))["A1_body_angle_shoulder"]
        b = uf.person_geometry(*person(pts, box=(0, 0, 640, 480)))["A1_body_angle_shoulder"]
        self.assertAlmostEqual(a, 45.0, places=6)
        self.assertAlmostEqual(a, b, places=6)

    def test_blurry_joints_leave_features_empty(self):
        vis = {27: 0.2, 28: 0.3}                                          # 발목이 흐림
        g = uf.person_geometry(*person(standing(), vis=vis))
        self.assertIsNone(g["A1_body_angle_shoulder"])
        self.assertIsNone(g["E3_hip_above_ankle"])
        self.assertIsNotNone(g["torso_px"])
        self.assertEqual(g["key_visible"], 7)

    def test_one_side_visible_uses_that_joint(self):
        g = uf.person_geometry(*person(standing(), vis={28: 0.1}))       # 오른쪽 발목만 흐림
        self.assertIsNotNone(g["A1_body_angle_shoulder"])

    def test_omobot_heights_in_torso_lengths(self):
        g = uf.person_geometry(*person(standing()))
        torso = g["torso_px"]
        self.assertAlmostEqual(torso, 100.0, places=6)
        self.assertAlmostEqual(g["E3_shoulder_above_ankle"], 260 / torso, places=6)
        self.assertAlmostEqual(g["E3_hip_above_ankle"], 160 / torso, places=6)

    def test_head_above_ankle_from_this_frame_only(self):
        self.assertAlmostEqual(uf.person_geometry(*person(standing()))["H3_head_above_ankle"], 3.0)   # 코 100, 발목 400
        self.assertAlmostEqual(uf.person_geometry(*person(lying()))["H3_head_above_ankle"], 0.0)     # 머리와 발이 같은 높이
        # 사람이 화면에서 더 아래(카메라 가까이)로 옮겨도 같은 값 (서 있을 때 기준을 쓰지 않음)
        self.assertAlmostEqual(uf.person_geometry(*person(standing(top=150)))["H3_head_above_ankle"], 3.0)
        self.assertIsNone(uf.person_geometry(*person(standing(), vis={0: 0.1}))["H3_head_above_ankle"])          # 코 흐림
        self.assertIsNone(uf.person_geometry(*person(standing(), vis={27: 0.1, 28: 0.1}))["H3_head_above_ankle"])  # 발목 흐림


class TimeFeatureTest(unittest.TestCase):
    def test_descent_speed_in_torso_lengths_per_second(self):
        self.assertAlmostEqual(uf.descent_speed((0, 150), (0, 100), 100.0, 0.25), 2.0)   # 0.5 몸통 / 0.25초
        self.assertLess(uf.descent_speed((0, 100), (0, 150), 100.0, 0.25), 0)            # 올라가면 음수
        self.assertIsNone(uf.descent_speed(None, (0, 100), 100.0, 0.25))

    def test_frame_seconds_before_matches_frame_count_at_a_steady_rate(self):
        for fps in (30, 20, 15):
            times = [k / fps for k in range(60)]
            for k in range(60):
                back = round(0.25 * fps)
                self.assertEqual(uf.frame_seconds_before(times, k, 0.25), k - back if k - back >= 0 else None, (fps, k))

    def test_frame_seconds_before_with_uneven_frames(self):
        times = [0.0, 0.1, 0.3, 0.5, 0.55, 0.9, 1.3]
        self.assertIsNone(uf.frame_seconds_before(times, 1, 0.25))     # 시작 뒤 0.25초가 안 됨
        self.assertEqual(uf.frame_seconds_before(times, 2, 0.25), 0)   # 0.05 → 0.0 (0.05 차이) / 0.1 (0.05 차이): 같으면 이른 쪽
        self.assertEqual(uf.frame_seconds_before(times, 4, 0.25), 2)   # 0.30 → 0.3
        self.assertEqual(uf.frame_seconds_before(times, 5, 0.25), 4)   # 0.65 → 0.55 (0.1 차이, 허용 끝)
        self.assertIsNone(uf.frame_seconds_before(times, 6, 0.25))     # 1.05 → 가장 가까운 0.9 가 0.15 차이

    def test_time_timing_divides_by_the_real_gap(self):
        # 몸 전체가 1초에 100px(= 몸통 1개) 내려감. 프레임을 불규칙하게 빼도 속도는 1.0 몸통/초
        frames = []
        for k in range(30):
            box, lms = person(standing(top=50 + k / FPS * 100.0))
            frames.append({"index": k, "now": k / FPS, "boxes": [list(box)], "landmarks": [lms]})
        sparse = [f for f in frames if f["index"] % 3 != 1 and f["index"] not in (12, 13, 14)]
        rows = uf.sequence_rows("android", "adl-95", sparse, {}, timing="time")
        speeds = [r["C1_descent_025"] for r in rows if r["C1_descent_025"] != ""]
        self.assertGreater(len(speeds), 10)
        for v in speeds:
            self.assertAlmostEqual(v, 1.0, places=6)
        # 프레임 수로 세면 (8프레임 전 = 0.267초로 가정) 빠진 프레임 때문에 속도가 부풀려짐
        counted = [r["C1_descent_025"] for r in uf.sequence_rows("android", "adl-95", sparse, {}, timing="frames")
                   if r["C1_descent_025"] != ""]
        self.assertGreater(max(counted), 1.3)

    def test_rows_for_a_falling_sequence(self):
        # 서 있다가(0~14) 한 프레임에 눕고(15~) 그 뒤 사람이 안 보임(25~29)
        frames, labels = [], {"fall-99": {}}
        for k in range(30):
            if k < 25:
                pts = standing() if k < 15 else lying()
                box, lms = person(pts)
                frames.append({"index": k, "now": k / FPS, "boxes": [list(box)], "landmarks": [lms]})
            else:
                frames.append({"index": k, "now": k / FPS, "boxes": [], "landmarks": []})
            labels["fall-99"][k + 1] = -1 if k < 15 else 1
        rows = uf.sequence_rows("android", "fall-99", frames, labels)
        self.assertEqual(len(rows), 30)                                   # 사람이 없는 프레임도 한 줄
        self.assertEqual(rows[26]["person_count"], 0)
        self.assertEqual(rows[26]["A1_body_angle_shoulder"], "")
        self.assertEqual(rows[5]["C1_descent_025"], "")                    # 0.25초 전 프레임이 없음
        self.assertAlmostEqual(rows[10]["C1_descent_025"], 0.0)            # 가만히 서 있음
        self.assertGreater(rows[16]["C1_descent_025"], 0)                  # 눕자 엉덩이가 내려감
        self.assertAlmostEqual(rows[10]["E2_torso_ratio"], 1.0)            # 첫 1초 몸통과 같음
        self.assertEqual(rows[10]["label"], -1)
        self.assertEqual(rows[10]["main"], 1)

    def test_head_and_hip_drop_from_standing_start(self):
        frames, labels = [], {"fall-98": {}}
        for k in range(40):
            box, lms = person(standing() if k < 20 else lying())
            frames.append({"index": k, "now": k / FPS, "boxes": [list(box)], "landmarks": [lms]})
        refs = {}
        rows = uf.sequence_rows("android", "fall-98", frames, labels, refs)
        self.assertEqual(refs["fall-98"]["source"], "start")
        self.assertEqual(refs["fall-98"]["frames"], list(range(1, 21)))     # 처음 3초 안의 서 있는 프레임
        self.assertAlmostEqual(refs["fall-98"]["height"], 300.0)            # 코 100 → 발목 400
        self.assertAlmostEqual(rows[10]["H1_head_drop"], 0.0)
        self.assertAlmostEqual(rows[30]["H1_head_drop"], 1.0)               # 머리가 키만큼 (100 → 400) 내려옴
        self.assertAlmostEqual(rows[30]["H2_hip_drop"], (400 - 240) / 300)

    def test_sitting_start_uses_fallback_and_no_standing_gives_empty(self):
        sitting = dict(standing())
        sitting.update({25: (370, 240), 26: (380, 240), 27: (370, 340), 28: (380, 340)})   # 무릎이 앞으로
        frames = []
        for k in range(150):                                                # 0~3.3초 앉음, 그 뒤 서 있음
            box, lms = person(sitting if k < 100 else standing())
            frames.append({"index": k, "now": k / FPS, "boxes": [list(box)], "landmarks": [lms]})
        refs = {}
        uf.sequence_rows("android", "fall-97", frames, {}, refs)
        self.assertEqual(refs["fall-97"]["source"], "fallback")
        self.assertEqual(refs["fall-97"]["frames"][0], 101)                 # 앉은 프레임은 기준에서 빠짐
        refs = {}
        rows = uf.sequence_rows("android", "fall-96", frames[:100], {}, refs)
        self.assertIsNone(refs["fall-96"])
        self.assertEqual(rows[50]["H1_head_drop"], "")

    def test_main_person_is_the_largest(self):
        small = {i: (x / 3 + 400, y / 3) for i, (x, y) in standing().items()}
        b1, l1 = person(small)
        b2, l2 = person(standing())
        frames = [{"index": 0, "now": 0.0, "boxes": [list(b1), list(b2)], "landmarks": [l1, l2]}]
        rows = uf.sequence_rows("android", "adl-99", frames, {})
        self.assertEqual([r["main"] for r in rows], [0, 1])
        self.assertEqual(rows[0]["label"], "")                             # 정답 없는 프레임


if __name__ == "__main__":
    unittest.main()
