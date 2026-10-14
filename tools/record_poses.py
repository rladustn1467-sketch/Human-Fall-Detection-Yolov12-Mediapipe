"""Record what the existing FallDetector sees and decides, for replay comparison with fall_logic.

Runs the unchanged models/fall_detector.py (YOLO + MediaPipe) on a video, an image, a folder of
images or a webcam, the same way the dashboard does (low-light correction first, then
FallDetector.process_frame), and writes a pose log (see tools/pose_log.py). No image is saved:
only boxes, landmarks, times and the detector's own results.

How it records without changing the detector:
  - a subclass wraps analyze_pose to keep the landmarks it returned
  - the `time` name inside models.fall_detector is replaced, in this process only, by a clock that
    returns one value per frame, and that value is recorded. (The original reads time.time()
    separately in each call, microseconds apart; within one frame this tool uses one value.)

Usage (from the project root, inside the detection venv):
  venv\\Scripts\\python.exe tools\\record_poses.py VIDEO_OR_IMAGE_OR_FOLDER [--clock video]
  venv\\Scripts\\python.exe tools\\record_poses.py 0              (webcam 0, wall clock)
  then: venv\\Scripts\\python.exe tools\\replay_compare.py eval_output\\<log>.jsonl
Output goes to eval_output/ (ignored by git through eval_output/.gitignore).
"""
import argparse
import datetime
import os
import sys
import time as _time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tools import pose_log  # noqa: E402

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp")
DEFAULT_OUTPUT_DIR = os.path.join(ROOT, "eval_output")
PROGRESS_EVERY = 100  # 이 프레임 수마다 진행 상황 출력


class FrameClock:
    """Stands in for the time module inside models.fall_detector: time() returns the current frame's time."""

    def __init__(self):
        self.now = None

    def time(self):
        return _time.time() if self.now is None else self.now

    def __getattr__(self, name):
        return getattr(_time, name)


def parse_arguments():
    parser = argparse.ArgumentParser(description="Record FallDetector inputs and results to a pose log")
    parser.add_argument("source", help="video file, image file, image folder, or webcam number (e.g. 0)")
    parser.add_argument("--model", default=os.path.join(ROOT, "yolov12n1.pt"),
                        help="YOLO model file (dashboard default: yolov12n1.pt)")
    parser.add_argument("--conf", type=float, default=0.5, help="detection confidence (dashboard default 0.5)")
    parser.add_argument("--angle-threshold", type=float, default=45,
                        help="FallDetector.angle_threshold (dashboard default 45)")
    parser.add_argument("--no-low-light", action="store_true",
                        help="skip LowLightEnhancer (the dashboard always applies it)")
    parser.add_argument("--clock", choices=("wall", "video"), default="wall",
                        help="wall: real time per frame (like the dashboard); "
                             "video: frame number / fps (needs a video file or --fps)")
    parser.add_argument("--fps", type=float, default=None,
                        help="frames per second for --clock video when the file has none, or for images")
    parser.add_argument("--max-frames", type=int, default=None, help="stop after this many frames")
    parser.add_argument("--out", default=None, help="output .jsonl path (default: eval_output/poses_<name>_<time>.jsonl)")
    return parser.parse_args()


def iter_frames(source, cv2):
    """Yield (frame, reported_fps) from a webcam, a video, an image or a folder of images (sorted by name)."""
    if source.isdigit():
        cap = cv2.VideoCapture(int(source))
        if not cap.isOpened() and os.name == "nt":
            cap = cv2.VideoCapture(int(source), cv2.CAP_DSHOW)  # 대시보드와 같은 대체 방식
        yield from _read_capture(cap, source)
        return
    if os.path.isdir(source):
        names = sorted(n for n in os.listdir(source) if n.lower().endswith(IMAGE_EXTENSIONS))
        paths = [os.path.join(source, n) for n in names]
    elif source.lower().endswith(IMAGE_EXTENSIONS):
        paths = [source]
    else:
        yield from _read_capture(cv2.VideoCapture(source), source)
        return
    for path in paths:
        frame = cv2.imread(path)
        if frame is None:
            print(f"[record] 사진을 읽을 수 없어 건너뜀: {path}")
            continue
        yield frame, None


