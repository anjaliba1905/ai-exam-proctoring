# ai_modules/eye_tracking.py - Gaze direction via MediaPipe Face Mesh
# Fixed for mediapipe >= 0.10 on Windows

import cv2
import numpy as np
import time

# ── MediaPipe safe import ─────────────────────────────────────────────────────
try:
    from mediapipe.python.solutions import face_mesh as mp_face_mesh
    from mediapipe.python.solutions import drawing_utils as mp_drawing
    from mediapipe.python.solutions import drawing_styles as mp_drawing_styles
    MEDIAPIPE_OK = True
except Exception as e:
    print(f"[EyeTracker] MediaPipe import warning: {e}")
    MEDIAPIPE_OK = False

from config import (EYE_GAZE_AWAY_THRESHOLD, GAZE_LEFT_THRESHOLD,
                    GAZE_RIGHT_THRESHOLD, GAZE_UP_THRESHOLD, VIOLATION_LOG_COOLDOWN)


class EyeTracker:
    """
    Uses MediaPipe Face Mesh to estimate gaze direction.
    Flags violation if student looks away for > EYE_GAZE_AWAY_THRESHOLD seconds.
    Gracefully disabled if MediaPipe not available.
    """

    LEFT_IRIS  = [474, 475, 476, 477]
    RIGHT_IRIS = [469, 470, 471, 472]
    LEFT_EYE   = [362, 382, 381, 380, 374, 373, 390, 249,
                  263, 466, 388, 387, 386, 385, 384, 398]
    RIGHT_EYE  = [33,  7,   163, 144, 145, 153, 154, 155,
                  133, 173, 157, 158, 159, 160, 161, 246]

    def __init__(self, violation_callback=None):
        self.violation_callback = violation_callback
        self._looking_away_since = None
        self._last_violation_log = 0
        self.mesh = None
        self._enabled = False

        if MEDIAPIPE_OK:
            try:
                self.mesh = mp_face_mesh.FaceMesh(
                    max_num_faces=1,
                    refine_landmarks=True,
                    min_detection_confidence=0.5,
                    min_tracking_confidence=0.5
                )
                self._enabled = True
                print("[EyeTracker] MediaPipe FaceMesh loaded OK.")
            except Exception as e:
                print(f"[EyeTracker] FaceMesh init failed: {e}. Eye tracking disabled.")
        else:
            print("[EyeTracker] MediaPipe unavailable. Eye tracking disabled.")

    def process_frame(self, frame_bgr):
        """
        Returns (annotated_frame, gaze_direction_str, looking_away_bool)
        If disabled, returns frame unchanged with neutral status.
        """
        if not self._enabled or self.mesh is None:
            return frame_bgr, "Gaze: N/A", False

        h, w = frame_bgr.shape[:2]
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False

        try:
            result = self.mesh.process(rgb)
        except Exception as e:
            print(f"[EyeTracker] process error: {e}")
            return frame_bgr, "Gaze: Error", False

        annotated = frame_bgr.copy()
        gaze_str = "Gaze: Center"
        looking_away = False

        if not result.multi_face_landmarks:
            return annotated, "Gaze: No Face", False

        lms = result.multi_face_landmarks[0].landmark

        try:
            lx, ly = self._iris_position(lms, self.LEFT_EYE,  self.LEFT_IRIS,  w, h)
            rx, ry = self._iris_position(lms, self.RIGHT_EYE, self.RIGHT_IRIS, w, h)
            avg_x = (lx + rx) / 2
            avg_y = (ly + ry) / 2

            if avg_x < GAZE_LEFT_THRESHOLD:
                gaze_str = "Gaze: LEFT"
                looking_away = True
            elif avg_x > GAZE_RIGHT_THRESHOLD:
                gaze_str = "Gaze: RIGHT"
                looking_away = True
            elif avg_y < GAZE_UP_THRESHOLD:
                gaze_str = "Gaze: UP"
                looking_away = True
            else:
                gaze_str = "Gaze: Center"
                looking_away = False
        except Exception as e:
            print(f"[EyeTracker] gaze calc error: {e}")
            return annotated, "Gaze: Error", False

        # Draw iris landmarks
        try:
            for idx in self.LEFT_IRIS + self.RIGHT_IRIS:
                lm = lms[idx]
                cx, cy = int(lm.x * w), int(lm.y * h)
                cv2.circle(annotated, (cx, cy), 2, (0, 255, 255), -1)
        except Exception:
            pass

        color = (0, 0, 255) if looking_away else (0, 255, 0)
        cv2.putText(annotated, gaze_str, (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2)

        self._check_gaze_violation(looking_away, gaze_str)
        return annotated, gaze_str, looking_away

    def _iris_position(self, landmarks, eye_indices, iris_indices, w, h):
        eye_pts  = np.array([(landmarks[i].x * w, landmarks[i].y * h)
                              for i in eye_indices])
        iris_pts = np.array([(landmarks[i].x * w, landmarks[i].y * h)
                              for i in iris_indices])
        eye_min = eye_pts.min(axis=0)
        eye_max = eye_pts.max(axis=0)
        eye_dim = eye_max - eye_min
        if eye_dim[0] < 1e-6 or eye_dim[1] < 1e-6:
            return 0.0, 0.0
        iris_center = iris_pts.mean(axis=0)
        norm_x = ((iris_center[0] - eye_min[0]) / eye_dim[0]) * 2 - 1
        norm_y = ((iris_center[1] - eye_min[1]) / eye_dim[1]) * 2 - 1
        return norm_x, norm_y

    def _check_gaze_violation(self, looking_away, direction):
        now = time.time()
        if looking_away:
            if self._looking_away_since is None:
                self._looking_away_since = now
            elapsed = now - self._looking_away_since
            if elapsed >= EYE_GAZE_AWAY_THRESHOLD:
                if now - self._last_violation_log >= VIOLATION_LOG_COOLDOWN:
                    self._last_violation_log = now
                    if self.violation_callback:
                        self.violation_callback(
                            "gaze_away",
                            f"Student looking {direction} for {elapsed:.1f}s"
                        )
        else:
            self._looking_away_since = None

    def close(self):
        if self.mesh:
            try:
                self.mesh.close()
            except Exception:
                pass
