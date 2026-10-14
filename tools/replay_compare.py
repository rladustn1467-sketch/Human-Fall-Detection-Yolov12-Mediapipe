"""Replay a pose log through fall_logic.LegacyFallLogic and compare with the recorded FallDetector results.

Needs only the standard library and fall_logic (no model, camera or GPU).

Usage (from the project root):
  venv\\Scripts\\python.exe tools\\replay_compare.py eval_output\\<log>.jsonl [--show 20]
Exit code: 0 identical, 1 differences found, 2 the file could not be read.
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tools import pose_log  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Compare fall_logic (legacy mode) with a recorded FallDetector run")
    parser.add_argument("log", help="pose log written by tools/record_poses.py")
    parser.add_argument("--show", type=int, default=20, help="how many differing frames to print")
    args = parser.parse_args()

    try:
        header, frames = pose_log.read_log(args.log)
    except (OSError, ValueError) as e:
        print(f"[replay] 기록을 읽을 수 없습니다: {e}")
        return 2

    result = pose_log.replay(header, frames)
    print(f"[replay] {args.log}")
    print(f"  원본: {header.get('source')} / 시각 기준: {header.get('clock')} / angle_threshold: {header['angle_threshold']}")
    print(f"  프레임 {result['frames']}개, 낙상 판정 프레임: 기존 {result['legacy_fall_frames']} / 새 모듈 {result['module_fall_frames']}")
    if not result["mismatches"]:
        print("  결과: 모든 프레임이 일치합니다")
        return 0
    print(f"  결과: {len(result['mismatches'])}개 프레임이 다릅니다 (앞에서 {args.show}개 표시)")
    for index, diffs in result["mismatches"][:args.show]:
        print(f"  - 프레임 {index}:")
        for diff in diffs:
            print(f"      {diff}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
