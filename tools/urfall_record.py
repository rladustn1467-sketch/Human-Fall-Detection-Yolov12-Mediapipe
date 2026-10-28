"""Turn UR Fall frame folders (PNG per frame) into pose logs, one log per sequence.

Runs the unchanged tools/record_poses.py (FallDetector: YOLO + MediaPipe, low-light correction like
the dashboard) on each folder datasets/urfall/rgb/<sequence>-cam0-rgb, reading the frames in file-name
order, with a video clock of 30 fps (UR Fall cam0 frame rate), so times in the log are frame times.
One process per sequence: every sequence starts with a fresh detector (no state carried over).

Usage (from the project root, inside the detection venv):
  venv\\Scripts\\python.exe tools\\urfall_record.py                 (all sequences in rgb/, skips finished logs)
  venv\\Scripts\\python.exe tools\\urfall_record.py fall-01 adl-21  (only these)
  venv\\Scripts\\python.exe tools\\urfall_record.py --force          (record again)
Logs go to eval_output/urfall/<sequence>.jsonl (ignored by git).
"""
import argparse
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 데이터셋은 저장소 밖 (humanfall/datasets/urfall): 작업 폴더가 여러 개여도 같은 곳을 씀
DEFAULT_DATASET = os.path.join(os.path.dirname(ROOT), "datasets", "urfall")
DEFAULT_OUT_DIR = os.path.join(ROOT, "eval_output", "urfall")
FPS = 30  # UR Fall cam0 (Kinect RGB) 프레임 속도
FOLDER_SUFFIX = "-cam0-rgb"


def sequences(dataset):
    """[(sequence name, frame folder)] sorted by name, e.g. ("fall-01", ".../rgb/fall-01-cam0-rgb")."""
    rgb = os.path.join(dataset, "rgb")
    out = []
    for name in sorted(os.listdir(rgb)):
        folder = os.path.join(rgb, name)
        if os.path.isdir(folder) and name.endswith(FOLDER_SUFFIX):
            out.append((name[:-len(FOLDER_SUFFIX)], folder))
    return out


def frame_count(folder):
    return sum(1 for n in os.listdir(folder) if n.lower().endswith(".png"))


def log_frames(path):
    """Number of frame lines in an existing log (0 when missing)."""
    if not os.path.exists(path):
        return 0
    with open(path, encoding="utf-8") as fp:
        return sum(1 for line in fp if '"type": "frame"' in line)


def main():
    parser = argparse.ArgumentParser(description="Record pose logs for UR Fall frame folders")
    parser.add_argument("only", nargs="*", help="sequence names to record (default: all), e.g. fall-01 adl-21")
    parser.add_argument("--dataset", default=DEFAULT_DATASET, help="UR Fall folder with rgb/ and features/")
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    parser.add_argument("--force", action="store_true", help="record again even when a complete log exists")
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    todo = [(n, f) for n, f in sequences(args.dataset) if not args.only or n in args.only]
    missing = set(args.only) - {n for n, _ in todo}
    if missing:
        raise SystemExit(f"[urfall] rgb/ 에 없는 시퀀스: {', '.join(sorted(missing))}")
    for name, folder in todo:
        out = os.path.join(args.out_dir, f"{name}.jsonl")
        frames = frame_count(folder)
        if not args.force and log_frames(out) == frames:
            print(f"[urfall] {name}: 기록 있음 ({frames}프레임), 건너뜀")
            continue
        print(f"[urfall] {name}: {frames}프레임 기록 시작")
        subprocess.run([sys.executable, os.path.join(ROOT, "tools", "record_poses.py"), folder,
                        "--clock", "video", "--fps", str(FPS), "--out", out], cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
