"""Prepare CAUCAFall (videos in humanfall/datasets/caucafall) for the same evaluation as UR Fall.

Writes to eval_output/caucafall/:
  videos.csv   sequence, video (path under datasets/caucafall/videos), subject, activity, kind, frames, fps
               sequence names follow the UR Fall convention so the other tools work unchanged:
               fall-cfS01-forward, adl-cfS01-walk, ... (kind = the "fall"/"adl" prefix)
  labels.csv   sequence, frame (1-based), label, omnifall_class — one row per video frame
               label like UR Fall: 0 = falling (OmniFall "fall"), 1 = on the ground after the fall ("fallen"),
               -1 = everything else; the frame's time is (frame - 1) / fps
  adl_tags.csv everyday-action segments of the adl- sequences, in the format of the UR Fall adl_tags.csv,
               taken from the OmniFall classes (walk, sit_down, sitting, kneel_down, kneeling, stand_up, ...)
  split.csv    tune/test by SUBJECT (a person is on one side only): 6 subjects tune, 4 test, fixed seed
Labels: OmniFall (labels-train.parquet, dataset "caucafall", CC BY-NC 4.0, internal evaluation only).

Usage: venv\\Scripts\\python.exe tools\\caucafall_prepare.py   (run in its own process: pyarrow is imported)
"""
import csv
import json
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(os.path.dirname(ROOT), "datasets", "caucafall")
LABELS = os.path.join(os.path.dirname(ROOT), "datasets", "omnifall_labels", "labels-train.parquet")
OUT = os.path.join(ROOT, "eval_output", "caucafall")
# OmniFall README 의 클래스 순서 (label 번호)
CLASSES = ("walk", "fall", "fallen", "sit_down", "sitting", "lie_down", "lying", "stand_up", "standing", "other",
           "kneel_down", "kneeling", "squat_down", "squatting", "crawl", "jump")
ACTIVITY_SHORT = {"Fall backwards": "backwards", "Fall forward": "forward", "Fall left": "left", "Fall right": "right",
                  "Fall sitting": "sitting", "Hop": "hop", "Kneel": "kneel", "Pick up object": "pickup",
                  "Sit down": "sitdown", "Walk": "walk"}
# OmniFall 클래스 → UR Fall adl_tags 의 동작 이름 (tools/urfall_distributions.ACTION_GROUP 에 있는 것)
CLASS_TO_ACTION = {"walk": "walk", "standing": "stand", "other": "stand", "jump": "stand", "sit_down": "sit_down",
                   "sitting": "sit_chair", "stand_up": "get_up", "kneel_down": "kneel_floor", "kneeling": "kneel_floor",
                   "squat_down": "squat", "squatting": "squat", "lie_down": "lie_down_floor", "lying": "lie_floor",
                   "crawl": "kneel_floor"}
SEED = 20261029
TUNE_SUBJECTS = 6


# 일상 동작 영상에서 OmniFall 이 "other" 로 둔 구간: 영상의 동작으로 정함 (무릎 꿇기 영상은 대부분 "other")
OTHER_BY_ACTIVITY = {"hop": "stand", "kneel": "kneel_floor", "pickup": "bend", "sitdown": "stand", "walk": "walk"}


def frame_label(segments, t, kind="fall"):
    """(label, class) at time t from [(start, end, class)]; the last segment that contains t wins.
    In fall videos the time on the ground after the fall is "fallen", or in a few videos "lying"/"lie_down"
    (FallBackwardsS1, S4): all of them are label 1."""
    cls = None
    for s, e, c in segments:
        if s <= t < e:
            cls = c
    if cls is None and segments and t >= max(e for _, e, _ in segments):
        cls = max(segments, key=lambda x: x[1])[2]       # 영상 끝 몇 프레임: 마지막 구간을 이어 씀
    on_ground = {"fall": 0, "fallen": 1, "lying": 1, "lie_down": 1} if kind == "fall" else {}
    return on_ground.get(cls, -1), cls or ""


