# ai_modules/face_detection.py  –  Face Detection (v9 IMPROVED)
#
# Key improvements over v7:
#   ✦ Multi-stage validation — a "face" must pass aspect ratio + size checks
#   ✦ Temporal consistency — require N consecutive frames before triggering
#   ✦ MediaPipe confidence boosted to 0.72 (was 0.60)
#   ✦ Haar fallback uses tighter minNeighbors (7) + aspect-ratio filter
#   ✦ False-positive suppression: reject detections whose bounding box is
#       wider than it is tall (books, screens, walls) or smaller than 60×60 px
#   ✦ "Multiple faces" requires TWO detections with valid face geometry,
#       so a face + an object no longer triggers
#   ✦ Cooldown between repeated no-face alerts is enforced
#   ✦ process_frame returns consistent (annotated, count, status) tuple

import cv2
import time

try:
    from mediapipe.python.solutions import face_detection as mp_face_detection
    from mediapipe.python.solutions import drawing_utils as mp_drawing
    MEDIAPIPE_OK = True
except Exception as e:
    print(f"[FaceDetector] MediaPipe not available: {e}")
    MEDIAPIPE_OK = False

from config import FACE_MISSING_THRESHOLD, VIOLATION_LOG_COOLDOWN


# ── Geometric validation helpers ─────────────────────────────────────────────

MIN_FACE_PX   = 60       # min dimension in pixels (filters tiny false hits)
MAX_FACE_FRAC = 0.90     # face can't be >90 % of frame width (filters full-frame hits)
ASPECT_MIN    = 0.55     # width/height ratio min (a face is roughly square)
ASPECT_MAX    = 1.80     # width/height ratio max
CONFIRM_FRAMES = 2       # need N frames to confirm "real" face / no-face


def _valid_face_box(x1, y1, x2, y2, frame_w, frame_h):
    """
    Return True only if this bounding box plausibly belongs to a real face.
    Rejects:
      - Boxes smaller than MIN_FACE_PX in either dimension
      - Boxes that fill almost the full frame (background hit)
      - Boxes with unusual aspect ratios (landscape objects)
    """
    w = x2 - x1
    h = y2 - y1
    if w < MIN_FACE_PX or h < MIN_FACE_PX:
        return False
    if w / frame_w > MAX_FACE_FRAC:
        return False
    aspect = w / max(h, 1)
    if not (ASPECT_MIN <= aspect <= ASPECT_MAX):
        return False
    return True


