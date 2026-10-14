"""Coordinate conversion for a future improved mode that works in frame pixel coordinates.

Not used by the legacy mode (which must keep crop-normalized coordinates). No thresholds
are defined here: those are decided after checking the real dataset and its labels.

Why pixels: the PC detector gives landmarks normalized to the person crop, while a phone
running MediaPipe Pose Landmarker on the whole frame gives landmarks normalized to the frame.
Converting both to frame pixels gives one coordinate system for the same rules.
"""


def crop_landmarks_to_pixels(landmarks, box):
    """Crop-normalized landmarks (FallDetector.analyze_pose) -> frame pixels.

    box: (x1, y1, x2, y2) the crop was cut from (frame[y1:y2, x1:x2]).
    Returns [(px, py, z, visibility), ...] as floats. Same mapping as utils.utils.draw_skeleton
    (x1 + x * box width) without its int() rounding. z is passed through unchanged (its scale
    follows the crop width in MediaPipe and is not converted).
    """
    x1, y1, x2, y2 = box
    box_w, box_h = x2 - x1, y2 - y1
    return [(float(x1 + lm[0] * box_w), float(y1 + lm[1] * box_h), lm[2], lm[3]) for lm in landmarks]


def frame_landmarks_to_pixels(landmarks, frame_width, frame_height):
    """Frame-normalized landmarks (e.g. Pose Landmarker on the whole frame) -> frame pixels."""
    return [(float(lm[0] * frame_width), float(lm[1] * frame_height), lm[2], lm[3]) for lm in landmarks]
