import time

import cv2
import numpy as np
import mediapipe as mp

# ---- 조정 가능한 설정값 ----
# 평균 밝기(그레이스케일 0~255)가 이 값보다 낮으면 보정을 시작
DARK_THRESHOLD = 80
# 보정 중에는 평균 밝기가 이 값을 넘어야 보정을 해제 (기준값 근처에서 켜짐/꺼짐 반복 방지)
BRIGHT_RELEASE_THRESHOLD = 95
# 이보다 어두우면 보정 한계 경고 (영상에 남은 정보가 거의 없음)
TOO_DARK_THRESHOLD = 20
# 밝기 표준편차가 이보다 낮으면 명암 정보가 거의 없는 영상으로 판단
MIN_CONTRAST_STD = 8
# 감마 보정이 목표로 하는 평균 밝기
TARGET_BRIGHTNESS = 110
# 감마 하한 (작을수록 강하게 밝힘, 1.0이면 감마 보정 없음)
MIN_GAMMA = 0.45
# CLAHE 대비 제한 (클수록 대비가 강해지지만 노이즈도 강조됨)
CLAHE_CLIP_LIMIT = 2.0
CLAHE_TILE_GRID = (8, 8)
# 밝히기 전에 적용하는 NLmeans 노이즈 제거 (어두운 영상에서만 실행)
# 강도: 클수록 노이즈가 더 지워지지만 윤곽도 뭉개짐 (0이면 노이즈 제거 안 함)
DENOISE_STRENGTH = 7
# 노이즈 제거를 수행할 해상도 비율: 작을수록 빠르지만 세부가 줄어듦 (0.35에서 약 66ms/프레임)
DENOISE_SCALE = 0.35
DENOISE_TEMPLATE_WINDOW = 3
DENOISE_SEARCH_WINDOW = 9
# 보정 전후 관절 인식 비교 로그 주기(초). 보정이 켜져 있을 때만 기록
COMPARE_LOG_INTERVAL = 5.0
# 비교 로그에서 확인할 최대 인원 (처리 시간 제한)
COMPARE_MAX_PEOPLE = 2


def measure_brightness(frame):
    """Return (mean, std) of the frame's grayscale brightness, measured on a small copy."""
    h, w = frame.shape[:2]
    scale = 160 / max(w, 1)
    small = cv2.resize(frame, (160, max(1, int(h * scale))), interpolation=cv2.INTER_AREA) if scale < 1 else frame
    mean, std = cv2.meanStdDev(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY))
    return float(mean[0][0]), float(std[0][0])


class LowLightEnhancer:
    """Brighten and add contrast to dark frames only; bright frames pass through untouched."""

    def __init__(self):
        self.active = False
        self.too_dark = False
        self._clahe = cv2.createCLAHE(clipLimit=CLAHE_CLIP_LIMIT, tileGridSize=CLAHE_TILE_GRID)

    def process(self, frame):
        """Return (frame_for_detection, info). The input frame is never modified."""
        brightness, contrast = measure_brightness(frame)

        # 히스테리시스로 보정 켜기/끄기 결정
        if not self.active and brightness < DARK_THRESHOLD:
            self.active = True
            print(f"[low-light] 어두운 영상 감지 (평균 밝기 {brightness:.0f} < {DARK_THRESHOLD}) - 보정 시작")
        elif self.active and brightness > BRIGHT_RELEASE_THRESHOLD:
            self.active = False
            print(f"[low-light] 밝기 회복 (평균 밝기 {brightness:.0f} > {BRIGHT_RELEASE_THRESHOLD}) - 보정 해제")

        too_dark = self.active and (brightness < TOO_DARK_THRESHOLD or contrast < MIN_CONTRAST_STD)
        if too_dark != self.too_dark:
            self.too_dark = too_dark
            if too_dark:
                print(f"[low-light] 경고: 영상이 너무 어두움 (밝기 {brightness:.0f}, 명암 편차 {contrast:.1f}). "
                      f"보정해도 관절 인식이 어려울 수 있습니다 - 조명을 확인하세요")
            else:
                print("[low-light] 보정 한계 상태 해제")

        info = {
            "brightness": brightness,
            "contrast": contrast,
            "enhanced": self.active,
            "too_dark": too_dark,
            "brightness_after": brightness,
        }
        if not self.active:
            return frame, info

        enhanced = self._enhance(frame, brightness)
        info["brightness_after"], _ = measure_brightness(enhanced)
        return enhanced, info

    def _enhance(self, frame, brightness):
        # 1) 밝히기 전에 센서 노이즈 제거 (밝히면 노이즈도 함께 증폭되므로 먼저 제거)
        out = self._denoise(frame) if DENOISE_STRENGTH > 0 else frame

        # 2) 감마 보정: 현재 평균 밝기를 목표 밝기 쪽으로 끌어올림 (하한 MIN_GAMMA로 과보정 방지)
        mean = min(max(brightness, 1.0), 254.0) / 255.0
        gamma = np.log(TARGET_BRIGHTNESS / 255.0) / np.log(mean)
        gamma = float(np.clip(gamma, MIN_GAMMA, 1.0))
        if gamma < 1.0:
            lut = ((np.arange(256) / 255.0) ** gamma * 255.0).astype(np.uint8)
            out = cv2.LUT(out, lut)

        # 3) CLAHE: 밝기(L) 채널에만 적용해 색 왜곡 없이 국소 대비 향상
        lab = cv2.cvtColor(out, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        lab = cv2.merge((self._clahe.apply(l), a, b))
        return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

    def _denoise(self, frame):
        # 전체 해상도 NLmeans는 너무 느리므로 축소한 영상에서 노이즈를 제거한 뒤 원래 크기로 복원
        h, w = frame.shape[:2]
        small = cv2.resize(frame, None, fx=DENOISE_SCALE, fy=DENOISE_SCALE, interpolation=cv2.INTER_AREA)
        small = cv2.fastNlMeansDenoisingColored(small, None, DENOISE_STRENGTH, DENOISE_STRENGTH,
                                                DENOISE_TEMPLATE_WINDOW, DENOISE_SEARCH_WINDOW)
        return cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)


