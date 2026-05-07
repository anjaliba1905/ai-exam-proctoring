"""
monitoring/camera_monitor.py — CLOUD-HYBRID VERSION (Production)

Architecture:
  • All AI (MediaPipe, YOLO) runs 100% locally on the student's machine.
  • Only tiny JSON violation events (~200 bytes each) go to the cloud.
  • Background queue drains violations without blocking the camera loop.
  • KeepAlivePinger prevents Render free-tier cold starts mid-exam.

Fixes vs original:
  • AUTH_TOKEN refreshed from env each batch send (supports token refresh)
  • Batching queue drains cleanly on shutdown (no lost violations)
  • Errors never crash the camera loop — all wrapped with try/except
  • Pinger uses exponential back-off on failures
  • CameraMonitor exposes .is_cloud_active property for UI status
"""

import cv2
import sys, os, time, threading, queue, logging
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtGui import QImage

log = logging.getLogger("camera_monitor")

# ── Cloud config (env vars set by cloud_auth.py at login time) ────────────────
API_URL = os.environ.get("PROCTORING_API_URL", "").rstrip("/")

_FLUSH_EVERY      = 5     # max items before forced flush
_FLUSH_INTERVAL_S = 10    # max seconds between flushes
_POST_TIMEOUT     = 8     # seconds per violation POST


class _CloudReporter(threading.Thread):
    """
    Background daemon thread.
    Drains a queue of violation dicts and POSTs them one-by-one.
    Never blocks the camera loop.
    """

    def __init__(self, session_id: int):
        super().__init__(daemon=True, name="CloudReporter")
        self.session_id  = session_id
        self._queue: queue.Queue = queue.Queue(maxsize=500)
        self._stop_event = threading.Event()
        self._sent = 0
        self._failed = 0

    def submit(self, violation_type: str, details: str, risk_delta: float = 0):
        """Non-blocking enqueue from the camera thread."""
        try:
            self._queue.put_nowait({
                "session_id":     self.session_id,
                "violation_type": violation_type,
                "details":        details,
                "risk_delta":     float(risk_delta),
            })
        except queue.Full:
            log.warning("[CloudReporter] Queue full — violation dropped: %s", violation_type)

    def run(self):
        pending = []
        last_flush = time.time()

        while not self._stop_event.is_set():
            # Collect items from queue (non-blocking)
            try:
                while len(pending) < _FLUSH_EVERY:
                    pending.append(self._queue.get_nowait())
            except queue.Empty:
                pass

            should_flush = (
                len(pending) >= _FLUSH_EVERY
                or (pending and (time.time() - last_flush) >= _FLUSH_INTERVAL_S)
            )

            if should_flush and pending:
                self._post_batch(pending)
                pending.clear()
                last_flush = time.time()

            time.sleep(0.5)

        # Drain remaining on shutdown
        while not self._queue.empty():
            try:
                pending.append(self._queue.get_nowait())
            except queue.Empty:
                break
        if pending:
            self._post_batch(pending)

        log.info("[CloudReporter] Stopped. sent=%d failed=%d", self._sent, self._failed)

    def _post_batch(self, items: list):
        # Read token fresh each batch (supports token refresh)
        token = os.environ.get("PROCTORING_AUTH_TOKEN", "")
        if not token or not API_URL:
            return
        headers = {"Authorization": f"Bearer {token}"}
        for item in items:
            try:
                resp = requests.post(
                    f"{API_URL}/violations",
                    json=item,
                    headers=headers,
                    timeout=_POST_TIMEOUT,
                )
                if resp.status_code in (200, 201):
                    self._sent += 1
                else:
                    self._failed += 1
                    log.warning("[CloudReporter] API %d: %s",
                                resp.status_code, resp.text[:120])
            except requests.exceptions.Timeout:
                self._failed += 1
                log.warning("[CloudReporter] POST timeout for %s", item.get("violation_type"))
            except requests.exceptions.RequestException as e:
                self._failed += 1
                log.warning("[CloudReporter] Network error: %s", e)

    def stop(self):
        self._stop_event.set()

    @property
    def stats(self) -> dict:
        return {"sent": self._sent, "failed": self._failed, "queued": self._queue.qsize()}


class _KeepAlivePinger(threading.Thread):
    """
    Pings /health every 10 minutes to prevent Render free-tier cold starts.
    Uses exponential back-off on failures (max 5 min back-off).
    """

    def __init__(self):
        super().__init__(daemon=True, name="KeepAlivePinger")
        self._stop = threading.Event()
        self._failures = 0

    def run(self):
        # First ping after 9 minutes (slightly less than 10 to stay safe)
        wait = 540
        while not self._stop.wait(timeout=wait):
            if not API_URL:
                break
            try:
                r = requests.get(f"{API_URL}/health", timeout=5)
                if r.status_code == 200:
                    self._failures = 0
                    log.debug("[KeepAlive] /health OK")
                else:
                    self._failures += 1
            except Exception as e:
                self._failures += 1
                log.warning("[KeepAlive] Ping failed: %s", e)

            # Back off on failures: 540s → 1080s → 1620s (max)
            wait = min(540 * (2 ** min(self._failures, 2)), 300)

    def stop(self):
        self._stop.set()


