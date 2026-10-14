"""Pixel conversion for the future improved mode (fall_logic/coords.py). Not used by the legacy mode."""
import unittest

from fall_logic.coords import crop_landmarks_to_pixels, frame_landmarks_to_pixels


class CropToPixelsTest(unittest.TestCase):
    def test_maps_crop_fractions_into_the_box(self):
        box = (100, 50, 300, 250)  # 폭 200, 높이 200
        landmarks = [(0.0, 0.0, 0.1, 0.9), (1.0, 1.0, 0.0, 1.0), (0.25, 0.5, -0.2, 0.5)]
        self.assertEqual(crop_landmarks_to_pixels(landmarks, box),
                         [(100.0, 50.0, 0.1, 0.9), (300.0, 250.0, 0.0, 1.0), (150.0, 150.0, -0.2, 0.5)])

    def test_same_mapping_as_draw_skeleton_before_rounding(self):
        # utils.utils.draw_skeleton: int(x * box_w) + x1
        box = (10, 20, 110, 70)
        (px, py, _, _), = crop_landmarks_to_pixels([(0.375, 0.5, 0.0, 1.0)], box)
        self.assertEqual((int(0.375 * 100) + 10, int(0.5 * 50) + 20), (int(px), int(py)))

    def test_values_outside_the_crop_are_kept(self):
        (px, py, _, _), = crop_landmarks_to_pixels([(-0.5, 1.5, 0.0, 1.0)], (100, 100, 200, 200))
        self.assertEqual((px, py), (50.0, 250.0))


class FrameToPixelsTest(unittest.TestCase):
    def test_scales_by_frame_size(self):
        self.assertEqual(frame_landmarks_to_pixels([(0.5, 0.25, 0.0, 1.0)], 640, 480),
                         [(320.0, 120.0, 0.0, 1.0)])


if __name__ == "__main__":
    unittest.main()