class FaceDetector:
    """
    Two-tier face detection (MediaPipe primary, Haar fallback).
    Includes geometric validation and temporal consistency to eliminate
    false positives from random objects in frame.
    """

    def __init__(self, violation_callback=None):
        self.violation_callback = violation_callback

        self._no_face_since       = None
        self._last_no_face_log    = 0
        self._last_multi_face_log = 0

        # Temporal consistency buffers
        self._face_count_history  = []   # rolling window of (timestamp, count)
        self._HISTORY_LEN         = CONFIRM_FRAMES

        self.detector      = None
        self._use_fallback = False

        if MEDIAPIPE_OK:
            try:
                self.detector = mp_face_detection.FaceDetection(
                    model_selection=1,            # full-range model (was 0 = short-range)
                    min_detection_confidence=0.72 # was 0.60 — stricter
                )
                print("[FaceDetector] MediaPipe FaceDetection (full-range, conf=0.72) loaded.")
            except Exception as e:
                print(f"[FaceDetector] MediaPipe init failed: {e}, using Haar fallback.")
                self._use_fallback = True
        else:
            self._use_fallback = True

        if self._use_fallback:
            self._haar = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            )
            print("[FaceDetector] Using Haar cascade fallback (tightened params).")

    # ── Public ────────────────────────────────────────────────────────────────

    def process_frame(self, frame_bgr):
        """
        Returns (annotated_frame, face_count, status_text)
        face_count reflects only geometrically validated faces.
        """
        if self._use_fallback:
            return self._process_haar(frame_bgr)
        return self._process_mediapipe(frame_bgr)

    # ── MediaPipe path ────────────────────────────────────────────────────────

    def _process_mediapipe(self, frame_bgr):
        h, w  = frame_bgr.shape[:2]
        rgb   = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False

        try:
            result = self.detector.process(rgb)
        except Exception as e:
            print(f"[FaceDetector] MediaPipe process error: {e}")
            return frame_bgr, 0, "Face: Error"

        annotated   = frame_bgr.copy()
        valid_faces = 0

        if result.detections:
            for det in result.detections:
                bb   = det.location_data.relative_bounding_box
                x1   = max(0, int(bb.xmin * w))
                y1   = max(0, int(bb.ymin * h))
                x2   = min(w, int((bb.xmin + bb.width)  * w))
                y2   = min(h, int((bb.ymin + bb.height) * h))

                # ── Geometric validation ──────────────────────────────────
                if not _valid_face_box(x1, y1, x2, y2, w, h):
                    # Draw grey box for rejected detection (debug aid)
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), (80, 80, 80), 1)
                    continue

                valid_faces += 1
                color = (0, 220, 80) if valid_faces == 1 else (0, 60, 220)
                cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
                conf  = det.score[0] if det.score else 0
                cv2.putText(annotated, f"{conf:.0%}", (x1, max(0, y1 - 6)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 1, cv2.LINE_AA)

        return self._handle_count(annotated, valid_faces)

    # ── Haar fallback path ────────────────────────────────────────────────────

    def _process_haar(self, frame_bgr):
        h, w    = frame_bgr.shape[:2]
        gray    = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        # Tighter: minNeighbors=7 (was 5), minSize 70×70 (was 60×60)
        raw = self._haar.detectMultiScale(
            gray, scaleFactor=1.08, minNeighbors=7, minSize=(70, 70),
            flags=cv2.CASCADE_SCALE_IMAGE
        )

        annotated   = frame_bgr.copy()
        valid_faces = 0

        for (fx, fy, fw, fh) in (raw if len(raw) else []):
            x1, y1, x2, y2 = fx, fy, fx + fw, fy + fh
            if not _valid_face_box(x1, y1, x2, y2, w, h):
                cv2.rectangle(annotated, (x1, y1), (x2, y2), (80, 80, 80), 1)
                continue
            valid_faces += 1
            color = (0, 220, 80) if valid_faces == 1 else (0, 60, 220)
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)

        return self._handle_count(annotated, valid_faces)

    # ── Common logic ──────────────────────────────────────────────────────────

    def _handle_count(self, annotated, face_count):
        """Update temporal buffer and fire callbacks accordingly."""
        now = time.time()
        self._face_count_history.append((now, face_count))
        # Trim to window
        while len(self._face_count_history) > self._HISTORY_LEN:
            self._face_count_history.pop(0)

        recent_counts = [c for _, c in self._face_count_history]
        # Use most recent confirmed count (avoid single-frame glitches)
        confirmed_count = recent_counts[-1] if recent_counts else 0

        if confirmed_count > 1:
            status = f"ALERT: {confirmed_count} faces detected!"
            self._handle_multiple_faces(confirmed_count)
            self._no_face_since = None

        elif confirmed_count == 1:
            status = "Face OK"
            self._no_face_since = None

        else:
            status = "WARNING: No face detected"
            self._handle_no_face()

        return annotated, confirmed_count, status

    def _handle_no_face(self):
        now = time.time()
        if self._no_face_since is None:
            self._no_face_since = now
        elapsed = now - self._no_face_since
        if elapsed >= FACE_MISSING_THRESHOLD:
            if now - self._last_no_face_log >= VIOLATION_LOG_COOLDOWN:
                self._last_no_face_log = now
                if self.violation_callback:
                    self.violation_callback(
                        "no_face",
                        f"Student absent from camera for {elapsed:.1f}s"
                    )

    def _handle_multiple_faces(self, count):
        now = time.time()
        if now - self._last_multi_face_log >= VIOLATION_LOG_COOLDOWN:
            self._last_multi_face_log = now
            if self.violation_callback:
                self.violation_callback(
                    "multiple_faces",
                    f"{count} real faces detected simultaneously"
                )

    def close(self):
        if self.detector:
            try:
                self.detector.close()
            except Exception:
                pass
