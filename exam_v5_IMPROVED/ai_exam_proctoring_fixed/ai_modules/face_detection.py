# ai_modules/face_detection.py - Face detection via OpenCV + MediaPipe
# Fixed for mediapipe >= 0.10 on Windows (explicit solution import)

import cv2
import time

# ── MediaPipe safe import (works on all versions) ─────────────────────────────
try:
    from mediapipe.python.solutions import face_detection as mp_face_detection
    from mediapipe.python.solutions import drawing_utils as mp_drawing
    MEDIAPIPE_OK = True
except Exception as e:
    print(f"[FaceDetector] MediaPipe import warning: {e}")
    MEDIAPIPE_OK = False

from config import FACE_MISSING_THRESHOLD, VIOLATION_LOG_COOLDOWN


class FaceDetector:
    """
    Uses MediaPipe Face Detection to:
      - Detect if no face is visible
      - Detect multiple faces simultaneously
    Falls back to OpenCV Haar cascade if MediaPipe unavailable.
    """

    def __init__(self, violation_callback=None):
        self.violation_callback = violation_callback
        self._no_face_since = None
        self._last_no_face_log = 0
        self._last_multi_face_log = 0
        self.detector = None
        self._use_fallback = False

        if MEDIAPIPE_OK:
            try:
                self.detector = mp_face_detection.FaceDetection(
                    model_selection=0,
                    min_detection_confidence=0.6
                )
                print("[FaceDetector] MediaPipe FaceDetection loaded OK.")
            except Exception as e:
                print(f"[FaceDetector] MediaPipe init failed: {e}, using fallback.")
                self._use_fallback = True
        else:
            self._use_fallback = True

        # OpenCV Haar fallback
        if self._use_fallback:
            self._haar = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            )
            print("[FaceDetector] Using OpenCV Haar cascade fallback.")

    def process_frame(self, frame_bgr):
        """
        Analyse a single BGR frame.
        Returns (annotated_frame, face_count, status_text)
        """
        if self._use_fallback:
            return self._process_haar(frame_bgr)
        return self._process_mediapipe(frame_bgr)

    def _process_mediapipe(self, frame_bgr):
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        try:
            result = self.detector.process(rgb)
        except Exception as e:
            print(f"[FaceDetector] process error: {e}")
            return frame_bgr, 0, "Face: Error"

        annotated = frame_bgr.copy()
        face_count = 0
        status = "Face OK"

        if result.detections:
            face_count = len(result.detections)
            for det in result.detections:
                bbox = det.location_data.relative_bounding_box
                h, w = frame_bgr.shape[:2]
                x1 = max(0, int(bbox.xmin * w))
                y1 = max(0, int(bbox.ymin * h))
                x2 = min(w, int((bbox.xmin + bbox.width) * w))
                y2 = min(h, int((bbox.ymin + bbox.height) * h))
                color = (0, 255, 0) if face_count == 1 else (0, 0, 255)
                cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)

            if face_count > 1:
                status = "ALERT: Multiple Faces!"
                self._handle_multiple_faces(face_count)
                self._no_face_since = None
            else:
                status = "Face Detected OK"
                self._no_face_since = None
        else:
            status = "WARNING: No Face"
            self._handle_no_face()

        return annotated, face_count, status

    def _process_haar(self, frame_bgr):
        """OpenCV Haar cascade fallback."""
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        faces = self._haar.detectMultiScale(gray, scaleFactor=1.1,
                                             minNeighbors=5, minSize=(60, 60))
        annotated = frame_bgr.copy()
        face_count = len(faces)

        for (x, y, w, h) in faces:
            color = (0, 255, 0) if face_count == 1 else (0, 0, 255)
            cv2.rectangle(annotated, (x, y), (x+w, y+h), color, 2)

        if face_count > 1:
            status = "ALERT: Multiple Faces!"
            self._handle_multiple_faces(face_count)
            self._no_face_since = None
        elif face_count == 1:
            status = "Face Detected OK"
            self._no_face_since = None
        else:
            status = "WARNING: No Face"
            self._handle_no_face()

        return annotated, face_count, status

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
                    f"{count} faces detected simultaneously"
                )

    def close(self):
        if self.detector:
            try:
                self.detector.close()
            except Exception:
                pass