def tags_from_frames(seq, rows):
    """Consecutive frames with the same action → [(seq, start, end, action, class)]."""
    activity = seq.split("-")[-1]
    out, cur = [], None
    for r in rows:
        cls = r["omnifall_class"]
        action = OTHER_BY_ACTIVITY.get(activity, "stand") if cls in ("other", "") else CLASS_TO_ACTION.get(cls, "stand")
        if cur and cur[3] == action and r["frame"] == cur[2] + 1:
            cur[2] = r["frame"]
        else:
            if cur:
                out.append(tuple(cur))
            cur = [seq, r["frame"], r["frame"], action, r["omnifall_class"]]
    if cur:
        out.append(tuple(cur))
    return out


def main():
    import cv2
    import pyarrow.parquet as pq
    sys.stdout.reconfigure(encoding="utf-8")
    os.makedirs(OUT, exist_ok=True)
    segs = {}
    for r in pq.read_table(LABELS).to_pylist():
        if r["dataset"] == "caucafall":
            segs.setdefault(r["path"].split("/")[-1], []).append((r["start"], r["end"], CLASSES[r["label"]]))
    with open(os.path.join(DATA, "manifest.json"), encoding="utf-8") as fp:
        manifest = json.load(fp)

    videos, labels, tags = [], [], []
    for m in sorted(manifest, key=lambda x: x["file"]):
        subject = int(m["subject"].split(".")[-1])
        act = ACTIVITY_SHORT[m["activity"]]
        kind = "fall" if m["activity"].startswith("Fall") else "adl"
        seq = f"{kind}-cfS{subject:02d}-{act}"
        name = os.path.splitext(os.path.basename(m["file"]))[0]
        cap = cv2.VideoCapture(os.path.join(DATA, "videos", m["file"]))
        frames, fps = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), cap.get(cv2.CAP_PROP_FPS)
        cap.release()
        videos.append({"sequence": seq, "video": m["file"], "subject": subject, "activity": m["activity"],
                       "kind": kind, "frames": frames, "fps": fps})
        rows = []
        for i in range(frames):
            lab, cls = frame_label(segs.get(name, []), i / fps, kind)
            rows.append({"sequence": seq, "frame": i + 1, "label": lab, "omnifall_class": cls})
        labels += rows
        if kind == "adl":
            tags += tags_from_frames(seq, rows)

    def write(name, fieldnames, items):
        with open(os.path.join(OUT, name), "w", encoding="utf-8", newline="") as fp:
            w = csv.writer(fp) if not isinstance(items[0], dict) else csv.DictWriter(fp, fieldnames=fieldnames)
            if isinstance(items[0], dict):
                w.writeheader()
                w.writerows(items)
            else:
                w.writerow(fieldnames)
                w.writerows(items)

    write("videos.csv", list(videos[0]), videos)
    write("labels.csv", list(labels[0]), labels)
    write("adl_tags.csv", ["sequence", "start_frame", "end_frame", "action", "omnifall_class"], tags)

    subjects = sorted({v["subject"] for v in videos})
    tune = set(random.Random(SEED).sample(subjects, TUNE_SUBJECTS))
    split = [[v["sequence"], f"{v['kind']}_cf", "tune" if v["subject"] in tune else "test", SEED, v["subject"]] for v in videos]
    write("split.csv", ["sequence", "group", "split", "seed", "subject"], split)

    falls = [v for v in videos if v["kind"] == "fall"]
    no_fall_label = [v["sequence"] for v in falls if not any(r["label"] == 0 for r in labels if r["sequence"] == v["sequence"])]
    print(f"영상 {len(videos)}개 (낙상 {len(falls)}, 일상 {len(videos) - len(falls)}), 프레임 {len(labels)}개")
    print(f"찾는 용 사람: {sorted(tune)}, 시험용 사람: {sorted(set(subjects) - tune)}")
    print(f"정답에 '넘어지는 중'이 없는 낙상 영상: {no_fall_label or '없음'}")
    print(f"저장: {OUT}")


if __name__ == "__main__":
    main()