class JointCompareLogger:
    """Periodically log whether MediaPipe finds joints on the original vs. the enhanced frame.

    Uses its own static Pose instance so the detector's tracking state is not disturbed.
    """

    def __init__(self):
        self._pose = None
        self._last_log = 0.0

    def maybe_log(self, original, enhanced, person_boxes, info):
        if not info.get("enhanced"):
            return
        now = time.time()
        if now - self._last_log < COMPARE_LOG_INTERVAL:
            return
        self._last_log = now

        head = (f"[low-light] 밝기 {info['brightness']:.0f} -> {info['brightness_after']:.0f}"
                f"{' (보정 한계)' if info.get('too_dark') else ''}")
        boxes = list(person_boxes)[:COMPARE_MAX_PEOPLE]
        if not boxes:
            print(f"{head} | 보정 영상에서 사람 미검출 - 관절 비교 불가")
            return

        if self._pose is None:
            self._pose = mp.solutions.pose.Pose(static_image_mode=True, model_complexity=1,
                                                min_detection_confidence=0.5)
        orig_ok = enh_ok = 0
        orig_vis, enh_vis = [], []
        for box in boxes:
            for img, vis in ((original, orig_vis), (enhanced, enh_vis)):
                found, visibility = self._detect_joints(img, box)
                vis.append(visibility)
                if found:
                    if img is original:
                        orig_ok += 1
                    else:
                        enh_ok += 1
        n = len(boxes)
        print(f"{head} | 관절 인식 원본 {orig_ok}/{n} (가시성 {np.mean(orig_vis):.2f}), "
              f"보정 {enh_ok}/{n} (가시성 {np.mean(enh_vis):.2f})")

    def _detect_joints(self, frame, box):
        x1, y1, x2, y2 = [int(v) for v in box]
        crop = frame[max(0, y1):y2, max(0, x1):x2]
        if crop.size == 0:
            return False, 0.0
        results = self._pose.process(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
        if not results.pose_landmarks:
            return False, 0.0
        return True, float(np.mean([lm.visibility for lm in results.pose_landmarks.landmark]))


def draw_debug_overlay(display, original, info):
    """Draw a small original-frame inset and brightness info onto the display frame (in place)."""
    h, w = display.shape[:2]
    tw, th = w // 4, h // 4
    thumb = cv2.resize(original, (tw, th), interpolation=cv2.INTER_AREA)
    x0, y0 = w - tw - 10, 10
    display[y0:y0 + th, x0:x0 + tw] = thumb
    cv2.rectangle(display, (x0, y0), (x0 + tw, y0 + th), (255, 255, 255), 1)
    cv2.putText(display, "ORIGINAL", (x0 + 4, y0 + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)

    if info.get("enhanced"):
        text = f"Light {info['brightness']:.0f} -> {info['brightness_after']:.0f} (CLAHE ON)"
        color = (0, 255, 255)
    else:
        text = f"Light {info['brightness']:.0f} (no correction)"
        color = (0, 255, 0)
    cv2.putText(display, text, (max(0, x0 - 140), y0 + th + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
    if info.get("too_dark"):
        cv2.putText(display, "TOO DARK - limited recovery", (max(0, x0 - 140), y0 + th + 46),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 255), 2)
