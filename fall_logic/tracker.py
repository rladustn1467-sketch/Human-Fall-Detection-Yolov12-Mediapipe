"""IoU person tracker, reproducing FallDetector.track_persons (models/fall_detector.py:575-659).

Known issues kept on purpose (legacy reproduction):
  - matching is not one-to-one: two boxes in the same frame can get the same ID
  - a tracker created earlier in the same frame is a match candidate for later boxes
  - expiry is checked only when trackers already existed at the start of the call
The only change is that the current time is passed in (now) instead of read from time.time().
"""

# 같은 사람으로 볼 최소 IoU (원본 값)
LEGACY_MIN_IOU = 0.3
# 이 시간(초) 넘게 안 보이면 추적 정보 삭제 (원본 값)
LEGACY_EXPIRE_SECONDS = 5.0


def _iou_ratio(intersection, union):
    # 원본의 박스 좌표는 numpy 정수라 0으로 나누면 예외 대신 nan/inf가 됨 (경고만 출력).
    # nan은 어떤 비교에서도 False라 매칭되지 않으므로 같은 결과가 되게 nan을 돌려줌.
    if union == 0:
        return float("nan") if intersection == 0 else float("inf") if intersection > 0 else float("-inf")
    return intersection / union


class LegacyIouTracker:
    def __init__(self):
        self.next_person_id = 1
        self.person_trackers = {}  # {id: {'box', 'last_seen', 'is_fallen'}}

    def update(self, person_boxes, now):
        """Assign IDs to this frame's boxes.

        Returns (box_to_id, expired_ids): box_to_id maps box index -> person ID (same as the
        original return value); expired_ids are the IDs removed this call, which the caller
        must also remove from its fallen set (the original does that inside track_persons).
        """
        current_time = now
        current_boxes = person_boxes
        box_to_id = {}

        if not self.person_trackers:
            for i, box in enumerate(current_boxes):
                self.person_trackers[self.next_person_id] = {
                    'box': box,
                    'last_seen': current_time,
                    'is_fallen': False
                }
                box_to_id[i] = self.next_person_id
                self.next_person_id += 1
            return box_to_id, []

        for i, current_box in enumerate(current_boxes):
            best_iou = LEGACY_MIN_IOU
            best_id = None

            for person_id, tracker_info in self.person_trackers.items():
                previous_box = tracker_info['box']

                x1 = max(current_box[0], previous_box[0])
                y1 = max(current_box[1], previous_box[1])
                x2 = min(current_box[2], previous_box[2])
                y2 = min(current_box[3], previous_box[3])

                if x2 < x1 or y2 < y1:
                    continue

                current_area = (current_box[2] - current_box[0]) * (current_box[3] - current_box[1])
                previous_area = (previous_box[2] - previous_box[0]) * (previous_box[3] - previous_box[1])
                intersection = (x2 - x1) * (y2 - y1)
                union = current_area + previous_area - intersection

                iou = _iou_ratio(intersection, union)

                if iou > best_iou:
                    best_iou = iou
                    best_id = person_id

            if best_id is not None:
                box_to_id[i] = best_id
                self.person_trackers[best_id]['box'] = current_box
                self.person_trackers[best_id]['last_seen'] = current_time
            else:
                self.person_trackers[self.next_person_id] = {
                    'box': current_box,
                    'last_seen': current_time,
                    'is_fallen': False
                }
                box_to_id[i] = self.next_person_id
                self.next_person_id += 1

        ids_to_remove = []
        for person_id, tracker_info in self.person_trackers.items():
            if current_time - tracker_info['last_seen'] > LEGACY_EXPIRE_SECONDS:
                ids_to_remove.append(person_id)

        for person_id in ids_to_remove:
            del self.person_trackers[person_id]

        return box_to_id, ids_to_remove
