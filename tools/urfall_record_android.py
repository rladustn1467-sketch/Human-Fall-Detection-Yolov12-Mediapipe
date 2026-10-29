"""Pose logs for UR Fall frame folders, made the way the Android app sees people (no YOLO).

Follows the phone pipeline (mobile/.../detect/FallPipeline.process) step by step, in Python:
  1. Silhouette.shrink    long side at most 640 px, width and height multiples of 4
  2. FrameMath.LowLight   gamma lift for dark frames, same thresholds and on/off hysteresis (no CLAHE/denoise)
  3. PoseDetector         MediaPipe Pose Landmarker (pose_landmarker_full.task, the app's model), VIDEO mode,
                          up to 2 people, detection/presence/tracking confidence 0.5, on the whole frame
  4. PoseBridge           person box = landmark extent + 10 % margin, landmarks re-expressed as fractions of it
  5. LegacyFallLogic      the same fall rule as the app (fall_logic, golden-tested against the Java port)
The log has the same format as tools/record_poses.py, so tools/urfall_score.py scores it unchanged
(its "legacy" fields are what LegacyFallLogic decided here, like the app would).

Differences that remain: Android decodes camera frames itself (here: PNG files) and resizes with Bitmap
filtering (here: OpenCV INTER_AREA, only used when a frame is larger than 640 px; UR Fall is 640x480).

Usage (from the project root, inside the detection venv):
  venv\\Scripts\\python.exe tools\\urfall_record_android.py [sequences...] [--force]
Logs go to eval_output/urfall_android/<sequence>.jsonl (ignored by git).
"""
import argparse
import datetime
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fall_logic.legacy import LegacyFallLogic  # noqa: E402
from tools import pose_log  # noqa: E402
from tools.urfall_record import DEFAULT_DATASET, FPS, frame_count, log_frames, sequences  # noqa: E402

DEFAULT_OUT_DIR = os.path.join(ROOT, "eval_output", "urfall_android")
# 앱 빌드가 받아 두는 모델 (mobile/android/app/build.gradle 의 downloadPoseModel). 작업 폴더마다 build/ 가 따로 있음
MODEL_CANDIDATES = [
    os.path.join(ROOT, "mobile", "android", "app", "build", "generated", "poseModel", "pose_landmarker_full.task"),
    os.path.join(os.path.dirname(ROOT), "wt6", "mobile", "android", "app", "build", "generated", "poseModel",
                 "pose_landmarker_full.task"),
]

# Silhouette.MAX_SIDE, PoseBridge.BOX_MARGIN, PoseDetector 설정
MAX_SIDE = 640
BOX_MARGIN = 0.10
NUM_POSES = 2
MIN_CONFIDENCE = 0.5
# FrameMath (utils/low_light.py 와 같은 값)
DARK_THRESHOLD = 80
BRIGHT_RELEASE_THRESHOLD = 95
TARGET_BRIGHTNESS = 110
MIN_GAMMA = 0.45


def shrink(frame, cv2):
    """Silhouette.shrink: long side <= 640, sides floored to multiples of 4."""
    h, w = frame.shape[:2]
    scale = min(1.0, MAX_SIDE / max(w, h))
    tw, th = max(4, int(w * scale) // 4 * 4), max(4, int(h * scale) // 4 * 4)
    if (tw, th) == (w, h):
        return frame
    return cv2.resize(frame, (tw, th), interpolation=cv2.INTER_AREA)


class LowLight:
    """FrameMath.LowLight on an RGB uint8 array (gray weights 0.299/0.587/0.114, truncating gamma table)."""

    def __init__(self, np):
        self.np = np
        self.active = False

    def process(self, rgb):
        np = self.np
        b = float((rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114).mean())
        if not self.active and b < DARK_THRESHOLD:
            self.active = True
        elif self.active and b > BRIGHT_RELEASE_THRESHOLD:
            self.active = False
        if not self.active:
            return rgb, False
        lut = gamma_table(b, np)
        if lut is None:
            return rgb, False
        return lut[rgb], True


def gamma_table(brightness, np):
    """FrameMath.gammaLut: table lifting the mean brightness toward TARGET (None = no change needed)."""
    mean = min(max(brightness, 1.0), 254.0) / 255.0
    gamma = max(MIN_GAMMA, min(1.0, math.log(TARGET_BRIGHTNESS / 255.0) / math.log(mean)))
    if gamma >= 1.0:
        return None
    return (np.power(np.arange(256) / 255.0, gamma) * 255.0).astype(np.uint8)   # Java 처럼 버림


def pose_bridge(poses, width, height):
    """PoseBridge.fromFrame: (boxes in frame pixels, landmarks as fractions of each box)."""
    boxes, landmarks = [], []
    for p in poses:
        if not p:
            continue
        xs = [q[0] * width for q in p]
        ys = [q[1] * height for q in p]
        min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)
        mx, my = (max_x - min_x) * BOX_MARGIN, (max_y - min_y) * BOX_MARGIN
        x1 = int(max(0, math.floor(min_x - mx)))
        y1 = int(max(0, math.floor(min_y - my)))
        x2 = int(min(width, math.ceil(max_x + mx)))
        y2 = int(min(height, math.ceil(max_y + my)))
        if x2 - x1 < 2 or y2 - y1 < 2:
            continue   # 화면 밖으로 거의 다 나간 사람
        boxes.append((x1, y1, x2, y2))
        landmarks.append([((q[0] * width - x1) / (x2 - x1), (q[1] * height - y1) / (y2 - y1), q[2], q[3]) for q in p])
    return boxes, landmarks


