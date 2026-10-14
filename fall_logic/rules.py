"""Posture rule, reproducing the check inside FallDetector.process_frame (models/fall_detector.py:494-542).

A person counts as fallen in a single frame when
    abs(angle) >= angle_threshold + 10   and   aspect_ratio < 1.5
No duration, motion or visibility check (known issue, kept for the legacy mode).
FallDetector.detect_fall / classify_fall_type exist but are never called, so they are not here.
"""

# 원본 코드에 고정된 값 (process_frame 안의 숫자 그대로)
LEGACY_ANGLE_MARGIN = 10
LEGACY_MAX_ASPECT_RATIO = 1.5
# 원본에서 fall_types가 항상 False라 언제나 이 유형이 됨
DEFAULT_FALL_TYPE = "slip_and_fall"
FALL_TYPES = ("step_and_fall", "slip_and_fall", "trip_and_fall", "stump_and_fall")


def is_legacy_fall_posture(pose_features, angle_threshold):
    """True if the features meet the legacy fall condition (same defaults as the original .get calls)."""
    angle = pose_features.get("angle", 0)
    if abs(angle) >= (angle_threshold + LEGACY_ANGLE_MARGIN):
        aspect_ratio = pose_features.get("aspect_ratio", 2.0)
        if aspect_ratio < LEGACY_MAX_ASPECT_RATIO:
            return True
    return False
