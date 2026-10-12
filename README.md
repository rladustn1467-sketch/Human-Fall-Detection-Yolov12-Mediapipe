# Human Fall Detection Using YOLOv12 and MediaPipe

![Program Preview](https://i.imgur.com/gutgsuN.png)

A real-time fall detection system using computer vision with YOLOv12 for person detection and MediaPipe for pose estimation. The system features an intuitive dashboard for monitoring and analyzing falls.

## Features

- **Real-time Detection**: Process video feeds from webcams or video files in real-time
- **Fall Type Classification**: Distinguishes between four types of falls: step and fall, slip and fall, trip and fall, and stump and fall
- **Modern PyQt5 Dashboard**: User-friendly interface with statistics, charts, and history tracking
- **Multi-person Detection**: Can track and analyze multiple people simultaneously
- **Advanced Pose Analysis**: Monitors key body points (shoulders, hips, feet) to accurately assess falls
- **Adjustable Sensitivity**: Fine-tune detection thresholds for different environments
- **Intelligent Fall Counting**: Prevents duplicate counts with person tracking and cooldown periods
- **Automatic Fall Snapshot**: Captures and stores images when falls are detected
- **Sound Alerts**: Audio notifications when falls are detected
- **Command Line Mode**: Also supports a headless command-line mode for deployments

## Requirements

- Python 3.12 (tested on Windows; MediaPipe 0.10.14 has no wheels for Python 3.13)
- CPU-only PyTorch by default (see GPU note below)
- Exact versions are pinned in `requirements.txt` (detection program) and `server/requirements.txt` (web server)

## Installation

1. Clone this repository:
   ```
   git clone https://github.com/rladustn1467-sketch/Human-Fall-Detection-Yolov12-Mediapipe.git
   cd Human-Fall-Detection-Yolov12-Mediapipe
   ```

2. Create a virtual environment for the detection program and install requirements:
   ```
   python -m venv venv
   venv\Scripts\python.exe -m pip install -r requirements.txt
   ```
   `requirements-working.txt` lists the exact version of every package in a tested
   environment and can be used instead to reproduce it exactly.

3. Create a separate virtual environment for the web server:
   ```
   cd server
   python -m venv venv
   venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

4. Download YOLOv12 model (automatic on first run, or manually place in project root)

**GPU (optional):** the default PyPI build of PyTorch on Windows is CPU-only. To use an
NVIDIA GPU, first install the CUDA build of `torch` and `torchvision` (same versions as in
`requirements.txt`) from the PyTorch index following https://pytorch.org/get-started/locally/,
then install `requirements.txt`. Separate `nvidia-*-cu11` packages are not needed.

**Do not upgrade MediaPipe to 1.x:** it removed the `mp.solutions` API that this project uses.

**Telegram alerts (optional):** the server can send a Telegram message when nobody responds
within the response time limit, when the user asks for help, and a correction when the user
later answers that they are okay. Copy `server/.env.example` to `server/.env` and fill in
`TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`, then restart the server. `server/.env` is in
`.gitignore`; never commit it. Without these values the server logs "텔레그램 설정 없음" and
runs without alerts. Alert rules live in `server/notify_rules.py`, delivery channels in
`server/notifiers.py`.

## Usage

### Dashboard Mode (Recommended)

```
python fall_detection_system.py --mode dashboard
```

### Command Line Mode

```
python fall_detection_system.py --mode cli --source 0
```

### Options

- `--mode`: Application mode (`dashboard` or `cli`)
- `--model`: Path to YOLOv12 model file (default: `yolov12n1.pt`)
- `--conf`: Detection confidence threshold (0-1)
- `--source`: Video source (0 for webcam, or path to video file)
- `--fall-threshold`: Threshold for fall detection sensitivity (0-1)
- `--angle-threshold`: Threshold for body angle in degrees (0-90)
- `--save-falls`: Save frames when falls are detected
- `--output-dir`: Directory to save fall snapshots

## System Architecture

The system consists of several key components:

1. **YOLOv12 Person Detection**: Identifies people in the video frames
2. **MediaPipe Pose Estimation**: Extracts skeletal data from detected persons
3. **Fall Detection Algorithm**: Analyzes pose data to detect falls with these criteria:
   - Body angle relative to vertical
   - Body aspect ratio (horizontal vs. vertical orientation)
   - Sudden vertical position changes
   - Motion pattern analysis
4. **Person Tracking**: Follows individuals across frames to maintain identity
5. **PyQt5 Dashboard**: Provides real-time monitoring and analytics

## Fall Classification Criteria

- **Step and Fall**: Gradual angle change with moderate velocity
- **Slip and Fall**: Rapid angle change with high velocity
- **Trip and Fall**: Forward momentum with moderate angle change
- **Stump and Fall**: Minimal horizontal movement with significant vertical drop

## Project Structure

```
fall-detection-system/
├── models/
│   └── fall_detector.py        # Core fall detection model
├── dashboard/
│   └── dashboard_app.py        # PyQt5 Dashboard UI application
├── utils/
│   └── utils.py                # Utility functions
├── fall_snapshots/             # Directory for fall images
├── fall_detection_system.py    # Main application script
├── README.md                   # Project documentation
└── requirements.txt            # Project dependencies
```

## Recent Improvements

- Enhanced fall detection algorithm with stricter criteria
- Added cooldown periods to prevent duplicate fall counts
- Improved sensitivity controls for different environments
- Added comprehensive fall type classification
- Fixed critical point detection for more accurate pose analysis
- Improved error handling for camera access and processing
- Optimized snapshot saving to reduce disk usage
- Migrated from Tkinter to PyQt5 for a more modern interface

## Future Enhancements

- Email notification system for alerting caregivers
- Integration with mobile applications
- Support for distributed camera networks
- Fall risk prediction based on movement patterns
- Cloud integration for remote monitoring
- AI-assisted fall risk prediction

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- YOLOv12 by Ultralytics (https://github.com/ultralytics/ultralytics)
- MediaPipe by Google (https://mediapipe.dev/)
- PyQt5 Dashboard inspiration from modern monitoring applications 
