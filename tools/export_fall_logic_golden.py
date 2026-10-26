"""Export golden cases from fall_logic.LegacyFallLogic for the Android (Java) port's unit tests.

The Java port (mobile/android/app/src/main/java/com/humanfall/app/detect/) must give the same decisions and
features as the Python legacy logic for the same inputs (person boxes + crop-normalized landmarks + times).
This writes sequences of frames with their expected outputs; the JVM test replays them.

Inputs are synthetic but cover: 1-2 people, standing / lying / tilted poses, boxes that move, disappear and
come back after the 5 s tracker expiry, missing landmarks, two boxes matching one tracker, zero-area boxes.

Run from the project folder (any Python 3, standard library only):
  python tools/export_fall_logic_golden.py mobile/android/app/src/test/resources/fall_logic_golden.json
"""
import json
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fall_logic.legacy import LegacyFallLogic  # noqa: E402

FEATURE_KEYS = ["height", "angle", "velocity_y", "velocity_x", "acceleration", "jerk", "mid_shoulder_y",
                "mid_shoulder_x", "mid_hip_y", "mid_hip_x", "aspect_ratio", "shoulder_to_hip_distance",
                "hip_to_feet_distance"]


def pose(rng, kind):
    """33 crop-normalized landmarks (x, y, z, visibility) for a rough body shape."""
    pts = []
    for i in range(33):
        if kind == "standing":
            x, y = 0.5 + rng.uniform(-0.15, 0.15), min(0.98, 0.05 + i / 33 * 0.9 + rng.uniform(-0.03, 0.03))
        elif kind == "lying":
            x, y = min(0.98, 0.05 + i / 33 * 0.9 + rng.uniform(-0.03, 0.03)), 0.5 + rng.uniform(-0.15, 0.15)
        else:   # 아무 자세
            x, y = rng.uniform(0, 1), rng.uniform(0, 1)
        pts.append([x, y, rng.uniform(-0.5, 0.5), rng.uniform(0, 1)])
    # 판정에 쓰는 관절은 자세에 맞게 (코 0, 어깨 11·12, 엉덩이 23·24, 무릎 25·26, 발목 27·28)
    if kind in ("standing", "lying"):
        a = rng.uniform(-0.3, 0.3)
        for idx, t in ((0, 0.05), (11, 0.25), (12, 0.25), (23, 0.55), (24, 0.55), (25, 0.75), (26, 0.75), (27, 0.95), (28, 0.95)):
            side = -0.06 if idx in (11, 23, 25, 27) else 0.06 if idx in (12, 24, 26, 28) else 0.0
            if kind == "standing":
                pts[idx][0], pts[idx][1] = 0.5 + side + a * t, t
            else:
                pts[idx][0], pts[idx][1] = t, 0.5 + side + a * t
    # 판정에 쓰지 않는 관절은 0 (Python 과 Java 입력이 같으면 되고, 파일 크기를 줄임), 값은 소수 4자리
    used = {0, 11, 12, 23, 24, 25, 26, 27, 28}
    return [[round(v, 4) for v in pt] if i in used else [0, 0, 0, 0] for i, pt in enumerate(pts)]


def box(rng, base=None):
    if base and rng.random() < 0.8:
        dx, dy = rng.randint(-15, 15), rng.randint(-15, 15)
        return [base[0] + dx, base[1] + dy, base[2] + dx, base[3] + dy]
    x1, y1 = rng.randint(0, 500), rng.randint(0, 300)
    return [x1, y1, x1 + rng.randint(40, 300), y1 + rng.randint(40, 300)]


def sequence(seed, frames):
    rng = random.Random(seed)
    logic = LegacyFallLogic()
    now = 1_700_000_000.0 + seed
    bases = [None, None]
    out = []
    for _ in range(frames):
        now += rng.choice([0.05, 0.2, 0.5, 1.0, 6.0]) if rng.random() < 0.95 else 0.0
        n = rng.choice([0, 1, 1, 1, 2, 2])
        boxes, lms = [], []
        for p in range(n):
            b = box(rng, bases[p])
            if rng.random() < 0.05:
                b = [b[0], b[1], b[0], b[3]]                       # 넓이 0 상자
            bases[p] = b
            boxes.append(b)
            r = rng.random()
            lms.append(None if r < 0.08 else [] if r < 0.1 else pose(rng, rng.choice(["standing", "lying", "lying", "random"])))
        if n == 2 and rng.random() < 0.1:
            boxes[1] = list(boxes[0])                               # 두 상자가 같은 추적 대상에 붙는 경우
        detected, data, feats = logic.update(now, [tuple(b) for b in boxes], lms)
        out.append({
            "now": now, "boxes": boxes, "landmarks": lms,
            "expect": {
                "fallsDetected": detected, "fallDetected": data["fall_detected"], "fallType": data["fall_type"],
                "personIds": data["person_ids"], "fallenIds": data["fallen_ids"], "personCount": data["person_count"],
                "features": [None if f is None else {k: f[k] for k in FEATURE_KEYS} for f in feats],
            },
        })
    return out


def main(path):
    cases = [{"seed": s, "frames": sequence(s, 40)} for s in range(20)]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps({"source": "fall_logic.LegacyFallLogic (Python)", "cases": cases}, allow_nan=True, separators=(",", ":"))
    Path(path).write_text(text, encoding="utf-8")
    frames = sum(len(c["frames"]) for c in cases)
    falls = sum(1 for c in cases for f in c["frames"] if f["expect"]["fallDetected"])
    print(f"wrote {path}: {len(cases)} sequences, {frames} frames, {falls} frames with a fall")


if __name__ == "__main__":
    main(sys.argv[1])
