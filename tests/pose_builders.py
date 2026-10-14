"""Synthetic poses in the same structure FallDetector.analyze_pose returns.

Structure (from models/fall_detector.py): a list of 33 tuples (x, y, z, visibility), where
x and y are normalized to the person crop frame[y1:y2, x1:x2] (x: fraction of box width,
y: fraction of box height). Only joints 0, 11, 12, 23-28 are used by the legacy features;
the other 24 joints get a fixed filler value.

MediaPipe joint numbers: 0 nose, 11/12 left/right shoulder, 23/24 left/right hip,
25/26 left/right knee, 27/28 left/right ankle ("left" = the person's left side).

Values are multiples of 1/16 so sums, halves and differences are exact in floating point
and expected results can be written as plain numbers.
"""

NUM_LANDMARKS = 33
FILLER = (0.5, 0.5, 0.0, 1.0)


def make_landmarks(points, z=0.0, visibility=1.0):
    """points: {joint number: (x, y)}; returns the 33-tuple list."""
    landmarks = [FILLER] * NUM_LANDMARKS
    for index, (x, y) in points.items():
        landmarks[index] = (x, y, z, visibility)
    return landmarks


# 카메라를 정면으로 보고 선 자세: 몸의 왼쪽(11, 23, 25, 27)이 화면 오른쪽(큰 x)에 있음
STANDING_FRONT_POINTS = {
    0: (0.5, 0.125),
    11: (0.625, 0.25), 12: (0.375, 0.25),
    23: (0.5625, 0.5), 24: (0.4375, 0.5),
    25: (0.5625, 0.75), 26: (0.4375, 0.75),
    27: (0.5625, 0.875), 28: (0.4375, 0.875),
}
# 등을 보이고 선 자세: 몸의 왼쪽이 화면 왼쪽(작은 x)에 있음
STANDING_BACK_POINTS = {
    0: (0.5, 0.125),
    11: (0.375, 0.25), 12: (0.625, 0.25),
    23: (0.4375, 0.5), 24: (0.5625, 0.5),
    25: (0.4375, 0.75), 26: (0.5625, 0.75),
    27: (0.4375, 0.875), 28: (0.5625, 0.875),
}
# 머리를 화면 왼쪽에 두고 누운 자세
LYING_HEAD_LEFT_POINTS = {
    0: (0.125, 0.5),
    11: (0.25, 0.4375), 12: (0.25, 0.5625),
    23: (0.5, 0.4375), 24: (0.5, 0.5625),
    25: (0.75, 0.4375), 26: (0.75, 0.5625),
    27: (0.875, 0.4375), 28: (0.875, 0.5625),
}

STANDING_FRONT = make_landmarks(STANDING_FRONT_POINTS)
STANDING_BACK = make_landmarks(STANDING_BACK_POINTS)
LYING_HEAD_LEFT = make_landmarks(LYING_HEAD_LEFT_POINTS)

# 사람 박스 (프레임 픽셀, x1, y1, x2, y2)
WIDE_BOX = (100, 100, 300, 200)       # 가로로 긴 박스 (누운 사람)
WIDE_BOX_SHIFTED = (110, 100, 310, 200)  # WIDE_BOX와 IoU 약 0.9
TALL_BOX = (0, 0, 100, 300)           # 세로로 긴 박스 (선 사람)
FAR_BOX = (400, 300, 600, 400)        # 위 박스들과 겹치지 않음
