import sys
import os
import cv2
import numpy as np
import datetime
import time
import threading
import json
import base64
import queue
import random
import uuid
import urllib.error
import urllib.request
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.dates import DateFormatter
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QFileDialog, QMessageBox, QFrame,
    QGridLayout, QGroupBox, QScrollArea, QTreeWidget, QTreeWidgetItem,
    QHeaderView, QSlider, QCheckBox, QLineEdit, QSpacerItem
)
from PyQt5.QtGui import QPixmap, QImage, QColor, QFont, QIcon
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QSize

# Add parent directory to path so we can import our modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models.fall_detector import FallDetector
from utils.silhouette import SilhouetteRenderer, shrink_frame
from utils.low_light import LowLightEnhancer, JointCompareLogger, draw_debug_overlay
from dashboard.device_link import DeviceLink, DeviceRevoked

from PyQt5.QtWidgets import QShortcut, QInputDialog
from PyQt5.QtGui import QKeySequence

# 낙상 이벤트 전송 설정 (다른 컴퓨터에서는 DEVICE_ID만 바꾸면 됨)
EVENT_SERVER_URL = "http://127.0.0.1:8000/api/events"
DEVICE_ID = "laptop"
_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 서버가 처음 실행될 때 만드는 접근 토큰 파일 (서버와 같은 컴퓨터에서 실행할 때)
ACCESS_TOKEN_FILE = os.path.join(_PROJECT_DIR, "server", "access_token.txt")
# 전송 실패 시 재시도 간격(초). 항목 수 = 재시도 횟수
SEND_RETRY_DELAYS = (1, 2, 4)
SEND_FAILURE_LOG = os.path.join(_PROJECT_DIR, "logs", "send_failures.log")
# 웹캠 없이 테스트할 때 카메라 프레임 대신 쓰는 사진 폴더 (F9: 카메라 프레임이 없으면 랜덤 선택, Shift+F9: 직접 선택)
TEST_IMAGE_DIR = os.path.join(_PROJECT_DIR, "test_images")
TEST_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp")
# 테스트 사진으로 만든 가짜 낙상의 가공 결과(실루엣 이미지)를 눈으로 확인하도록 저장하는 폴더
TEST_OUTPUT_DIR = os.path.join(_PROJECT_DIR, "test_output")

class ModernStyle:
    """Modern UI style definitions for the application."""
    
    # Color scheme
    DARK_PRIMARY = "#1a73e8"       # Google Blue
    LIGHT_PRIMARY = "#4285f4"
    ACCENT = "#fbbc05"             # Yellow
    DANGER = "#ea4335"             # Red
    SUCCESS = "#34a853"            # Green
    BG_DARK = "#202124"
    BG_LIGHT = "#f8f9fa"
    TEXT_DARK = "#3c4043"
    TEXT_LIGHT = "#e8eaed"
    CARD_BG = "#ffffff"
    
    # Stylesheet templates
    MAIN_STYLESHEET = """
        QMainWindow, QDialog {
            background-color: %s;
        }
        QTabWidget {
            background-color: %s;
        }
        QTabWidget::pane {
            border: none;
            background-color: %s;
        }
        QTabBar::tab {
            background-color: %s;
            color: %s;
            padding: 8px 15px;
            margin-right: 2px;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
        }
        QTabBar::tab:selected {
            background-color: %s;
            color: %s;
            border-bottom: 3px solid %s;
        }
        QWidget {
            font-family: 'Segoe UI', Arial;
            font-size: 10pt;
        }
        QLabel {
            color: %s;
        }
        QPushButton {
            background-color: %s;
            color: white;
            border: none;
            padding: 8px 15px;
            border-radius: 4px;
        }
        QPushButton:hover {
            background-color: %s;
        }
        QPushButton:disabled {
            background-color: #cccccc;
            color: #666666;
        }
        QGroupBox {
            background-color: %s;
            border-radius: 6px;
            border: 1px solid #e0e0e0;
            margin-top: 15px;
            font-weight: bold;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 10px;
            padding: 0 5px;
            color: %s;
        }
    """ % (
        BG_LIGHT, BG_LIGHT, BG_LIGHT,  # Main colors
        BG_LIGHT, TEXT_DARK,           # Tab normal
        CARD_BG, DARK_PRIMARY, DARK_PRIMARY,  # Tab selected
        TEXT_DARK,                     # Label text
        LIGHT_PRIMARY, DARK_PRIMARY,   # Button colors
        CARD_BG,                       # GroupBox background
        DARK_PRIMARY                   # GroupBox title
    )
    
    # Button style variations
    PRIMARY_BTN = """
        QPushButton {
            background-color: %s;
            color: white;
        }
        QPushButton:hover {
            background-color: %s;
        }
    """ % (DARK_PRIMARY, LIGHT_PRIMARY)
    
    DANGER_BTN = """
        QPushButton {
            background-color: %s;
            color: white;
        }
        QPushButton:hover {
            background-color: #ff6b6b;
        }
    """ % (DANGER)
    
    SUCCESS_BTN = """
        QPushButton {
            background-color: %s;
            color: white;
        }
        QPushButton:hover {
            background-color: #4ad66d;
        }
    """ % (SUCCESS)