def _read_capture(cap, source):
    if not cap.isOpened():
        raise SystemExit(f"[record] 영상을 열 수 없습니다: {source}")
    import cv2
    fps = cap.get(cv2.CAP_PROP_FPS) or None
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            yield frame, fps
    finally:
        cap.release()


def main():
    args = parse_arguments()

    # 무거운 라이브러리는 인자 확인 뒤에 불러옴
    import cv2
    from models import fall_detector as fd_mod
    from utils.low_light import LowLightEnhancer

    class RecordingFallDetector(fd_mod.FallDetector):
        """Unchanged FallDetector that also keeps what analyze_pose returned in this frame."""

        def analyze_pose(self, frame, person_box):
            landmarks, pose_features = super().analyze_pose(frame, person_box)
            self.recorded_poses.append((landmarks, pose_features))
            return landmarks, pose_features

    clock = FrameClock()
    original_time = fd_mod.time
    fd_mod.time = clock  # 이 프로세스 안에서만: 감지기 코드의 time.time()이 프레임 시각을 돌려줌

    detector = RecordingFallDetector(model_path=args.model, confidence=args.conf)
    detector.angle_threshold = args.angle_threshold  # 대시보드 _ensure_fall_detector와 같은 방식
    detector.recorded_poses = []
    low_light = None if args.no_low_light else LowLightEnhancer()

    out_path = args.out
    if not out_path:
        os.makedirs(DEFAULT_OUTPUT_DIR, exist_ok=True)
        name = "webcam" + args.source if args.source.isdigit() else os.path.splitext(os.path.basename(args.source.rstrip("/\\")))[0]
        out_path = os.path.join(DEFAULT_OUTPUT_DIR, f"poses_{name}_{datetime.datetime.now():%Y%m%d_%H%M%S}.jsonl")

    count = falls = 0
    try:
        with open(out_path, "w", encoding="utf-8") as fp:
            header_written = False
            for index, (frame, source_fps) in enumerate(iter_frames(args.source, cv2)):
                if args.max_frames is not None and index >= args.max_frames:
                    break
                fps = args.fps or source_fps
                if not header_written:
                    if args.clock == "video" and not fps:
                        raise SystemExit("[record] --clock video 에는 영상의 FPS 정보나 --fps 값이 필요합니다")
                    pose_log.write_line(fp, pose_log.make_header(
                        source=args.source, model=args.model, confidence=args.conf,
                        angle_threshold=args.angle_threshold, low_light=low_light is not None,
                        clock=args.clock, fps=fps, created=datetime.datetime.now().isoformat(timespec="seconds"),
                        coordinates="boxes: frame pixels; landmarks: MediaPipe Pose on frame[y1:y2, x1:x2] (crop-normalized)"))
                    header_written = True

                clock.now = index / fps if args.clock == "video" else _time.time()
                if low_light is not None:
                    frame, _ = low_light.process(frame)
                detector.recorded_poses = []
                _, falls_detected, fall_data = detector.process_frame(frame)

                boxes = fall_data["person_boxes"]
                if len(detector.recorded_poses) != len(boxes):
                    raise SystemExit(f"[record] 프레임 {index}: 박스 {len(boxes)}개, 자세 {len(detector.recorded_poses)}개 - "
                                     "감지기 호출 순서가 예상과 다릅니다. 기록을 멈춥니다")
                landmarks = [lms for lms, _ in detector.recorded_poses]
                features = [feats for _, feats in detector.recorded_poses]
                pose_log.write_line(fp, pose_log.make_frame(index, clock.now, boxes, landmarks,
                                                            falls_detected, fall_data, features))
                fp.flush()
                count += 1
                falls += bool(falls_detected)
                if count % PROGRESS_EVERY == 0:
                    print(f"[record] {count}프레임 기록 (낙상 판정 프레임 {falls})")
    finally:
        fd_mod.time = original_time

    print(f"[record] 완료: {count}프레임, 낙상 판정 프레임 {falls} -> {out_path}")
    if count == 0:
        print("[record] 기록된 프레임이 없습니다")


if __name__ == "__main__":
    main()
