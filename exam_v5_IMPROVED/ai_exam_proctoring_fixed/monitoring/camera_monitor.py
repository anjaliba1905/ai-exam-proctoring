# monitoring/camera_monitor.py - Webcam capture + AI pipeline
# UPGRADED: Integrates IntentDetector, PredictiveEngine, InvisibleCheatDetector
# AI models loaded inside run() (background thread) — never blocks UI.

import cv2
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtGui import QImage


class CameraMonitor(QThread):
    """
    Background thread that:
      1. Loads AI models (MediaPipe, YOLO, Intent, Predictive, Invisible) inside thread
      2. Captures webcam frames continuously
      3. Runs face / eye / phone / intent / predictive / invisible pipeline
      4. Emits annotated frame + rich status signals back to UI
    """

    frame_ready         = pyqtSignal(QImage)
    status_update       = pyqtSignal(dict)
    violation_signal    = pyqtSignal(str, str)
    init_done           = pyqtSignal(str)

    # New signals for advanced features
    intent_signal       = pyqtSignal(str, str, int, int)      # name, desc, risk_boost, confidence
    prediction_signal   = pyqtSignal(str, float, str)         # label, confidence, risk_level
    invisible_signal    = pyqtSignal(str, str, float, float)  # type, desc, confidence, risk
    advanced_status     = pyqtSignal(dict)                    # intents + predictions + invisible

    def __init__(self, camera_index=0, parent=None):
        super().__init__(parent)
        self.camera_index = camera_index
        self._running = False
        self.face_detector       = None
        self.eye_tracker         = None
        self.phone_detector      = None
        self.intent_detector     = None
        self.predictive_engine   = None
        self.invisible_detector  = None
        self._frame_count        = 0
        self._invisible_interval = 5

    def _on_violation(self, vtype, details):
        self.violation_signal.emit(vtype, details)
        if self.intent_detector:
            self.intent_detector.record_violation(vtype)
        if self.predictive_engine:
            preds = self.predictive_engine.record_event(vtype)
            for pred in preds[:1]:
                if pred["confidence"] >= 50:
                    self.prediction_signal.emit(
                        pred["label"], pred["confidence"], pred["risk_level"])

    def _on_intent(self, name, description, risk_boost, confidence):
        self.intent_signal.emit(name, description, risk_boost, confidence)

    def _on_prediction(self, label, confidence, risk_level):
        self.prediction_signal.emit(label, confidence, risk_level)

    def _on_invisible(self, cheat_type, description, confidence, risk_score):
        self.invisible_signal.emit(cheat_type, description, confidence, risk_score)
        self.violation_signal.emit(
            f"invisible_{cheat_type}",
            f"[Inferred] {description} (confidence={confidence:.0f}%)"
        )

    def run(self):
        self._running = True

        # Load core AI modules
        try:
            from ai_modules.face_detection import FaceDetector
            self.face_detector = FaceDetector(violation_callback=self._on_violation)
        except Exception as e:
            print(f"[CameraMonitor] FaceDetector load error: {e}")

        try:
            from ai_modules.eye_tracking import EyeTracker
            self.eye_tracker = EyeTracker(violation_callback=self._on_violation)
        except Exception as e:
            print(f"[CameraMonitor] EyeTracker load error: {e}")

        try:
            from ai_modules.phone_detection import PhoneDetector
            self.phone_detector = PhoneDetector(violation_callback=self._on_violation)
        except Exception as e:
            print(f"[CameraMonitor] PhoneDetector load error: {e}")

        # Load advanced engines
        try:
            from ai_modules.intent_detector import IntentDetector
            self.intent_detector = IntentDetector(intent_callback=self._on_intent)
            print("[CameraMonitor] IntentDetector loaded OK.")
        except Exception as e:
            print(f"[CameraMonitor] IntentDetector load error: {e}")

        try:
            from ai_modules.predictive_engine import PredictiveEngine
            self.predictive_engine = PredictiveEngine(prediction_callback=self._on_prediction)
            print("[CameraMonitor] PredictiveEngine loaded OK.")
        except Exception as e:
            print(f"[CameraMonitor] PredictiveEngine load error: {e}")

        try:
            from ai_modules.invisible_cheat_detector import InvisibleCheatDetector
            self.invisible_detector = InvisibleCheatDetector(alert_callback=self._on_invisible)
            print("[CameraMonitor] InvisibleCheatDetector loaded OK.")
        except Exception as e:
            print(f"[CameraMonitor] InvisibleCheatDetector load error: {e}")

        self.init_done.emit("AI models loaded")

        # Open webcam
        cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap = cv2.VideoCapture(self.camera_index)
        if not cap.isOpened():
            self.status_update.emit({
                "face_count": 0, "face_status": "No Camera",
                "gaze": "N/A", "phone": False,
                "intents": [], "predictions": [], "invisible": [],
            })
            print(f"[CameraMonitor] Could not open camera index {self.camera_index}")
            return

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 15)

        while self._running:
            ret, frame = cap.read()
            if not ret:
                self.msleep(100)
                continue

            frame = cv2.flip(frame, 1)
            self._frame_count += 1

            face_count     = 0
            face_status    = "Initialising..."
            gaze_str       = "Gaze: N/A"
            phone_found    = False
            looking_away   = False
            gaze_direction = "Center"

            if self.face_detector:
                try:
                    frame, face_count, face_status = self.face_detector.process_frame(frame)
                except Exception as e:
                    print(f"[CameraMonitor] face detect error: {e}")

            if self.eye_tracker and face_count == 1:
                try:
                    frame, gaze_str, looking_away = self.eye_tracker.process_frame(frame)
                    if ": " in gaze_str:
                        gaze_direction = gaze_str.split(": ", 1)[1]
                except Exception as e:
                    print(f"[CameraMonitor] eye track error: {e}")

            if self.phone_detector:
                try:
                    frame, phone_found, _ = self.phone_detector.process_frame(frame)
                except Exception as e:
                    print(f"[CameraMonitor] phone detect error: {e}")

            # Feed invisible detector
            if self.invisible_detector:
                try:
                    self.invisible_detector.feed_gaze(gaze_direction, looking_away)
                    self.invisible_detector.feed_face(face_count)
                    self.invisible_detector.feed_phone(phone_found)
                except Exception as e:
                    print(f"[CameraMonitor] invisible feed error: {e}")

                if self._frame_count % self._invisible_interval == 0:
                    try:
                        self.invisible_detector.analyse()
                    except Exception as e:
                        print(f"[CameraMonitor] invisible analyse error: {e}")

            # Gather advanced status
            intents     = self.intent_detector.get_active_intents()      if self.intent_detector    else []
            predictions = self.predictive_engine.get_predictions()       if self.predictive_engine  else []
            invisible   = self.invisible_detector.get_active_detections() if self.invisible_detector else []

            # Build overlays
            overlays = [
                (face_status,                                        face_count == 0 or face_count > 1),
                (gaze_str,                                           looking_away),
                ("Phone: DETECTED!" if phone_found else "Phone: OK", phone_found),
            ]
            if invisible:
                top_inv = invisible[0]
                overlays.append((f"INV: {top_inv['label'][:22]}", True))
            if predictions and predictions[0]["confidence"] >= 65:
                pred = predictions[0]
                overlays.append((
                    f"PRED: {pred['label'][:18]} {pred['confidence']:.0f}%",
                    pred["risk_level"] in ("HIGH", "CRITICAL")
                ))

            y_start = frame.shape[0] - (len(overlays) * 24 + 8)
            for txt, is_alert in overlays:
                color = (0, 0, 255) if is_alert else (0, 220, 0)
                cv2.putText(frame, txt, (8, y_start),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.50, (0, 0, 0), 3)
                cv2.putText(frame, txt, (8, y_start),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.50, color, 1)
                y_start += 24

            qt_img = self._to_qimage(frame)
            self.frame_ready.emit(qt_img)
            self.status_update.emit({
                "face_count":  face_count,
                "face_status": face_status,
                "gaze":        gaze_str,
                "phone":       phone_found,
            })

            if self._frame_count % 3 == 0:
                self.advanced_status.emit({
                    "intents":     intents,
                    "predictions": predictions,
                    "invisible":   invisible,
                })

            self.msleep(66)

        # Cleanup
        cap.release()
        if self.face_detector:
            self.face_detector.close()
        if self.eye_tracker:
            self.eye_tracker.close()
        for engine in [self.intent_detector, self.predictive_engine, self.invisible_detector]:
            if engine and hasattr(engine, "clear"):
                try:
                    engine.clear()
                except Exception:
                    pass

    def stop(self):
        self._running = False
        self.wait(3000)

    @staticmethod
    def _to_qimage(frame_bgr):
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        bytes_per_line = ch * w
        return QImage(rgb.data.tobytes(), w, h, bytes_per_line, QImage.Format_RGB888)
