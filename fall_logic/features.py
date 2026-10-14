"""Pose features, reproducing FallDetector.calculate_pose_features (models/fall_detector.py) exactly.

Input coordinates are the ones FallDetector produces: each landmark is
(x, y, z, visibility) from MediaPipe Pose run on the person crop frame[y1:y2, x1:x2].
So x is a fraction of the box width and y a fraction of the box height, measured
separately (not frame pixels, not frame-normalized).

Known issues are kept on purpose (legacy reproduction):
  - prev_poses is one list shared by every person, so velocity/acceleration/jerk of one
    person can be computed against another person's pose
  - velocities use time_diff = 1 (per call), not real time
  - the aspect ratio width uses only the person's left-side joints for the minimum x and
    right-side joints for the maximum x, so it is negative for a person facing the camera
    and is then replaced by 0.0001
  - visibility is ignored
The arithmetic below is copied line by line so results are bit-identical; do not tidy it.
"""
import math

# 코, 어깨, 엉덩이, 무릎, 발목 (MediaPipe Pose 33개 관절 번호)
KEY_POINTS = [0, 11, 12, 23, 24, 25, 26, 27, 28]
# 이전 자세 기록 최대 개수 (모든 사람이 같이 씀)
MAX_POSE_HISTORY = 15


def compute_legacy_features(landmarks, prev_poses, now):
    """Return the feature dict for one person, or None, and append it to prev_poses.

    landmarks: list of (x, y, z, visibility), crop-normalized, as FallDetector.analyze_pose builds it.
    prev_poses: the shared history list; modified in place (appended, trimmed to 15).
    now: the value FallDetector gets from time.time() (stored as "timestamp").
    """
    if not landmarks:
        return None

    key_points = KEY_POINTS

    key_landmarks = [landmarks[i][:2] for i in key_points if i < len(landmarks)]

    if len(key_landmarks) < len(key_points):
        return None

    head_y = landmarks[0][1]
    left_ankle_y = landmarks[27][1]
    right_ankle_y = landmarks[28][1]
    ankle_y = (left_ankle_y + right_ankle_y) / 2
    height = abs(ankle_y - head_y)

    mid_shoulder_x = (landmarks[11][0] + landmarks[12][0]) / 2
    mid_shoulder_y = (landmarks[11][1] + landmarks[12][1]) / 2
    mid_hip_x = (landmarks[23][0] + landmarks[24][0]) / 2
    mid_hip_y = (landmarks[23][1] + landmarks[24][1]) / 2

    dx = mid_hip_x - mid_shoulder_x
    dy = mid_hip_y - mid_shoulder_y

    angle = math.degrees(math.atan2(dx, dy))  # Angle with vertical axis

    shoulder_pos = (mid_shoulder_x, mid_shoulder_y)
    hip_pos = (mid_hip_x, mid_hip_y)
    feet_pos = ((landmarks[27][0] + landmarks[28][0])/2, (landmarks[27][1] + landmarks[28][1])/2)

    left_most_x = min(landmarks[11][0], landmarks[23][0], landmarks[25][0], landmarks[27][0])
    right_most_x = max(landmarks[12][0], landmarks[24][0], landmarks[26][0], landmarks[28][0])
    top_most_y = min(landmarks[0][1], landmarks[11][1], landmarks[12][1])
    bottom_most_y = max(landmarks[27][1], landmarks[28][1])

    bbox_width = right_most_x - left_most_x
    bbox_height = bottom_most_y - top_most_y
    aspect_ratio = bbox_height / max(bbox_width, 0.0001)  # Avoid division by zero

    shoulder_to_hip_distance = math.sqrt((mid_shoulder_x - mid_hip_x)**2 + (mid_shoulder_y - mid_hip_y)**2)
    hip_to_feet_distance = math.sqrt((mid_hip_x - feet_pos[0])**2 + (mid_hip_y - feet_pos[1])**2)

    velocity_y = 0
    velocity_x = 0
    acceleration = 0
    jerk = 0

    if prev_poses:
        prev = prev_poses[-1]
        time_diff = 1  # 원본과 같이 프레임 간격을 1로 가정

        velocity_y = (mid_shoulder_y - prev["mid_shoulder_y"]) / time_diff

        velocity_x = (mid_shoulder_x - prev["mid_shoulder_x"]) / time_diff

        if len(prev_poses) >= 2:
            prev_velocity_y = (prev["mid_shoulder_y"] - prev_poses[-2]["mid_shoulder_y"]) / time_diff
            acceleration = (velocity_y - prev_velocity_y) / time_diff

            if len(prev_poses) >= 3:
                prev_acceleration = (prev_velocity_y - (prev_poses[-2]["mid_shoulder_y"] - prev_poses[-3]["mid_shoulder_y"]) / time_diff) / time_diff
                jerk = (acceleration - prev_acceleration) / time_diff

    features = {
        "height": height,
        "angle": angle,
        "velocity_y": velocity_y,
        "velocity_x": velocity_x,
        "acceleration": acceleration,
        "jerk": jerk,
        "mid_shoulder_y": mid_shoulder_y,
        "mid_shoulder_x": mid_shoulder_x,
        "mid_hip_y": mid_hip_y,
        "mid_hip_x": mid_hip_x,
        "shoulder_pos": shoulder_pos,
        "hip_pos": hip_pos,
        "feet_pos": feet_pos,
        "aspect_ratio": aspect_ratio,
        "shoulder_to_hip_distance": shoulder_to_hip_distance,
        "hip_to_feet_distance": hip_to_feet_distance,
        "timestamp": now
    }

    prev_poses.append(features)
    if len(prev_poses) > MAX_POSE_HISTORY:
        prev_poses.pop(0)

    return features
