"""LegacyFallLogic: the decision part of FallDetector.process_frame without YOLO, MediaPipe or drawing.

FallDetector.process_frame(frame) does, per frame:
  1. detect_person      -> person_boxes (frame pixels)            [stays in FallDetector]
  2. track_persons      -> box index -> person ID                  [tracker.py]
  3. analyze_pose       -> landmarks (crop-normalized) per box     [stays in FallDetector]
     calculate_pose_features -> features, shared history          [features.py]
  4. the rule loop      -> fall_data                               [rules.py + update() below]
LegacyFallLogic.update() takes the outputs of 1 and 3 and returns the same fall_data as 4,
so it can be compared frame by frame with the original (tools/replay_compare.py).
"""
from fall_logic.features import compute_legacy_features
from fall_logic.rules import DEFAULT_FALL_TYPE, FALL_TYPES, is_legacy_fall_posture
from fall_logic.tracker import LegacyIouTracker

# FallDetector와 대시보드 설정의 기본값
DEFAULT_ANGLE_THRESHOLD = 45


class LegacyFallLogic:
    """Same state and decisions as one FallDetector instance (create a new one where a new detector would be)."""

    def __init__(self, angle_threshold=DEFAULT_ANGLE_THRESHOLD):
        self.angle_threshold = angle_threshold
        self.tracker = LegacyIouTracker()
        self.prev_poses = []               # 모든 사람이 같이 쓰는 자세 기록 (원본과 동일)
        self.fallen_person_ids = set()     # 한 번 낙상 처리된 ID (추적이 끊길 때만 지워짐)
        # 원본은 classify_fall_type을 부르지 않아 항상 모두 False
        self.fall_types = {fall_type: False for fall_type in FALL_TYPES}

    def update(self, now, person_boxes, pose_landmarks):
        """Process one frame.

        now: the time FallDetector would read with time.time() for this frame.
        person_boxes: [(x1, y1, x2, y2), ...] in frame pixels, as detect_person returns them.
        pose_landmarks: one entry per box, in the same order: the landmarks list analyze_pose
            returned for that box, or None when it returned (None, None).
        Returns (falls_detected, fall_data, features): the first two exactly as
        process_frame returns them (without the drawn frame); features is the per-box
        feature dict (or None), for comparison and debugging only.
        """
        if len(pose_landmarks) != len(person_boxes):
            raise ValueError("pose_landmarks must have one entry per person box")

        box_to_id, expired_ids = self.tracker.update(person_boxes, now)
        for person_id in expired_ids:
            if person_id in self.fallen_person_ids:
                self.fallen_person_ids.remove(person_id)

        current_person_ids = list(box_to_id.values())

        falls_detected = False
        fall_data = {
            "person_count": len(person_boxes),
            "fall_detected": False,
            "fall_type": None,
            "person_boxes": person_boxes,
            "critical_points": [],
            "person_ids": current_person_ids,
            "fallen_ids": []
        }

        pose_data = []
        features = []
        for i, box in enumerate(person_boxes):
            person_id = box_to_id.get(i)
            landmarks = pose_landmarks[i]
            # analyze_pose는 관절이 있을 때만 특징을 계산함 (없으면 (None, None))
            pose_features = None if landmarks is None else compute_legacy_features(landmarks, self.prev_poses, now)
            pose_data.append((person_id, landmarks, pose_features))
            features.append(pose_features)

        for person_id, landmarks, pose_features in pose_data:
            if person_id in self.fallen_person_ids:
                continue

            if not landmarks or not pose_features:
                continue

            if is_legacy_fall_posture(pose_features, self.angle_threshold):
                fall_type = None
                for ft, is_active in self.fall_types.items():
                    if is_active:
                        fall_type = ft
                        break

                if not fall_type:
                    fall_type = DEFAULT_FALL_TYPE

                if person_id is not None and person_id not in fall_data["fallen_ids"]:
                    fall_data["fallen_ids"].append(person_id)
                    self.fallen_person_ids.add(person_id)

                fall_data["fall_detected"] = True
                fall_data["fall_type"] = fall_type
                falls_detected = True

        return falls_detected, fall_data, features
