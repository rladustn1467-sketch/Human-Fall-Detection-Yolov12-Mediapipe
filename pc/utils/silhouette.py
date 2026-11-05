import cv2
import numpy as np
import mediapipe as mp

# 서버로 보내는 이미지의 긴 변 최대 길이 (메모리·전송량 절약)
MAX_SIDE = 640
JPEG_QUALITY = 80
# 사람 영역을 칠할 색 (BGR)
SILHOUETTE_COLOR = (60, 60, 60)
# 배경 블러 강도 (가우시안 sigma, 값이 클수록 더 흐림)
BACKGROUND_BLUR_SIGMA = 4
# 사람 박스 주변 여유 비율 (팔다리가 박스 밖으로 나가는 경우 대비)
BOX_MARGIN = 0.15
# 분할 마스크가 잘라낸 영역에서 차지하는 비율이 이 범위를 벗어나면 실패로 판단
MIN_MASK_RATIO = 0.05
MAX_MASK_RATIO = 0.90


def shrink_frame(frame, person_boxes, max_side=MAX_SIDE):
    """Downscale a frame (and its person boxes) so the long side is at most max_side.

    Always returns a new array, so the caller can keep it after the original
    frame is reused or released.
    """
    h, w = frame.shape[:2]
    scale = min(1.0, max_side / max(h, w))
    if scale < 1.0:
        small = cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    else:
        small = frame.copy()
    boxes = [tuple(int(v * scale) for v in box) for box in person_boxes]
    return small, boxes


class SilhouetteRenderer:
    """Hide every detected person behind a solid silhouette and blur the background.

    Not thread-safe: create and use it from a single (worker) thread.
    """

    def __init__(self):
        self._pose = None

    def _get_pose(self):
        # 처음 사용할 때만 모델을 로드 (감지용 Pose와는 별도 인스턴스)
        if self._pose is None:
            self._pose = mp.solutions.pose.Pose(
                static_image_mode=True,
                model_complexity=1,
                enable_segmentation=True,
                min_detection_confidence=0.5
            )
        return self._pose

    def render(self, frame, person_boxes):
        """Return a silhouette JPEG as bytes, or None if any person could not be masked.

        The original frame is never encoded; on any failure nothing is returned.
        """
        if frame is None or not person_boxes:
            return None

        h, w = frame.shape[:2]
        mask = np.zeros((h, w), dtype=np.uint8)
        pose = self._get_pose()

        for x1, y1, x2, y2 in person_boxes:
            mx = int((x2 - x1) * BOX_MARGIN)
            my = int((y2 - y1) * BOX_MARGIN)
            cx1, cy1 = max(0, x1 - mx), max(0, y1 - my)
            cx2, cy2 = min(w, x2 + mx), min(h, y2 + my)
            if cx2 - cx1 < 10 or cy2 - cy1 < 10:
                return None

            rgb_crop = cv2.cvtColor(frame[cy1:cy2, cx1:cx2], cv2.COLOR_BGR2RGB)
            results = pose.process(rgb_crop)
            if results.segmentation_mask is None:
                return None

            person_mask = results.segmentation_mask > 0.5
            ratio = float(person_mask.mean())
            if not (MIN_MASK_RATIO <= ratio <= MAX_MASK_RATIO):
                return None
            mask[cy1:cy2, cx1:cx2][person_mask] = 255

        # 분할 경계에서 신체 가장자리가 새어 나오지 않도록 마스크를 약간 넓힘
        mask = cv2.dilate(mask, np.ones((9, 9), np.uint8))

        # 출력은 블러된 배경에서 시작하므로 원본 픽셀은 그대로 남지 않음
        output = cv2.GaussianBlur(frame, (0, 0), BACKGROUND_BLUR_SIGMA)
        output[mask > 0] = SILHOUETTE_COLOR

        ok, encoded = cv2.imencode(".jpg", output, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        if not ok:
            return None
        return encoded.tobytes()