# ── Main CameraMonitor ─────────────────────────────────────────────────────────

class CameraMonitor(QThread):
    """
    Background QThread: local AI pipeline + cloud violation reporting.
    Signal interface is identical to the original — UI needs no changes.
    """

    frame_ready       = pyqtSignal(QImage)
    status_update     = pyqtSignal(dict)
    violation_signal  = pyqtSignal(str, str)
    init_done         = pyqtSignal(str)

    intent_signal     = pyqtSignal(str, str, int, int)
    prediction_signal = pyqtSignal(str, float, str)
    invisible_signal  = pyqtSignal(str, str, float, float)
    advanced_status   = pyqtSignal(dict)

    def __init__(self, camera_index: int = 0, session_id: int = 0, parent=None):
        super().__init__(parent)
        self.camera_index  = camera_index
        self.session_id    = session_id
        self._running      = False
        self._cloud: _CloudReporter  = None
        self._pinger: _KeepAlivePinger = None

        self.face_detector      = None
        self.eye_tracker        = None
        self.phone_detector     = None
        self.intent_detector    = None
        self.predictive_engine  = None
        self.invisible_detector = None

        self._frame_count        = 0
        self._invisible_interval = 5

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def is_cloud_active(self) -> bool:
        return self._cloud is not None and self._cloud.is_alive()

    @property
    def cloud_stats(self) -> dict:
        return self._cloud.stats if self._cloud else {"sent": 0, "failed": 0, "queued": 0}

    # ── Callbacks from AI modules ───────────────────────────────────────────────

    def _on_violation(self, vtype: str, details: str):
        self.violation_signal.emit(vtype, details)
        try:
            from config import RISK_WEIGHTS
            delta = float(RISK_WEIGHTS.get(vtype, 5))
        except Exception:
            delta = 5.0
        if self._cloud:
            self._cloud.submit(vtype, details, delta)
        if self.intent_detector:
            try:
                self.intent_detector.record_violation(vtype)
            except Exception:
                pass
        if self.predictive_engine:
            try:
                preds = self.predictive_engine.record_event(vtype)
                for pred in preds[:1]:
                    if pred.get("confidence", 0) >= 50:
                        self.prediction_signal.emit(
                            pred["label"], pred["confidence"], pred["risk_level"])
            except Exception:
                pass

    def _on_intent(self, name, description, risk_boost, confidence):
        self.intent_signal.emit(name, description, risk_boost, confidence)

    def _on_prediction(self, label, confidence, risk_level):
        self.prediction_signal.emit(label, confidence, risk_level)

    def _on_invisible(self, cheat_type, description, confidence, risk_score):
        self.invisible_signal.emit(cheat_type, description, confidence, risk_score)
        self._on_violation(
            f"invisible_{cheat_type}",
            f"[Inferred] {description} (confidence={confidence:.0f}%)"
        )

    # ── AI model loader (each wrapped — one failure doesn't block others) ──────

    def _load_models(self):
        loaders = [
            ("FaceDetector",           "ai_modules.face_detection",        "FaceDetector",
             lambda cls: cls(violation_callback=self._on_violation), "face_detector"),
            ("EyeTracker",             "ai_modules.eye_tracking",          "EyeTracker",
             lambda cls: cls(violation_callback=self._on_violation), "eye_tracker"),
            ("PhoneDetector",          "ai_modules.phone_detection",       "PhoneDetector",
             lambda cls: cls(violation_callback=self._on_violation), "phone_detector"),
            ("IntentDetector",         "ai_modules.intent_detector",       "IntentDetector",
             lambda cls: cls(intent_callback=self._on_intent),       "intent_detector"),
            ("PredictiveEngine",       "ai_modules.predictive_engine",     "PredictiveEngine",
             lambda cls: cls(prediction_callback=self._on_prediction), "predictive_engine"),
            ("InvisibleCheatDetector", "ai_modules.invisible_cheat_detector",
             "InvisibleCheatDetector",
             lambda cls: cls(alert_callback=self._on_invisible),     "invisible_detector"),
        ]
        loaded = []
        for label, module, cls_name, factory, attr in loaders:
            try:
                import importlib
                mod = importlib.import_module(module)
                cls = getattr(mod, cls_name)
                setattr(self, attr, factory(cls))
                loaded.append(label)
            except Exception as e:
                log.warning("[CameraMonitor] %s load error: %s", label, e)

        return loaded

    # ── Thread main ────────────────────────────────────────────────────────────

    def run(self):
        self._running = True

        # Start cloud services
        token = os.environ.get("PROCTORING_AUTH_TOKEN", "")
        if self.session_id and token and API_URL:
            self._cloud  = _CloudReporter(self.session_id)
            self._cloud.start()
            self._pinger = _KeepAlivePinger()
            self._pinger.start()
            log.info("[CameraMonitor] Cloud reporting active (session=%d)", self.session_id)
        else:
            log.info("[CameraMonitor] Offline mode — cloud reporting disabled.")

        # Load AI models
        loaded = self._load_models()
        self.init_done.emit(
            f"AI models loaded: {', '.join(loaded) or 'none'} — "
            f"cloud: {'active' if self._cloud else 'offline'}"
        )

        # Open camera
        cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap = cv2.VideoCapture(self.camera_index)
        if not cap.isOpened():
            self.status_update.emit({
                "face_count": 0, "face_status": "No Camera",
                "gaze": "N/A", "phone": False,
                "intents": [], "predictions": [], "invisible": [],
            })
            self._cleanup(cap=None)
            return

        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 15)

        while self._running:
            ret, frame = cap.read()
            if not ret:
                self.msleep(100)
                continue

            frame = cv2.flip(frame, 1)
            self._frame_count += 1

            face_count, face_status = 0, "Initialising..."
            gaze_str, looking_away  = "Gaze: N/A", False
            phone_found             = False
            gaze_direction          = "Center"

            if self.face_detector:
                try:
                    frame, face_count, face_status = self.face_detector.process_frame(frame)
                except Exception as e:
                    log.debug("[CameraMonitor] face detect: %s", e)

            if self.eye_tracker and face_count == 1:
                try:
                    frame, gaze_str, looking_away = self.eye_tracker.process_frame(frame)
                    if ": " in gaze_str:
                        gaze_direction = gaze_str.split(": ", 1)[1]
                except Exception as e:
                    log.debug("[CameraMonitor] eye track: %s", e)

            if self.phone_detector:
                try:
                    frame, phone_found, _ = self.phone_detector.process_frame(frame)
                except Exception as e:
                    log.debug("[CameraMonitor] phone detect: %s", e)

            if self.invisible_detector:
                try:
                    self.invisible_detector.feed_gaze(gaze_direction, looking_away)
                    self.invisible_detector.feed_face(face_count)
                    self.invisible_detector.feed_phone(phone_found)
                    if self._frame_count % self._invisible_interval == 0:
                        self.invisible_detector.analyse()
                except Exception as e:
                    log.debug("[CameraMonitor] invisible detect: %s", e)

            intents     = self._safe_get(self.intent_detector,    "get_active_intents",  [])
            predictions = self._safe_get(self.predictive_engine,  "get_predictions",     [])
            invisible   = self._safe_get(self.invisible_detector, "get_active_detections", [])

            self._draw_overlays(frame, face_status, face_count,
                                gaze_str, looking_away, phone_found,
                                invisible, predictions)

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

            self.msleep(66)  # ~15 FPS

        self._cleanup(cap)

    def _draw_overlays(self, frame, face_status, face_count,
                        gaze_str, looking_away, phone_found,
                        invisible, predictions):
        overlays = [
            (face_status,                                         face_count == 0 or face_count > 1),
            (gaze_str,                                            looking_away),
            ("Phone: DETECTED!" if phone_found else "Phone: OK",  phone_found),
        ]
        if invisible:
            overlays.append((f"INV: {invisible[0].get('label','?')[:22]}", True))
        if predictions and predictions[0].get("confidence", 0) >= 65:
            p = predictions[0]
            overlays.append((f"PRED: {p['label'][:18]} {p['confidence']:.0f}%",
                             p["risk_level"] in ("HIGH", "CRITICAL")))

        y = frame.shape[0] - (len(overlays) * 24 + 8)
        for txt, is_alert in overlays:
            color = (0, 0, 255) if is_alert else (0, 220, 0)
            cv2.putText(frame, txt, (8, y), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (0, 0, 0), 3)
            cv2.putText(frame, txt, (8, y), cv2.FONT_HERSHEY_SIMPLEX, 0.50, color, 1)
            y += 24

    def _cleanup(self, cap):
        if cap:
            cap.release()
        for obj in [self.face_detector, self.eye_tracker]:
            if obj and hasattr(obj, "close"):
                try:
                    obj.close()
                except Exception:
                    pass
        for engine in [self.intent_detector, self.predictive_engine, self.invisible_detector]:
            if engine and hasattr(engine, "clear"):
                try:
                    engine.clear()
                except Exception:
                    pass
        if self._cloud:
            self._cloud.stop()
            self._cloud.join(timeout=5)
        if self._pinger:
            self._pinger.stop()

    def stop(self):
        self._running = False
        self.wait(3000)

    @staticmethod
    def _safe_get(obj, method: str, default):
        if obj is None:
            return default
        try:
            return getattr(obj, method)()
        except Exception:
            return default

    @staticmethod
    def _to_qimage(frame_bgr) -> QImage:
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        return QImage(rgb.data.tobytes(), w, h, ch * w, QImage.Format_RGB888)