class FallDetectionDashboard(QMainWindow):
    def __init__(self, server_url=None):
        super().__init__()
        self.event_server_url = server_url or EVENT_SERVER_URL
        
        # Set window title and size
        self.setWindowTitle("Fall Detection System Dashboard")
        self.resize(1280, 800)
        
        # Apply modern styles
        self.setStyleSheet(ModernStyle.MAIN_STYLESHEET)
        
        # Dashboard state variables
        self.is_running = False
        self.camera_source = 0  # Default camera source
        self.video_source = None
        self.video_paused = False
        self.detection_enabled = True
        self.fall_detector = None
        self.cap = None
        
        # Statistics
        self.stats = {
            "total_people_detected": 0,
            "total_falls_detected": 0,
            "fall_types": {
                "step_and_fall": 0,
                "slip_and_fall": 0,
                "trip_and_fall": 0,
                "stump_and_fall": 0
            },
            "detection_history": []  # List of (timestamp, fall_type) tuples
        }
        
        # Load configuration
        self.config = {
            "model_path": "yolov12n1.pt",
            "confidence": 0.5,
            "fall_threshold": 0.4,
            "angle_threshold": 45,
            "sound_alerts": True,
            # 원본 화면 스냅샷 저장은 사생활 보호를 위해 사용하지 않음 (서버에는 실루엣 이미지만 전송)
            "auto_save_falls": False,
            "output_dir": "fall_snapshots",
            "fall_cooldown": 5.0  # Cooldown in seconds for the same person
        }
        
        # Initialize tracking set for fallen IDs
        self.tracked_fallen_ids = set()
        
        # Track when each person fell (for cooldown)
        self.fallen_timestamps = {}
        
        # Last snapshot time to avoid saving too many images
        self.last_snapshot_time = 0
        self.snapshot_cooldown = 2.0  # seconds

        # Latest raw camera frame and person boxes (for silhouette images sent to the server)
        self._last_raw_frame = None
        self._last_person_boxes = []

        # One worker thread handles silhouette rendering and sending; the small
        # bounded queue keeps at most a few downscaled frames in memory
        self._event_queue = queue.Queue(maxsize=2)
        self._silhouette = SilhouetteRenderer()
        threading.Thread(target=self._event_worker_loop, daemon=True).start()

        # Low-light correction applied before detection; F10 toggles the debug view
        self.low_light = LowLightEnhancer()
        self.joint_compare = JointCompareLogger()
        self.low_light_debug = False

        # 앱과 연결 (device_link.py): 연결되면 기기 토큰으로 낙상·상태 신호를 보내고, 앱에서 끄면 카메라 감지를 멈춤.
        # 연결 전에는 지금까지처럼 /api/events (공용 토큰)
        self.device_link = DeviceLink(self.event_server_url)
        self._remote_paused = False       # 앱에서 감지를 꺼서 이 프로그램이 카메라를 멈춘 상태
        self._last_frame_ok_at = 0.0      # 카메라(또는 영상)에서 마지막으로 프레임을 읽은 시각

        # Create the central widget and layout
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        
        # Setup the UI components
        self.setup_ui()
        # TEST: F9 단축키로 가짜 낙상 발생
        self.test_shortcut = QShortcut(QKeySequence("F9"), self)
        self.test_shortcut.activated.connect(self.trigger_test_fall)
        # TEST: Shift+F9로 사진을 골라 카메라 프레임 대신 써서 가짜 낙상 발생
        self.test_image_shortcut = QShortcut(QKeySequence("Shift+F9"), self)
        self.test_image_shortcut.activated.connect(self.choose_test_image)
        # F10: 원본/보정 영상 비교 디버그 표시 켜기/끄기
        self.low_light_shortcut = QShortcut(QKeySequence("F10"), self)
        self.low_light_shortcut.activated.connect(self.toggle_low_light_debug)

        # 상태 신호는 백그라운드에서, 앱의 켜기/끄기 반영과 연결 상태 표시는 1초마다 화면 스레드에서
        self.device_link.start(self._camera_ok)
        self.device_timer = QTimer(self)
        self.device_timer.timeout.connect(self._sync_device_link)
        self.device_timer.start(1000)
        self._sync_device_link()

    def setup_ui(self):
        """Set up the main user interface."""
        # Create a tab widget
        self.tab_widget = QTabWidget()
        self.main_layout.addWidget(self.tab_widget)
        
        # Create tabs
        self.dashboard_tab = QWidget()
        self.settings_tab = QWidget()
        self.history_tab = QWidget()
        
        # Add tabs to the tab widget
        self.tab_widget.addTab(self.dashboard_tab, "Dashboard")
        self.tab_widget.addTab(self.settings_tab, "Settings")
        self.tab_widget.addTab(self.history_tab, "History")
        
        # Setup each tab
        self.setup_dashboard_tab()
        self.setup_settings_tab()
        self.setup_history_tab()
        
        # Add status bar at the bottom
        self.status_bar = self.statusBar()
        self.status_bar.showMessage("Ready to start detection")

    def setup_dashboard_tab(self):
        """Set up the main dashboard tab."""
        # Main layout for dashboard tab
        layout = QHBoxLayout(self.dashboard_tab)
        
        # Create left panel (video feed and controls)
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(10, 10, 10, 10)
        
        # Create right panel (statistics and charts)
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 10, 10, 10)
        
        # Add panels to main layout
        layout.addWidget(left_panel, 3)  # 3:2 ratio
        layout.addWidget(right_panel, 2)
        
        # Video display frame
        video_group = QGroupBox("Video Feed")
        video_layout = QVBoxLayout(video_group)
        video_layout.setContentsMargins(10, 20, 10, 10)
        
        # Video canvas
        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setMinimumSize(640, 480)
        self.video_label.setStyleSheet("background-color: black;")
        video_layout.addWidget(self.video_label)
        
        # Add video frame to left panel
        left_layout.addWidget(video_group)
        
        # Controls group
        controls_group = QGroupBox("Controls")
        controls_layout = QVBoxLayout(controls_group)
        controls_layout.setContentsMargins(10, 20, 10, 10)
        
        # Source selection
        source_layout = QHBoxLayout()
        source_layout.addWidget(QLabel("Video Source:"))
        
        self.camera_combo = QComboBox()
        self.camera_combo.addItems(["Webcam (0)", "Webcam (1)", "Webcam (2)"])
        self.camera_combo.setCurrentIndex(0)
        self.camera_combo.currentIndexChanged.connect(self.on_camera_changed)
        source_layout.addWidget(self.camera_combo)
        
        self.browse_btn = QPushButton("Browse Video File")
        self.browse_btn.clicked.connect(self.browse_video_file)
        source_layout.addWidget(self.browse_btn)
        source_layout.addStretch(1)
        
        controls_layout.addLayout(source_layout)
        
        # Buttons layout
        buttons_layout = QHBoxLayout()
        
        # Start/Stop button
        self.start_stop_btn = QPushButton("Start Detection")
        self.start_stop_btn.clicked.connect(self.toggle_detection)
        self.start_stop_btn.setStyleSheet(ModernStyle.PRIMARY_BTN)
        self.start_stop_btn.setMinimumWidth(150)
        buttons_layout.addWidget(self.start_stop_btn)
        
        # Pause/Resume button
        self.pause_resume_btn = QPushButton("Pause")
        self.pause_resume_btn.clicked.connect(self.toggle_pause)
        self.pause_resume_btn.setEnabled(False)
        self.pause_resume_btn.setMinimumWidth(100)
        buttons_layout.addWidget(self.pause_resume_btn)
        
        # Reset stats button
        self.reset_stats_btn = QPushButton("Reset Stats")
        self.reset_stats_btn.clicked.connect(self.reset_statistics)
        self.reset_stats_btn.setStyleSheet(ModernStyle.DANGER_BTN)
        self.reset_stats_btn.setMinimumWidth(100)
        buttons_layout.addWidget(self.reset_stats_btn)
        
        # Settings button
        self.settings_btn = QPushButton("Settings")
        self.settings_btn.clicked.connect(lambda: self.tab_widget.setCurrentIndex(1))
        self.settings_btn.setMinimumWidth(100)
        buttons_layout.addWidget(self.settings_btn)
        
        buttons_layout.addStretch(1)
        controls_layout.addLayout(buttons_layout)

        # 앱 연결: 앱의 '기기 추가'에서 받은 연결 코드를 한 번 입력 (기기 토큰은 프로젝트 밖에 저장)
        link_layout = QHBoxLayout()
        link_layout.addWidget(QLabel("앱 연결:"))
        self.link_status_label = QLabel("")
        self.link_status_label.setWordWrap(True)
        link_layout.addWidget(self.link_status_label, 1)
        self.link_pair_btn = QPushButton("연결 코드 입력")
        self.link_pair_btn.clicked.connect(self.enter_pairing_code)
        link_layout.addWidget(self.link_pair_btn)
        self.link_forget_btn = QPushButton("이 PC에서 연결 해제")
        self.link_forget_btn.clicked.connect(self.forget_device_link)
        link_layout.addWidget(self.link_forget_btn)
        controls_layout.addLayout(link_layout)

        # Add controls to left panel
        left_layout.addWidget(controls_group)
        
        # Statistics group
        stats_group = QGroupBox("Detection Statistics")
        stats_layout = QGridLayout(stats_group)
        stats_layout.setContentsMargins(10, 20, 10, 10)
        
        # People detected
        stats_layout.addWidget(QLabel("People Detected:"), 0, 0)
        self.people_count_label = QLabel("0")
        self.people_count_label.setStyleSheet("font-weight: bold;")
        stats_layout.addWidget(self.people_count_label, 0, 1)
        
        # Falls detected
        stats_layout.addWidget(QLabel("Falls Detected:"), 1, 0)
        self.fall_count_label = QLabel("0")
        self.fall_count_label.setStyleSheet("font-weight: bold;")
        stats_layout.addWidget(self.fall_count_label, 1, 1)
        
        # FPS
        stats_layout.addWidget(QLabel("FPS:"), 2, 0)
        self.fps_label = QLabel("0.0")
        self.fps_label.setStyleSheet("font-weight: bold;")
        stats_layout.addWidget(self.fps_label, 2, 1)
        
        # Fall types heading
        fall_types_label = QLabel("Fall Types:")
        fall_types_label.setStyleSheet("font-weight: bold;")
        stats_layout.addWidget(fall_types_label, 3, 0, 1, 2)
        
        # Individual fall types
        self.fall_type_labels = {}
        fall_types = [
            ("step_and_fall", "Step and Fall"),
            ("slip_and_fall", "Slip and Fall"),
            ("trip_and_fall", "Trip and Fall"),
            ("stump_and_fall", "Stump and Fall")
        ]
        
        for i, (fall_type, display_name) in enumerate(fall_types):
            stats_layout.addWidget(QLabel(f"   {display_name}:"), i+4, 0)
            self.fall_type_labels[fall_type] = QLabel("0")
            stats_layout.addWidget(self.fall_type_labels[fall_type], i+4, 1)
        
        # Add statistics to right panel
        right_layout.addWidget(stats_group)
        
        # Charts
        # Pie chart
        pie_group = QGroupBox("Fall Type Distribution")
        pie_layout = QVBoxLayout(pie_group)
        pie_layout.setContentsMargins(10, 20, 10, 10)
        
        self.pie_figure = Figure(figsize=(4, 4), dpi=100)
        self.pie_canvas = FigureCanvas(self.pie_figure)
        self.pie_ax = self.pie_figure.add_subplot(111)
        pie_layout.addWidget(self.pie_canvas)
        
        # Timeline chart
        timeline_group = QGroupBox("Detection Timeline")
        timeline_layout = QVBoxLayout(timeline_group)
        timeline_layout.setContentsMargins(10, 20, 10, 10)
        
        self.timeline_figure = Figure(figsize=(4, 3), dpi=100)
        self.timeline_canvas = FigureCanvas(self.timeline_figure)
        self.timeline_ax = self.timeline_figure.add_subplot(111)
        timeline_layout.addWidget(self.timeline_canvas)
        
        # Add charts to right panel
        right_layout.addWidget(pie_group)
        right_layout.addWidget(timeline_group)
        
        # Initialize charts
        self.update_pie_chart()
        self.update_timeline_chart()

    def setup_settings_tab(self):
        """Set up the settings tab."""
        # Main layout for settings tab
        layout = QVBoxLayout(self.settings_tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Model settings
        model_group = QGroupBox("Model Settings")
        model_layout = QGridLayout(model_group)
        model_layout.setContentsMargins(15, 25, 15, 15)
        model_layout.setSpacing(10)
        
        # Model path
        model_layout.addWidget(QLabel("YOLOv12 Model:"), 0, 0)
        
        model_path_layout = QHBoxLayout()
        self.model_path_edit = QLineEdit(self.config["model_path"])
        model_path_layout.addWidget(self.model_path_edit)
        
        browse_model_btn = QPushButton("Browse")
        browse_model_btn.clicked.connect(self.browse_model_file)
        model_path_layout.addWidget(browse_model_btn)
        
        model_layout.addLayout(model_path_layout, 0, 1)
        
        # Confidence threshold
        model_layout.addWidget(QLabel("Confidence Threshold:"), 1, 0)
        
        conf_layout = QHBoxLayout()
        self.confidence_slider = QSlider(Qt.Horizontal)
        self.confidence_slider.setMinimum(1)
        self.confidence_slider.setMaximum(100)
        self.confidence_slider.setValue(int(self.config["confidence"] * 100))
        self.confidence_slider.setTickPosition(QSlider.TicksBelow)
        self.confidence_slider.setTickInterval(10)
        conf_layout.addWidget(self.confidence_slider)
        
        self.confidence_label = QLabel(f"{self.config['confidence']:.2f}")
        conf_layout.addWidget(self.confidence_label)
        
        self.confidence_slider.valueChanged.connect(self.update_confidence_label)
        model_layout.addLayout(conf_layout, 1, 1)
        
        # Add model settings to main layout
        layout.addWidget(model_group)
        
        # Detection parameters
        detection_group = QGroupBox("Detection Parameters")
        detection_layout = QGridLayout(detection_group)
        detection_layout.setContentsMargins(15, 25, 15, 15)
        detection_layout.setSpacing(10)
        
        # Fall threshold
        detection_layout.addWidget(QLabel("Fall Threshold:"), 0, 0)
        
        fall_threshold_layout = QHBoxLayout()
        self.fall_threshold_slider = QSlider(Qt.Horizontal)
        self.fall_threshold_slider.setMinimum(1)
        self.fall_threshold_slider.setMaximum(100)
        self.fall_threshold_slider.setValue(int(self.config["fall_threshold"] * 100))
        self.fall_threshold_slider.setTickPosition(QSlider.TicksBelow)
        self.fall_threshold_slider.setTickInterval(10)
        fall_threshold_layout.addWidget(self.fall_threshold_slider)
        
        self.fall_threshold_label = QLabel(f"{self.config['fall_threshold']:.2f}")
        fall_threshold_layout.addWidget(self.fall_threshold_label)
        
        self.fall_threshold_slider.valueChanged.connect(self.update_fall_threshold_label)
        detection_layout.addLayout(fall_threshold_layout, 0, 1)
        
        # Angle threshold
        detection_layout.addWidget(QLabel("Angle Threshold:"), 1, 0)
        
        angle_threshold_layout = QHBoxLayout()
        self.angle_threshold_slider = QSlider(Qt.Horizontal)
        self.angle_threshold_slider.setMinimum(5)
        self.angle_threshold_slider.setMaximum(90)
        self.angle_threshold_slider.setValue(self.config["angle_threshold"])
        self.angle_threshold_slider.setTickPosition(QSlider.TicksBelow)
        self.angle_threshold_slider.setTickInterval(5)
        angle_threshold_layout.addWidget(self.angle_threshold_slider)
        
        self.angle_threshold_label = QLabel(f"{self.config['angle_threshold']}")
        angle_threshold_layout.addWidget(self.angle_threshold_label)
        
        self.angle_threshold_slider.valueChanged.connect(self.update_angle_threshold_label)
        detection_layout.addLayout(angle_threshold_layout, 1, 1)
        
        # Add detection parameters to main layout
        layout.addWidget(detection_group)
        
        # Notification settings
        notification_group = QGroupBox("Notification Settings")
        notification_layout = QGridLayout(notification_group)
        notification_layout.setContentsMargins(15, 25, 15, 15)
        notification_layout.setSpacing(10)
        
        # Sound alerts
        self.sound_alerts_check = QCheckBox("Enable Sound Alerts")
        self.sound_alerts_check.setChecked(self.config.get("sound_alerts", True))
        notification_layout.addWidget(self.sound_alerts_check, 0, 0, 1, 2)
        
        # Auto-save falls
        self.auto_save_falls_check = QCheckBox("Automatically Save Fall Snapshots")
        self.auto_save_falls_check.setChecked(False)
        # 원본 화면이 저장되므로 사생활 보호를 위해 끔
        self.auto_save_falls_check.setEnabled(False)
        self.auto_save_falls_check.setToolTip("사생활 보호를 위해 원본 스냅샷 저장은 사용하지 않습니다")
        notification_layout.addWidget(self.auto_save_falls_check, 1, 0, 1, 2)
        
        # Output directory
        notification_layout.addWidget(QLabel("Output Directory:"), 2, 0)
        
        output_dir_layout = QHBoxLayout()
        self.output_dir_edit = QLineEdit(self.config.get("output_dir", "fall_snapshots"))
        output_dir_layout.addWidget(self.output_dir_edit)
        
        browse_dir_btn = QPushButton("Browse")
        browse_dir_btn.clicked.connect(self.browse_output_dir)
        output_dir_layout.addWidget(browse_dir_btn)
        
        notification_layout.addLayout(output_dir_layout, 2, 1)
        
        # Add notification settings to main layout
        layout.addWidget(notification_group)
        
        # Advanced settings section
        advanced_group = QGroupBox("Advanced Detection Settings")
        advanced_layout = QGridLayout(advanced_group)
        advanced_layout.setContentsMargins(15, 25, 15, 15)
        advanced_layout.setSpacing(10)
        
        # Detection sensitivity
        advanced_layout.addWidget(QLabel("Detection Sensitivity:"), 0, 0)
        
        sensitivity_layout = QHBoxLayout()
        self.sensitivity_slider = QSlider(Qt.Horizontal)
        self.sensitivity_slider.setMinimum(1)
        self.sensitivity_slider.setMaximum(10)
        self.sensitivity_slider.setValue(5)  # Medium sensitivity
        self.sensitivity_slider.setTickPosition(QSlider.TicksBelow)
        self.sensitivity_slider.setTickInterval(1)
        sensitivity_layout.addWidget(self.sensitivity_slider)
        
        self.sensitivity_label = QLabel("Medium")
        sensitivity_layout.addWidget(self.sensitivity_label)
        
        # IMPORTANT: Define the update_sensitivity_label method right here as a lambda function
        # This avoids the need for a separate method declaration
        self.sensitivity_slider.valueChanged.connect(
            lambda value: self.sensitivity_label.setText({
                1: "Very Low", 2: "Low", 3: "Low-Medium", 4: "Medium-Low", 
                5: "Medium", 6: "Medium-High", 7: "High-Medium", 
                8: "High", 9: "Very High", 10: "Maximum"
            }.get(value, "Medium"))
        )
        
        advanced_layout.addLayout(sensitivity_layout, 0, 1)
        
        # Add to main layout
        layout.addWidget(advanced_group)
        
        # Save settings button
        save_layout = QHBoxLayout()
        save_layout.addStretch(1)
        
        save_settings_btn = QPushButton("Save Settings")
        save_settings_btn.setStyleSheet(ModernStyle.SUCCESS_BTN)
        save_settings_btn.setMinimumWidth(150)
        save_settings_btn.clicked.connect(self.save_settings)
        save_layout.addWidget(save_settings_btn)
        
        layout.addLayout(save_layout)
        layout.addStretch(1)

    def setup_history_tab(self):
        """Set up the history tab."""
        # Main layout for history tab
        layout = QVBoxLayout(self.history_tab)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Toolbar
        toolbar_layout = QHBoxLayout()
        
        # Filter options
        toolbar_layout.addWidget(QLabel("Filter by:"))
        
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All", "Step and Fall", "Slip and Fall", "Trip and Fall", "Stump and Fall"])
        self.filter_combo.currentIndexChanged.connect(self.filter_history)
        toolbar_layout.addWidget(self.filter_combo)
        
        toolbar_layout.addStretch(1)
        
        # Export button
        export_btn = QPushButton("Export History")
        export_btn.clicked.connect(self.export_history)
        toolbar_layout.addWidget(export_btn)
        
        layout.addLayout(toolbar_layout)
        
        # History tree widget
        self.history_tree = QTreeWidget()
        self.history_tree.setColumnCount(3)
        self.history_tree.setHeaderLabels(["Time", "Fall Type", "Details"])
        self.history_tree.setAlternatingRowColors(True)
        self.history_tree.setStyleSheet("""
            QTreeWidget {
                background-color: white;
                alternate-background-color: #f5f5f5;
                border: 1px solid #e0e0e0;
                font-size: 10pt;
            }
            QHeaderView::section {
                background-color: #4285f4;
                color: white;
                font-weight: bold;
                padding: 6px;
                border: none;
            }
        """)
        
        # Set column widths
        header = self.history_tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        
        layout.addWidget(self.history_tree)

    # UI utility methods
    def update_confidence_label(self, value):
        """Update confidence threshold label when slider changes."""
        confidence = value / 100.0
        self.confidence_label.setText(f"{confidence:.2f}")
    
    def update_fall_threshold_label(self, value):
        """Update fall threshold label when slider changes."""
        threshold = value / 100.0
        self.fall_threshold_label.setText(f"{threshold:.2f}")
    
    def update_angle_threshold_label(self, value):
        """Update angle threshold label when slider changes."""
        self.angle_threshold_label.setText(f"{value}")
    
    # File and directory browsing methods
    def browse_model_file(self):
        """Open file dialog to select a model file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select YOLOv12 Model File",
            "",
            "PyTorch models (*.pt);;All Files (*)"
        )
        
        if file_path:
            self.model_path_edit.setText(file_path)
    
    def browse_output_dir(self):
        """Open directory dialog to select output directory."""
        dir_path = QFileDialog.getExistingDirectory(
            self,
            "Select Output Directory for Fall Snapshots"
        )
        
        if dir_path:
            self.output_dir_edit.setText(dir_path)
    
    def browse_video_file(self):
        """Open file dialog to select a video file."""
        if self.is_running:
            QMessageBox.information(self, "Info", "Please stop detection before changing the video source.")
            return
            
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Video File",
            "",
            "Video Files (*.mp4 *.avi *.mov *.mkv);;All Files (*)"
        )
        
        if file_path:
            self.video_source = file_path
            # Update camera combo box to show video file name
            self.camera_combo.setCurrentText(os.path.basename(file_path))
    
    # Settings management
    def save_settings(self):
        """Save the settings to the configuration."""
        # Update configuration with current settings
        self.config["model_path"] = self.model_path_edit.text()
        self.config["confidence"] = self.confidence_slider.value() / 100.0
        self.config["fall_threshold"] = self.fall_threshold_slider.value() / 100.0
        self.config["angle_threshold"] = self.angle_threshold_slider.value()
        self.config["sound_alerts"] = self.sound_alerts_check.isChecked()
        self.config["auto_save_falls"] = self.auto_save_falls_check.isChecked()
        self.config["output_dir"] = self.output_dir_edit.text()
        
        # If detection is running, apply the changes to the fall detector
        if self.fall_detector:
            self.fall_detector.confidence = self.config["confidence"]
            self.fall_detector.fall_threshold = self.config["fall_threshold"]
            self.fall_detector.angle_threshold = self.config["angle_threshold"]
        
        # Save to a configuration file (optional)
        try:
            os.makedirs(os.path.dirname(os.path.abspath("config/settings.json")), exist_ok=True)
            with open("config/settings.json", "w") as f:
                json.dump(self.config, f, indent=4)
            QMessageBox.information(self, "Settings Saved", "Configuration has been saved successfully.")
        except Exception as e:
            QMessageBox.warning(self, "Save Error", f"Could not save configuration to file: {str(e)}")
        
        # Switch back to main tab
        self.tab_widget.setCurrentIndex(0)
    
    # Camera source management
    def on_camera_changed(self, index):
        """Handle camera source selection changes."""
        if self.is_running:
            QMessageBox.information(self, "Info", "Please stop detection before changing the camera source.")
            return
        
        selection = self.camera_combo.currentText()
        if selection.startswith("Webcam"):
            # Extract camera number from string like "Webcam (0)"
            try:
                camera_id = int(selection.split("(")[1].split(")")[0])
                self.camera_source = camera_id
                self.video_source = None
            except:
                QMessageBox.critical(self, "Error", "Invalid camera selection.")
    
    # Video processing methods
    def toggle_detection(self):
        """Start or stop the fall detection process."""
        if self.is_running:
            # Stop detection
            self.is_running = False
            self.start_stop_btn.setText("Start Detection")
            self.pause_resume_btn.setEnabled(False)
            self.status_bar.showMessage("Ready to start detection")
            
            # Stop the video processing timer if it exists
            if hasattr(self, 'video_timer') and self.video_timer.isActive():
                self.video_timer.stop()
            
            # Release camera if open
            if self.cap and self.cap.isOpened():
                self.cap.release()
                self.cap = None

            # Drop the last raw frame so it is not kept in memory or reused
            self._last_raw_frame = None
            self._last_person_boxes = []
        else:
            # Start detection
            self.start_detection()
    
    def toggle_pause(self):
        """Pause or resume the video processing."""
        if self.video_paused:
            # Resume
            self.video_paused = False
            self.pause_resume_btn.setText("Pause")
            self.status_bar.showMessage("Running")
        else:
            # Pause
            self.video_paused = True
            self.pause_resume_btn.setText("Resume")
            self.status_bar.showMessage("Paused")
    
    def _ensure_fall_detector(self):
        """Create the fall detector on first use."""
        if not self.fall_detector:
            self.fall_detector = FallDetector(
                model_path=self.config["model_path"],
                confidence=self.config["confidence"]
            )

            # Set detection parameters
            self.fall_detector.fall_threshold = self.config["fall_threshold"]
            self.fall_detector.angle_threshold = self.config["angle_threshold"]

    def start_detection(self):
        """Initialize and start the fall detection process."""
        if self.device_link.paired and not self.device_link.enabled:
            # 앱에서 이 기기의 감지를 꺼 둠: 카메라를 열지 않음 (앱에서 켜면 자동으로 다시 시작)
            self._remote_paused = True
            self.status_bar.showMessage("앱에서 이 기기의 감지를 꺼 두었어요. 앱에서 켜면 다시 시작해요.")
            QMessageBox.information(self, "감지 꺼짐", "앱에서 이 기기의 감지를 꺼 두었어요.\n앱에서 감지를 켜면 자동으로 다시 시작해요.")
            return
        try:
            # Initialize the fall detector if not already created
            self._ensure_fall_detector()

            # Open video source
            if self.video_source:
                # Video file
                self.cap = cv2.VideoCapture(self.video_source)
            else:
                # Camera - try without DSHOW first
                print("DEBUG:", repr(self.camera_source), type(self.camera_source), repr(self.video_source))
                self.cap = cv2.VideoCapture(self.camera_source)
                
                

            
            if not self.cap.isOpened():
                # Try with DSHOW on Windows as fallback
                try:
                    if os.name == 'nt':  # Windows
                        self.cap = cv2.VideoCapture(self.camera_source, cv2.CAP_DSHOW)
                except:
                    pass
                    
                if not self.cap.isOpened():
                    QMessageBox.critical(self, "Error", "Could not open video source.")
                    return
            
            # Update UI state
            self.is_running = True
            self.video_paused = False
            self.start_stop_btn.setText("Stop Detection")
            self.pause_resume_btn.setEnabled(True)
            self.pause_resume_btn.setText("Pause")
            self.status_bar.showMessage("Running")
            
            # Initialize FPS counter
            self.frame_count = 0
            self.last_fps_update = time.time()
            self.fps = 0.0
            
            # Create and start the video processing timer
            self.video_timer = QTimer()
            self.video_timer.timeout.connect(self.process_frame)
            self.video_timer.start(30)  # 30ms interval (~33 FPS)
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to start detection: {str(e)}")
            self.is_running = False
            import traceback
            traceback.print_exc()
    
    def process_frame(self):
        """Process a single video frame."""
        if not self.is_running or not self.cap:
            return
            
        if not self.video_paused:
            # Read a frame
            ret, frame = self.cap.read()
            if not ret:
                if self.video_source:
                    # Video file ended
                    QMessageBox.information(self, "Info", "Video playback completed.")
                    self.toggle_detection()
                    return
                else:
                    # Camera frame read error - try again next time
                    return
            self._last_frame_ok_at = time.time()

            # Calculate FPS
            self.frame_count += 1
            current_time = time.time()
            time_diff = current_time - self.last_fps_update
            
            if time_diff >= 1.0:
                self.fps = self.frame_count / time_diff
                self.frame_count = 0
                self.last_fps_update = current_time
                # Update FPS display
                self.fps_label.setText(f"{self.fps:.1f}")
            
            # Correct dark frames before detection; the corrected frame is used for
            # pose detection, silhouettes and display alike
            raw_frame = frame
            frame, light_info = self.low_light.process(raw_frame)

            # Process the frame for fall detection
            if self.detection_enabled:
                output_frame, fall_detected, fall_data = self.fall_detector.process_frame(frame)
                self.joint_compare.maybe_log(raw_frame, frame, fall_data.get("person_boxes", []), light_info)

                # Keep a reference (no copy) to the raw frame for silhouette images
                self._last_raw_frame = frame
                self._last_person_boxes = fall_data.get("person_boxes", [])
                
                # Add FPS display to the frame
                fps_text = f"FPS: {self.fps:.1f}"
                cv2.putText(
                    output_frame, 
                    fps_text, 
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 
                    0.8, 
                    (0, 255, 0), 
                    2
                )

                if self.low_light_debug:
                    draw_debug_overlay(output_frame, raw_frame, light_info)
                
                # Update statistics
                self.update_statistics(fall_data)
                
                # Display the processed frame
                self.display_frame(output_frame)
            else:
                # Display the original frame without detection
                self.display_frame(frame)
    
    def display_frame(self, frame):
        """Display a frame in the video label."""
        # Resize the frame to fit the label
        h, w, ch = frame.shape
        bytes_per_line = ch * w
        
        # Convert to RGB format for Qt
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Convert to QImage and then to QPixmap
        qt_image = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(qt_image)
        
        # Scale pixmap to fit label while maintaining aspect ratio
        pixmap = pixmap.scaled(
            self.video_label.width(), 
            self.video_label.height(),
            Qt.KeepAspectRatio, 
            Qt.SmoothTransformation
        )
        
        # Update label
        self.video_label.setPixmap(pixmap)
        self.current_frame = frame  # Store for snapshot saving
    
    # Statistics and visualization methods
    def update_statistics(self, fall_data):
        """Update the statistics with new detection data."""
        # Update people count
        if "person_count" in fall_data:
            current_people = fall_data["person_count"]
            self.stats["total_people_detected"] = max(self.stats["total_people_detected"], current_people)
            self.people_count_label.setText(str(self.stats["total_people_detected"]))
        
        # Update fall statistics if a fall is detected
        if fall_data["fall_detected"]:
            # Debug print to see what keys are available
            print(f"Fall detected! Data keys: {fall_data.keys()}")
            print(f"Fall type from detector: {fall_data.get('fall_type', 'None')}")
            
            # Make sure we have a valid fall type
            fall_type = fall_data.get("fall_type")
            if not fall_type or fall_type not in self.stats["fall_types"]:
                # Default to a more common fall type if not specified or unknown
                fall_type = "slip_and_fall"  # Default fallback
                print(f"Using default fall type: {fall_type}")
            
            # Check for fallen IDs
            fallen_ids = []
            if "fallen_person_ids" in fall_data:
                fallen_ids = fall_data["fallen_person_ids"]
            elif "fallen_ids" in fall_data:
                fallen_ids = fall_data["fallen_ids"]
            
            # Get current time for cooldown check
            current_time = time.time()
            
            # If we have person IDs, use them for tracking
            if fallen_ids:
                # Convert to set for comparison
                current_fallen_ids = set(fallen_ids)
                
                # Filter out IDs that are still in cooldown period
                new_fallen_ids = set()
                for person_id in current_fallen_ids:
                    # Check if this is a new fall or if cooldown period has passed
                    if (person_id not in self.fallen_timestamps or 
                        current_time - self.fallen_timestamps.get(person_id, 0) > self.config.get("fall_cooldown", 5.0)):
                        new_fallen_ids.add(person_id)
                        # Update the timestamp for this person
                        self.fallen_timestamps[person_id] = current_time
                
                print(f"Current fallen IDs: {current_fallen_ids}")
                print(f"New fallen IDs (after cooldown): {new_fallen_ids}")
                
                if new_fallen_ids:
                    # Process new falls
                    self._process_new_falls(fall_type, new_fallen_ids, current_time)
            else:
                # No person IDs - use time-based cooldown
                if current_time - self.last_snapshot_time > self.snapshot_cooldown:
                    # Process as a single fall
                    self._process_new_falls(fall_type, {0}, current_time)  # Use dummy ID

    def update_pie_chart(self):
        """Update the pie chart with current fall type data."""
        # Clear previous chart
        self.pie_ax.clear()
        
        # Get fall type data
        fall_types = list(self.stats["fall_types"].keys())
        fall_counts = [self.stats["fall_types"][fall_type] for fall_type in fall_types]
        
        # Format labels
        fall_type_labels = [t.replace("_", " ").title() for t in fall_types]
        
        # Check if there's any data to display
        if sum(fall_counts) == 0:
            self.pie_ax.text(
                0.5, 0.5, 
                "No falls detected", 
                horizontalalignment='center',
                verticalalignment='center',
                transform=self.pie_ax.transAxes,
                fontsize=12
            )
        else:
            # Create the pie chart
            wedges, texts, autotexts = self.pie_ax.pie(
                fall_counts, 
                labels=fall_type_labels, 
                autopct='%1.1f%%',
                startangle=90,
                colors=['#4285f4', '#34a853', '#fbbc05', '#ea4335']  # Google colors
            )
            
            # Style the chart
            for text in texts:
                text.set_fontsize(9)
            for autotext in autotexts:
                autotext.set_fontsize(9)
                autotext.set_fontweight('bold')
        
        # Adjust layout and update
        self.pie_figure.tight_layout()
        self.pie_canvas.draw()
    
    def update_timeline_chart(self):
        """Update the timeline chart with fall detections over time."""
        # Clear previous chart
        self.timeline_ax.clear()
        
        # Check if we have any data
        if not self.stats["detection_history"]:
            self.timeline_ax.text(
                0.5, 0.5, 
                "No detection history", 
                horizontalalignment='center',
                verticalalignment='center',
                transform=self.timeline_ax.transAxes,
                fontsize=12
            )
        else:
            # Extract timestamps and convert to datetime objects
            timestamps = [entry[0] for entry in self.stats["detection_history"]]
            times = [datetime.datetime.strptime(ts, "%Y-%m-%d %H:%M:%S") for ts in timestamps]
            
            # Count falls by time (binned by minute)
            time_counts = {}
            for t in times:
                # Round to nearest minute to bin
                minute_time = t.replace(second=0)
                if minute_time in time_counts:
                    time_counts[minute_time] += 1
                else:
                    time_counts[minute_time] = 1
            
            # Sort times for plotting
            sorted_times = sorted(time_counts.keys())
            counts = [time_counts[t] for t in sorted_times]
            
            # Plot time series
            self.timeline_ax.plot(sorted_times, counts, marker='o', linestyle='-', 
                             color=ModernStyle.DARK_PRIMARY)
            self.timeline_ax.set_title('Falls Over Time')
            self.timeline_ax.set_ylabel('Count')
            
            # Format x-axis for better readability
            self.timeline_ax.xaxis.set_major_formatter(DateFormatter('%H:%M'))
            self.timeline_ax.tick_params(axis='x', rotation=45)
        
        # Adjust layout and update
        self.timeline_figure.tight_layout()
        self.timeline_canvas.draw()
    
    # History management methods
    def filter_history(self):
        """Filter history based on selected fall type."""
        filter_value = self.filter_combo.currentText()
        
        # Clear the current display
        self.history_tree.clear()
        
        # Add all entries that match the filter
        for timestamp, fall_type, details in self.get_filtered_history(filter_value):
            item = QTreeWidgetItem([timestamp, fall_type, details])
            self.history_tree.addTopLevelItem(item)

    def get_filtered_history(self, filter_value):
        """Get history entries matching the filter."""
        filtered_entries = []
        
        for item in self.stats["detection_history"]:
            timestamp, fall_type = item
            
            # Format the fall type for display
            display_fall_type = "Unknown"
            if fall_type:
                display_fall_type = fall_type.replace("_", " ").title()
            
            # Details
            details = "Fall detected with critical points identified"
            
            # Apply filter
            if filter_value == "All" or display_fall_type == filter_value:
                filtered_entries.append((timestamp, display_fall_type, details))
        
        return filtered_entries

    def export_history(self):
        """Export detection history to a CSV file."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Detection History",
            "",
            "CSV Files (*.csv);;All Files (*)"
        )
        
        if file_path:
            try:
                with open(file_path, 'w') as f:
                    f.write("Timestamp,Fall Type,Details\n")
                    
                    for timestamp, fall_type, details in self.get_filtered_history(self.filter_combo.currentText()):
                        f.write(f'"{timestamp}","{fall_type}","{details}"\n')
                
                QMessageBox.information(self, "Export Complete", f"History data has been exported to {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed to export history: {str(e)}")
    
    # Utility methods
    
    def play_alert_sound(self):
        """Play a voice alert when a fall is detected."""
        try:
            import subprocess

            script = (
                'Add-Type -AssemblyName System.Speech; '
                '$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; '
                '$s.Speak("낙상이 감지되었습니다")'
            )

            subprocess.Popen(
                ["powershell", "-NoProfile", "-Command", script],
                creationflags=subprocess.CREATE_NO_WINDOW
            )

        except Exception as e:
            print(f"Voice alert error: {e}")

    
    def save_fall_snapshot(self):
        """Save the current frame as an image when a fall is detected."""
        try:
            # Make sure output directory exists
            output_dir = self.config.get("output_dir", "fall_snapshots")
            os.makedirs(output_dir, exist_ok=True)
            
            # Create filename with timestamp
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"fall_{timestamp}.jpg"
            filepath = os.path.join(output_dir, filename)
            
            # Save the image if we have a current frame
            if hasattr(self, 'current_frame') and self.current_frame is not None:
                cv2.imwrite(filepath, self.current_frame)
                print(f"Fall snapshot saved to: {filepath}")
        except Exception as e:
            print(f"Error saving fall snapshot: {e}")
    
    def reset_statistics(self):
        """Reset all fall detection statistics."""
        reply = QMessageBox.question(
            self, 
            "Reset Statistics", 
            "Are you sure you want to reset all statistics?",
            QMessageBox.Yes | QMessageBox.No, 
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # Reset statistics
            self.stats = {
                "total_people_detected": 0,
                "total_falls_detected": 0,
                "fall_types": {
                    "step_and_fall": 0,
                    "slip_and_fall": 0, 
                    "trip_and_fall": 0,
                    "stump_and_fall": 0
                },
                "detection_history": []
            }
            
            # Reset tracked fallen IDs
            self.tracked_fallen_ids = set()
            
            # Update UI
            self.people_count_label.setText("0")
            self.fall_count_label.setText("0")
            
            for fall_type in self.fall_type_labels:
                self.fall_type_labels[fall_type].setText("0")
            
            # Clear detection tree
            self.history_tree.clear()
            
            # Update charts
            self.update_pie_chart()
            self.update_timeline_chart()
            
            QMessageBox.information(self, "Reset Complete", "Statistics have been reset.")

    def toggle_low_light_debug(self):
        # F10: 원본 썸네일과 밝기 정보를 영상 위에 표시
        self.low_light_debug = not self.low_light_debug
        print(f"[low-light] 디버그 표시 {'ON' if self.low_light_debug else 'OFF'}")

    def trigger_test_fall(self):
        # TEST: 가짜 낙상 1건 발생시키기 (F9)
        # 카메라 프레임이 없으면(웹캠 없음) test_images의 사진을 랜덤으로 골라 카메라 프레임 대신 사용
        if self._last_raw_frame is None:
            image_path = self._random_test_image()
            if image_path:
                self.trigger_test_fall_from_image(image_path)
                return
        self.test_fall_count = getattr(self, "test_fall_count", 0) + 1
        print("TEST: fake fall")
        self._process_new_falls("slip_and_fall", [-self.test_fall_count], time.time(), is_test=True)

    @staticmethod
    def _random_test_image():
        try:
            names = [n for n in os.listdir(TEST_IMAGE_DIR) if n.lower().endswith(TEST_IMAGE_EXTENSIONS)]
        except OSError:
            names = []
        if not names:
            print("TEST: test_images 폴더에 사진이 없어 사진 없는 가짜 낙상으로 진행합니다")
            return None
        return os.path.join(TEST_IMAGE_DIR, random.choice(names))

    def choose_test_image(self):
        # TEST: Shift+F9 - 사진을 직접 골라 가짜 낙상 발생
        image_path, _ = QFileDialog.getOpenFileName(
            self, "테스트 사진 선택", TEST_IMAGE_DIR, "Images (*.jpg *.jpeg *.png *.bmp)")
        if image_path:
            self.trigger_test_fall_from_image(image_path)

    def trigger_test_fall_from_image(self, image_path):
        """Fake fall that uses a photo in place of a camera frame, then follows the real fall path.

        The photo goes through the same steps as a camera frame (low-light correction, person
        detection, silhouette rendering, server upload, alerts). Only the processed silhouette
        image is saved to test_output/ for checking; the photo itself is never sent.
        """
        frame = cv2.imread(image_path)
        if frame is None:
            print(f"TEST: 사진을 읽을 수 없습니다: {image_path}")
            return
        try:
            self._ensure_fall_detector()
        except Exception as e:
            print(f"TEST: 감지 모델을 불러오지 못했습니다: {e}")
            return

        frame, _ = self.low_light.process(frame)
        output_frame, _, fall_data = self.fall_detector.process_frame(frame)
        boxes = fall_data.get("person_boxes", [])
        self.display_frame(output_frame)

        name = os.path.splitext(os.path.basename(image_path))[0]
        print(f"TEST: fake fall from image {os.path.basename(image_path)} (사람 {len(boxes)}명 감지)")
        self.test_fall_count = getattr(self, "test_fall_count", 0) + 1
        self._process_new_falls("slip_and_fall", [-self.test_fall_count], time.time(), is_test=True,
                                frame=frame, boxes=boxes, test_output_name=name)

    # ---- 앱 연결 (device_link.py) ----
    def _camera_ok(self):
        """For the status signal: the camera (or video) delivered a frame in the last few seconds."""
        return bool(self.is_running and self.cap is not None and time.time() - self._last_frame_ok_at < 5)

    def _sync_device_link(self):
        """Every second on the UI thread: follow the app's detection on/off, and show the connection state."""
        link = self.device_link
        if link.paired and not link.enabled and self.is_running and not self._remote_paused:
            # 앱에서 감지를 끔 → 카메라를 닫고 감지를 멈춤 (영상 분석·낙상 전송 없음)
            self.toggle_detection()
            self._remote_paused = True
            self.status_bar.showMessage("앱에서 이 기기의 감지를 껐어요. 카메라를 멈췄어요.")
            print("[device] 앱에서 감지를 꺼서 카메라 감지를 멈췄어요")
            link.nudge()
        elif self._remote_paused and (not link.paired or link.enabled):
            # 앱에서 다시 켬 (또는 연결이 해제됨) → 멈추기 전처럼 다시 시작
            self._remote_paused = False
            if not self.is_running:
                print("[device] 앱에서 감지를 켜서 카메라 감지를 다시 시작해요")
                self.start_detection()
                link.nudge()
        if not hasattr(self, "link_status_label"):
            return
        if link.revoked:
            text = "앱에서 연결이 해제됐어요. 앱에서 새 연결 코드를 받아 다시 연결해 주세요."
        elif not link.paired:
            text = "연결 안 됨 (예전 방식으로 전송해요)"
        else:
            info = link.info
            where = info.get("location") or ""
            if link.last_error:
                text = f"연결됨 · {where} · {link.last_error} (다시 시도 중)"
            elif not link.enabled:
                text = f"연결됨 · {where} · 앱에서 감지를 꺼 두었어요"
            elif link.last_ok_at:
                text = f"연결됨 · {where} · 감지 켜짐"
            else:
                text = f"연결됨 · {where} · 서버 응답 기다리는 중"
        self.link_status_label.setText(text)
        self.link_forget_btn.setEnabled(link.paired)

    def enter_pairing_code(self):
        code, ok = QInputDialog.getText(self, "앱과 연결", "앱의 '기기 추가'에서 받은 6자리 연결 코드를 입력해 주세요:")
        if not ok:
            return
        success, message = self.device_link.pair(code)
        (QMessageBox.information if success else QMessageBox.warning)(self, "앱과 연결", message)
        self._sync_device_link()

    def forget_device_link(self):
        answer = QMessageBox.question(self, "연결 해제",
                                      "이 PC에 저장된 기기 연결을 지울까요?\n앱의 기기 목록에서도 이 기기를 삭제해 주세요.\n"
                                      "해제하면 예전 방식(/api/events)으로 보내요.")
        if answer == QMessageBox.Yes:
            self.device_link.forget()
            self._sync_device_link()

    def _post_fall_event(self, fall_type, is_test, image_b64=None):
        """Send one fall event to the server, retrying on network/server errors.

        Blocking; call from a background thread. Success is only reported after the
        server confirms it (and confirms the image was saved, when one was sent).
        """
        event_id = uuid.uuid4().hex  # same id on every retry, so the server never records it twice
        if self.device_link.revoked:
            # 앱에서 기기를 삭제함: 예전 경로로 몰래 보내지 않음 (다시 연결하거나 'PC에서 연결 해제'를 누른 뒤에만 예전 방식)
            print(f"[device] 앱에서 기기 연결이 해제된 상태라 보내지 않았어요 (event {event_id[:8]})")
            self._log_send_failure(event_id, fall_type, "device revoked: not sent")
            return
        if self.device_link.paired:
            # 앱과 연결됨: 기기 토큰으로 새 API (그 집의 사고를 바로 만들고 사진 연결). 옛 경로로는 보내지 않음
            try:
                result = self.device_link.send_fall(event_id, fall_type, is_test, image_b64)
            except DeviceRevoked:
                print(f"[device] 앱에서 기기 연결이 해제돼 보내지 못했어요 (event {event_id[:8]}). 연결 코드로 다시 연결해 주세요.")
                self._log_send_failure(event_id, fall_type, "device revoked (401)")
                return
            except Exception as e:
                print(f"[device] 전송 실패 (event {event_id[:8]}): {e}")
                self._log_send_failure(event_id, fall_type, f"device: {e}")
                return
            if result.get("test"):
                print(f"[device] 시험 신호 전송 완료 (event {event_id[:8]}, 사고·알림 없음)")
            elif result.get("ignored") == "off":
                print(f"[device] 앱에서 감지를 꺼 둔 상태라 서버가 기록하지 않았어요 (event {event_id[:8]})")
            else:
                print(f"[device] 전송 완료 (event {event_id[:8]}, 사고 {result.get('incident_id')}"
                      f"{', 사진 연결' if result.get('image_saved') else ''})")
            return
        event = {
            "event_id": event_id,
            "device_id": DEVICE_ID,
            "fall_type": fall_type,
            "is_test": is_test,
        }
        if image_b64:
            event["image_jpeg_base64"] = image_b64
        payload = json.dumps(event).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        token = self._read_access_token()
        if token:
            headers["X-Access-Token"] = token

        error = None
        for attempt in range(len(SEND_RETRY_DELAYS) + 1):
            if attempt:
                time.sleep(SEND_RETRY_DELAYS[attempt - 1])
                print(f"[server] 재시도 {attempt}/{len(SEND_RETRY_DELAYS)} (event {event_id[:8]})")
            try:
                request = urllib.request.Request(self.event_server_url, data=payload, headers=headers, method="POST")
                with urllib.request.urlopen(request, timeout=3) as response:
                    result = json.loads(response.read())
            except urllib.error.HTTPError as e:
                error = f"HTTP {e.code}"
                if e.code < 500:
                    # 인증 실패(401)나 잘못된 요청(422)은 다시 보내도 같으므로 재시도하지 않음
                    if e.code == 401:
                        error += " (인증 실패: server/access_token.txt 확인)"
                    break
                continue
            except Exception as e:
                # 서버가 꺼져 있거나 네트워크 오류 - 재시도
                error = str(e)
                continue

            if not result.get("ok"):
                error = f"서버 응답 이상: {result}"
                break
            if image_b64 and not result.get("image_saved"):
                print(f"[server] 기록 저장됨, 이미지는 서버가 저장하지 못함 (event {event_id[:8]})")
                self._log_send_failure(event_id, fall_type, "image not saved by server")
                return
            print(f"[server] 전송 완료 (event {event_id[:8]}{', 이미지 포함' if image_b64 else ''})")
            return

        # 서버가 꺼져 있거나 전송에 실패해도 대시보드는 계속 동작
        print(f"[server] 전송 실패 (event {event_id[:8]}): {error}")
        self._log_send_failure(event_id, fall_type, error)

    @staticmethod
    def _read_access_token():
        try:
            with open(ACCESS_TOKEN_FILE, encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            return ""

    @staticmethod
    def _log_send_failure(event_id, fall_type, error):
        try:
            os.makedirs(os.path.dirname(SEND_FAILURE_LOG), exist_ok=True)
            with open(SEND_FAILURE_LOG, "a", encoding="utf-8") as f:
                f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} event={event_id} type={fall_type} error={error}\n")
        except OSError as e:
            print(f"[server] 실패 기록 저장 불가: {e}")

    def _send_fall_event(self, fall_type, is_test):
        """Send a fall event without an image in a background thread."""
        threading.Thread(target=self._post_fall_event, args=(fall_type, is_test), daemon=True).start()

    def _queue_fall_events(self, fall_type, is_test, count, frame=None, boxes=None, test_output_name=None):
        """Queue fall events (with a silhouette image when possible) for the worker thread.

        frame/boxes default to the latest camera frame; a test photo can be passed instead.
        """
        if frame is None:
            frame, boxes = self._last_raw_frame, self._last_person_boxes
        small_frame, small_boxes = None, []
        if frame is not None:
            try:
                # Downscaled copy only; the full-size raw frame is never queued
                small_frame, small_boxes = shrink_frame(frame, boxes or [])
            except Exception as e:
                print(f"[silhouette] 프레임 준비 실패: {e}")

        try:
            self._event_queue.put_nowait((fall_type, is_test, count, small_frame, small_boxes, test_output_name))
        except queue.Full:
            # Worker is busy: discard the frame but never lose the fall events
            print("[silhouette] 대기열이 가득 차 이미지 없이 전송합니다")
            for _ in range(count):
                self._send_fall_event(fall_type, is_test)

    def _event_worker_loop(self):
        """Render silhouette images and send fall events, one job at a time."""
        while True:
            fall_type, is_test, count, frame, boxes, test_output_name = self._event_queue.get()
            image_b64 = None
            try:
                jpeg = self._silhouette.render(frame, boxes)
                if jpeg:
                    image_b64 = base64.b64encode(jpeg).decode("ascii")
                    if test_output_name:
                        self._save_test_output(jpeg, test_output_name)
                else:
                    print("[silhouette] 실루엣 처리 실패 - 이미지 없이 전송합니다")
            except Exception as e:
                print(f"[silhouette] 실루엣 처리 오류 - 이미지 없이 전송합니다: {e}")
            finally:
                # Temporary frame is discarded whether or not rendering succeeded
                frame = None

            for _ in range(count):
                self._post_fall_event(fall_type, is_test, image_b64)

    @staticmethod
    def _save_test_output(jpeg, name):
        """Save the processed (silhouette) image of a test-photo fall for visual checking."""
        try:
            os.makedirs(TEST_OUTPUT_DIR, exist_ok=True)
            path = os.path.join(TEST_OUTPUT_DIR, f"{datetime.datetime.now():%Y%m%d_%H%M%S}_{name}_silhouette.jpg")
            with open(path, "wb") as f:
                f.write(jpeg)
            print(f"TEST: 가공된 이미지 저장: {path}")
        except OSError as e:
            print(f"TEST: 가공된 이미지 저장 실패: {e}")

    def _process_new_falls(self, fall_type, new_fallen_ids, current_time, is_test=False,
                           frame=None, boxes=None, test_output_name=None):
        """Process newly detected falls.

        frame/boxes: image to send instead of the latest camera frame (test photos).
        """
        # Increment counter by number of new falls
        self.stats["total_falls_detected"] += len(new_fallen_ids)
        self.fall_count_label.setText(str(self.stats["total_falls_detected"]))
        
        # Play sound alert if enabled
        if self.config.get("sound_alerts", True):
            self.play_alert_sound()
        
        # 원본 스냅샷은 저장하지 않음 (사생활 보호). 이 시각은 ID 없는 낙상의 중복 방지에도 쓰이므로 계속 갱신
        if current_time - self.last_snapshot_time > self.snapshot_cooldown:
            self.last_snapshot_time = current_time
        
        # Update fall types count
        self.stats["fall_types"][fall_type] += len(new_fallen_ids)
        self.fall_type_labels[fall_type].setText(str(self.stats["fall_types"][fall_type]))
        
        # Update tracking info
        self.tracked_fallen_ids.update(new_fallen_ids)
        
        # Add to detection history
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Format fall type for display
        display_fall_type = fall_type.replace("_", " ").title()
        
        # Create details string
        details = f"Fall detected: {display_fall_type}"
        
        # Add to history tree (most recent at top)
        item = QTreeWidgetItem([timestamp, display_fall_type, details])
        self.history_tree.insertTopLevelItem(0, item)
        
        # Add to history for charts
        self.stats["detection_history"].append((timestamp, fall_type))
        
        # Update the charts
        self.update_pie_chart()
        self.update_timeline_chart()
        
        # Print confirmation
        print(f"Recorded new fall of type: {fall_type}")

        # Send one event per newly fallen person to the server
        self._queue_fall_events(fall_type, is_test, len(new_fallen_ids), frame, boxes, test_output_name)

    def update_sensitivity_label(self, value):
        sensitivity_labels = {
            1: "Very Low", 2: "Low", 3: "Low-Medium", 
            4: "Medium-Low", 5: "Medium", 6: "Medium-High", 
            7: "High-Medium", 8: "High", 9: "Very High", 
            10: "Maximum"
        }
        self.sensitivity_label.setText(sensitivity_labels.get(value, "Medium"))

def run_dashboard_mode(args):
    """Run the fall detection system in dashboard mode."""
    # Switch from tkinter to PyQt5
    app = QApplication(sys.argv)
    window = FallDetectionDashboard()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    run_dashboard_mode(None) 