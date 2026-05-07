# 🎓 AI Exam Proctoring System

A complete desktop exam proctoring application built with Python, PyQt5, and AI/ML libraries.

## Features

| Module | Technology | What It Does |
|---|---|---|
| **Face Detection** | OpenCV + MediaPipe | Detects missing/multiple faces |
| **Eye Tracking** | MediaPipe Face Mesh | Monitors gaze direction |
| **Phone Detection** | YOLOv8 | Detects mobile phones via camera |
| **Audio Monitoring** | Librosa + sounddevice | Detects speech/background noise |
| **Screen Monitor** | PyQt5 | Detects window/tab switching |
| **Risk Scoring** | Scikit-learn | Calculates cheating probability |
| **Teacher Dashboard** | PyQt5 | Admin panel with full analytics |
| **Database** | SQLite | Stores students, sessions, violations |

## Project Structure

```
ai_exam_proctoring/
├── main_app.py              # Entry point
├── config.py                # All configuration constants
├── database.py              # SQLite data layer
├── requirements.txt
│
├── ui/
│   ├── login_window.py      # Student + Teacher login
│   └── exam_window.py       # Main exam interface
│
├── monitoring/
│   ├── camera_monitor.py    # Webcam capture + AI pipeline
│   ├── audio_monitor.py     # Microphone analysis
│   └── screen_monitor.py    # Window focus detection
│
├── ai_modules/
│   ├── face_detection.py    # MediaPipe face detection
│   ├── eye_tracking.py      # Iris-based gaze tracking
│   ├── phone_detection.py   # YOLOv8 phone detection
│   └── risk_scoring.py      # ML risk calculator
│
├── dashboard/
│   └── teacher_dashboard.py # Teacher admin dashboard
│
├── models/
│   └── yolov8n.pt           # Auto-downloaded on first run
│
└── data/
    └── violations.db        # SQLite database (auto-created)
```

## Installation

### Prerequisites
- Python 3.9 or 3.10 (recommended)
- Webcam connected
- Microphone connected

### Step 1: Create Virtual Environment
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### Step 2: Install Dependencies
```bash
pip install -r requirements.txt
```

> Note: YOLOv8 model (`yolov8n.pt`) downloads automatically (~6 MB) on first run.

### Step 3: Run the Application
```bash
python main_app.py
```

## Login Credentials

### Student Login
| Student ID | Password | Name |
|---|---|---|
| STU001 | pass123 | Aarav Shah |
| STU002 | pass123 | Priya Patel |
| STU003 | pass123 | Rohan Mehta |
| STU004 | pass123 | Sneha Joshi |
| STU005 | pass123 | Kiran Desai |

### Teacher Login
- **Username:** `admin`
- **Password:** `admin123`

## Exam Details
- **20 questions** covering: Python, OOP, Algorithms, Data Structures, Networking, Databases, OS
- **30 minutes** time limit
- Questions are stored in the SQLite database

## Violation Types Monitored

| Type | Trigger | Risk Weight |
|---|---|---|
| `phone_detected` | Mobile phone in camera view | 30 pts |
| `multiple_faces` | More than 1 face visible | 25 pts |
| `tab_switch` | Window loses focus | 20 pts |
| `no_face` | No face for 5+ seconds | 15 pts |
| `audio_alert` | Speech detected 4+ seconds | 15 pts |
| `gaze_away` | Looking away 8+ seconds | 10 pts |

## Risk Levels
- 🟢 **Low Risk**: Score 0–30
- 🟡 **Medium Risk**: Score 31–60
- 🔴 **High Risk**: Score 61–100

## Configuration
Edit `config.py` to customise:
- Exam duration (`EXAM_DURATION_MINUTES`)
- Detection thresholds
- Risk scoring weights
- Teacher credentials

## Troubleshooting

**Camera not found**: Change `camera_index=0` to `1` or `2` in `monitoring/camera_monitor.py`

**sounddevice error**: Install PortAudio:
```bash
# Ubuntu/Debian
sudo apt install portaudio19-dev

# macOS
brew install portaudio

# Then reinstall
pip install sounddevice
```

**MediaPipe iris tracking**: Requires Python 3.9–3.11. Not yet supported on Python 3.12+.
