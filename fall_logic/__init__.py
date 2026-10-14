"""Fall decision logic separated from the PyQt5 dashboard.

Stage 1 (current): a legacy mode that reproduces models/fall_detector.py exactly,
including its known issues. Nothing in the existing program imports this package;
the dashboard and CLI keep using FallDetector unchanged. Connect it only after
tools/replay_compare.py shows zero differences on recorded data.

The package is pure Python (no cv2, numpy, torch or mediapipe), so the same rules
and test cases can later be ported to a mobile app.

Modules:
  features.py  pose features (copy of FallDetector.calculate_pose_features)
  tracker.py   IoU person tracker (copy of FallDetector.track_persons)
  rules.py     posture rule (copy of the check in FallDetector.process_frame)
  legacy.py    LegacyFallLogic: ties the three together, returns the same fall_data
  coords.py    coordinate conversion for a future improved mode (pixel coordinates);
               not used by the legacy mode

Tests (from the project root, inside the detection venv):
  venv\\Scripts\\python.exe -m unittest discover -s tests -t .
"""
from fall_logic.legacy import LegacyFallLogic

__all__ = ["LegacyFallLogic"]
