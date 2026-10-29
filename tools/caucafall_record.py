"""Pose logs for the CAUCAFall videos (list from tools/caucafall_prepare.py: eval_output/caucafall/videos.csv).

  --pipeline android  the Android app's way (tools/urfall_record_android.record on the video frames)
  --pipeline pc       the unchanged PC detector (tools/record_poses.py on the video, video clock from its fps)
Frame times are index / fps of the video (20 fps). Logs: eval_output/caucafall/<pipeline>/<sequence>.jsonl.
Already complete logs are skipped (--force records again).

Usage: venv\\Scripts\\python.exe tools\\caucafall_record.py --pipeline android
"""
import argparse
import csv
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tools.urfall_record import log_frames  # noqa: E402

VIDEOS = os.path.join(os.path.dirname(ROOT), "datasets", "caucafall", "videos")
OUT = os.path.join(ROOT, "eval_output", "caucafall")


def main():
    parser = argparse.ArgumentParser(description="Record pose logs for the CAUCAFall videos")
    parser.add_argument("--pipeline", choices=("android", "pc"), required=True)
    parser.add_argument("only", nargs="*", help="sequence names (default: all)")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    with open(os.path.join(OUT, "videos.csv"), encoding="utf-8") as fp:
        videos = [v for v in csv.DictReader(fp) if not args.only or v["sequence"] in args.only]
    out_dir = os.path.join(OUT, args.pipeline)
    os.makedirs(out_dir, exist_ok=True)

    if args.pipeline == "android":
        import cv2
        import mediapipe as mp
        import numpy as np
        from mediapipe.tasks.python import BaseOptions, vision
        from tools import urfall_record_android as ua
        model = ua.find_model(None)
    for v in videos:
        out = os.path.join(out_dir, f"{v['sequence']}.jsonl")
        path = os.path.join(VIDEOS, v["video"])
        if not args.force and log_frames(out) == int(v["frames"]):
            print(f"[caucafall] {v['sequence']}: 기록 있음, 건너뜀", flush=True)
            continue
        if args.pipeline == "android":
            ua.record(v["sequence"], path, ua.video_frames(path, cv2), float(v["fps"]), out, model,
                      cv2, np, mp, vision, BaseOptions)
        else:
            subprocess.run([sys.executable, os.path.join(ROOT, "tools", "record_poses.py"), path,
                            "--clock", "video", "--out", out], cwd=ROOT, check=True)
        got = log_frames(out)
        if got != int(v["frames"]):
            print(f"[caucafall] {v['sequence']}: 프레임 수가 다름 (영상 정보 {v['frames']}, 읽은 프레임 {got})", flush=True)


if __name__ == "__main__":
    main()
