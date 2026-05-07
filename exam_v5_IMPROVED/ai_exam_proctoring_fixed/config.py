# config.py - System-wide configuration constants

import os

# ─── Paths ───────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
MODELS_DIR = os.path.join(BASE_DIR, "models")
DB_PATH = os.path.join(DATA_DIR, "violations.db")
YOLO_MODEL_PATH = os.path.join(MODELS_DIR, "yolov8n.pt")

# ─── App Info ─────────────────────────────────────────────────────────────────
APP_NAME = "AI Exam Proctoring System"
APP_VERSION = "1.0.0"
TEACHER_USERNAME = "admin"
TEACHER_PASSWORD = "admin123"

# ─── Exam Settings ────────────────────────────────────────────────────────────
EXAM_DURATION_MINUTES = 30
TOTAL_QUESTIONS = 20

# ─── Monitoring Intervals (milliseconds) ─────────────────────────────────────
CAMERA_FRAME_INTERVAL = 100
AUDIO_CHECK_INTERVAL = 3000
SCREEN_CHECK_INTERVAL = 2000
VIOLATION_LOG_COOLDOWN = 5

# ─── Face Detection Thresholds ───────────────────────────────────────────────
FACE_MISSING_THRESHOLD = 5
MULTIPLE_FACE_THRESHOLD = 1

# ─── Eye Tracking Thresholds ─────────────────────────────────────────────────
EYE_GAZE_AWAY_THRESHOLD = 8
GAZE_LEFT_THRESHOLD = -0.35
GAZE_RIGHT_THRESHOLD = 0.35
GAZE_UP_THRESHOLD = -0.3

# ─── Phone Detection ─────────────────────────────────────────────────────────
PHONE_CONFIDENCE_THRESHOLD = 0.45
PHONE_CLASSES = [67]

# ─── Audio Monitoring ────────────────────────────────────────────────────────
AUDIO_SAMPLE_RATE = 22050
AUDIO_CHUNK_DURATION = 2
AUDIO_ENERGY_THRESHOLD = 0.02
AUDIO_SPEECH_DURATION = 4

# ─── Risk Scoring Weights ────────────────────────────────────────────────────
RISK_WEIGHTS = {
    "phone_detected": 30,
    "multiple_faces": 25,
    "no_face": 15,
    "gaze_away": 10,
    "tab_switch": 20,
    "audio_alert": 15,
}

RISK_THRESHOLDS = {
    "low": 30,     # score <= 30  → Low Risk
    "medium": 60,  # score <= 60  → Medium Risk
                   # score  > 60  → High Risk (implicit else)
}

# ─── UI Colors ────────────────────────────────────────────────────────────────
COLOR_PRIMARY = "#1a1a2e"
COLOR_SECONDARY = "#16213e"
COLOR_ACCENT = "#0f3460"
COLOR_HIGHLIGHT = "#e94560"
COLOR_SUCCESS = "#00b894"
COLOR_WARNING = "#fdcb6e"
COLOR_DANGER = "#d63031"
COLOR_TEXT = "#dfe6e9"
COLOR_TEXT_MUTED = "#636e72"
COLOR_CARD = "#0d1b2a"

# ─── Invisible Cheat Detection Risk Weights (added) ──────────────────────────
INVISIBLE_CHEAT_RISK_WEIGHTS = {
    "invisible_hidden_earpiece":           25,
    "invisible_hidden_phone_under_desk":   30,
    "invisible_offscreen_notes":           20,
    "invisible_remote_assistance":         25,
    "invisible_smart_glasses_or_contact_lens": 18,
}

# Merge into main RISK_WEIGHTS so RiskScorer picks them up automatically
RISK_WEIGHTS.update(INVISIBLE_CHEAT_RISK_WEIGHTS)

# ─── Predictive Engine Settings ───────────────────────────────────────────────
PREDICTION_CONFIDENCE_THRESHOLD = 50    # % confidence to show prediction in UI
PREDICTION_DISPLAY_MAX          = 3     # max predictions shown in panel

# ─── Intent Detection Settings ────────────────────────────────────────────────
INTENT_COOLDOWN_SECONDS = 15            # min seconds between duplicate intent alerts
INTENT_DISPLAY_MAX      = 3             # max intents shown in panel