def find_model(path):
    for candidate in ([path] if path else MODEL_CANDIDATES):
        if candidate and os.path.exists(candidate):
            return candidate
    raise SystemExit("[android] pose_landmarker_full.task 를 찾을 수 없습니다. 앱을 한 번 빌드하거나 --model 로 지정하세요")


def png_frames(folder, cv2):
    """BGR frames of a UR Fall frame folder, in file-name order."""
    for file_name in sorted(n for n in os.listdir(folder) if n.lower().endswith(".png")):
        bgr = cv2.imread(os.path.join(folder, file_name))
        if bgr is None:
            raise SystemExit(f"[android] 사진을 읽을 수 없음: {file_name}")
        yield bgr


def video_frames(path, cv2):
    """BGR frames of a video file, in order."""
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise SystemExit(f"[android] 영상을 열 수 없음: {path}")
    try:
        while True:
            ok, bgr = cap.read()
            if not ok:
                break
            yield bgr
    finally:
        cap.release()


def record(name, source, frames, fps, out_path, model_path, cv2, np, mp, vision, base_options):
    """frames: BGR frames in order (png_frames or video_frames); fps: their frame rate (frame times = index / fps)."""
    options = vision.PoseLandmarkerOptions(
        base_options=base_options(model_asset_path=model_path),
        running_mode=vision.RunningMode.VIDEO,
        num_poses=NUM_POSES,
        min_pose_detection_confidence=MIN_CONFIDENCE,
        min_pose_presence_confidence=MIN_CONFIDENCE,
        min_tracking_confidence=MIN_CONFIDENCE,
        output_segmentation_masks=False)   # 마스크는 사진용 (관절 결과에는 영향 없음)
    logic = LegacyFallLogic()
    low_light = LowLight(np)
    falls = count = 0
    with vision.PoseLandmarker.create_from_options(options) as landmarker, open(out_path, "w", encoding="utf-8") as fp:
        pose_log.write_line(fp, pose_log.make_header(
            source=source, model=model_path, confidence=MIN_CONFIDENCE, angle_threshold=logic.angle_threshold,
            low_light=True, clock="video", fps=fps, created=datetime.datetime.now().isoformat(timespec="seconds"),
            pipeline="android", coordinates="boxes: frame pixels (landmark extent + 10%); "
                                            "landmarks: Pose Landmarker on the whole frame, as fractions of the box"))
        for index, bgr in enumerate(frames):
            count += 1
            rgb = cv2.cvtColor(shrink(bgr, cv2), cv2.COLOR_BGR2RGB)
            rgb, _ = low_light.process(rgb)
            image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
            result = landmarker.detect_for_video(image, int(round(index * 1000 / fps)))
            poses = [[(lm.x, lm.y, lm.z, lm.visibility if lm.visibility is not None else 0.0) for lm in person]
                     for person in result.pose_landmarks]
            h, w = rgb.shape[:2]
            boxes, landmarks = pose_bridge(poses, w, h)
            now = index / fps
            falls_detected, fall_data, features = logic.update(now, boxes, landmarks)
            pose_log.write_line(fp, pose_log.make_frame(index, now, boxes, landmarks, falls_detected, fall_data, features))
            falls += bool(falls_detected)
    print(f"[android] {name}: {count}프레임, 낙상 판정 프레임 {falls} -> {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Record Android-style pose logs for UR Fall frame folders")
    parser.add_argument("only", nargs="*", help="sequence names (default: all)")
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    parser.add_argument("--model", default=None, help="pose_landmarker_full.task (default: the app build's copy)")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    import cv2
    import mediapipe as mp
    import numpy as np
    from mediapipe.tasks.python import BaseOptions
    from mediapipe.tasks.python import vision

    model_path = find_model(args.model)
    os.makedirs(args.out_dir, exist_ok=True)
    todo = [(n, f) for n, f in sequences(args.dataset) if not args.only or n in args.only]
    missing = set(args.only) - {n for n, _ in todo}
    if missing:
        raise SystemExit(f"[android] rgb/ 에 없는 시퀀스: {', '.join(sorted(missing))}")
    for name, folder in todo:
        out = os.path.join(args.out_dir, f"{name}.jsonl")
        if not args.force and log_frames(out) == frame_count(folder):
            print(f"[android] {name}: 기록 있음, 건너뜀")
            continue
        record(name, folder, png_frames(folder, cv2), FPS, out, model_path, cv2, np, mp, vision, BaseOptions)


if __name__ == "__main__":
    main()
