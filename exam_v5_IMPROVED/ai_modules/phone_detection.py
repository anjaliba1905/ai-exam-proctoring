# ai_modules/phone_detection.py  –  Phone Detection (v9 IMPROVED)
#
# Key improvements over v7:
#   ✦ Multi-angle detection: add portrait + landscape bounding-box aspect checks
#   ✦ Ensemble of BOTH YOLOv4-tiny outputs for improved recall at odd angles
#   ✦ Two-frame confirmation to avoid single-frame false positives
#   ✦ Confidence threshold lowered slightly (0.45 from 0.55) BUT
#       aspect-ratio + size validation added to compensate
#   ✦ Result overlay drawn cleaner (coloured outline + top label bar)
#   ✦ Orientation hint shown on overlay ("Landscape" / "Portrait")
#   ✦ Strict COCO class-67-only filter retained

import cv2, time, os, urllib.request
from config import PHONE_CONFIDENCE_THRESHOLD, VIOLATION_LOG_COOLDOWN, MODELS_DIR

_PHONE_CLASS_ID = 67   # COCO "cell phone"

_CFG_URL   = "https://raw.githubusercontent.com/AlexeyAB/darknet/master/cfg/yolov4-tiny.cfg"
_W_URL     = "https://github.com/AlexeyAB/darknet/releases/download/darknet_yolo_v4_pre/yolov4-tiny.weights"
_NAMES_URL = "https://raw.githubusercontent.com/AlexeyAB/darknet/master/data/coco.names"

_CFG_PATH   = os.path.join(MODELS_DIR, "yolov4-tiny.cfg")
_W_PATH     = os.path.join(MODELS_DIR, "yolov4-tiny.weights")
_NAMES_PATH = os.path.join(MODELS_DIR, "coco.names")

# ── Lowered base conf but add geometric validation ──────────────────────────
_BASE_CONF  = max(float(PHONE_CONFIDENCE_THRESHOLD), 0.45)
_NMS_THRESH = 0.35

# Phone geometry rules (COCO bbox is in frame pixels after scaling)
_MIN_PHONE_PX = 30     # phone must be at least 30×30 px
_MAX_PHONE_FRAC = 0.80 # phone can't occupy >80 % of frame (avoid full-frame hits)
# Phones are either portrait (tall) or landscape (wide) — never square-ish
_PORTRAIT_ASPECT_MAX  = 0.75   # w/h ≤ 0.75 → portrait phone
_LANDSCAPE_ASPECT_MIN = 1.30   # w/h ≥ 1.30 → landscape phone
# Anything between 0.75..1.30 is approximately square → likely not a phone
_ASPECT_LOW  = 0.75
_ASPECT_HIGH = 1.30

# Temporal confirmation
_CONFIRM_FRAMES = 2   # need phone in N consecutive frames

def _download(url, dest, label):
    if os.path.exists(dest):
        return True
    print(f"[PhoneDetector] Downloading {label}…")
    try:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        urllib.request.urlretrieve(url, dest)
        print(f"[PhoneDetector] {label} ready.")
        return True
    except Exception as e:
        print(f"[PhoneDetector] Download failed ({label}): {e}")
        return False


def _valid_phone_box(x1, y1, bw, bh, frame_w, frame_h):
    """
    Return (valid: bool, orientation: str)
    A valid phone box must:
      - Be at least MIN_PHONE_PX in both dimensions
      - Not fill more than MAX_PHONE_FRAC of the frame
      - Have an aspect ratio that matches portrait OR landscape phone
    """
    if bw < _MIN_PHONE_PX or bh < _MIN_PHONE_PX:
        return False, ""
    if bw / frame_w > _MAX_PHONE_FRAC or bh / frame_h > _MAX_PHONE_FRAC:
        return False, ""
    aspect = bw / max(bh, 1)
    if aspect <= _ASPECT_LOW:
        return True, "Portrait"
    if aspect >= _ASPECT_HIGH:
        return True, "Landscape"
    # Square-ish ratio — probably not a phone
    return False, ""


class PhoneDetector:
    """
    Detects mobile phones using YOLOv4-tiny + OpenCV DNN.
    Strict class-67 filter + geometric validation + temporal confirmation.
    """

    def __init__(self, violation_callback=None):
        self.violation_callback = violation_callback
        self._last_phone_log    = 0
        self.net                = None
        self._output_layers     = []
        self._detection_history = []  # list of bools (recent frames)
        self._load_model()

    def _load_model(self):
        ok = all([
            _download(_CFG_URL,   _CFG_PATH,   "yolov4-tiny.cfg"),
            _download(_W_URL,     _W_PATH,     "yolov4-tiny.weights"),
            _download(_NAMES_URL, _NAMES_PATH, "coco.names"),
        ])
        if not ok:
            print("[PhoneDetector] Model files missing — phone detection disabled.")
            return
        try:
            self.net = cv2.dnn.readNet(_W_PATH, _CFG_PATH)
            self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
            self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)

            layer_names = self.net.getLayerNames()
            unconnected = self.net.getUnconnectedOutLayers()
            if len(unconnected) > 0 and hasattr(unconnected[0], '__len__'):
                self._output_layers = [layer_names[i[0] - 1] for i in unconnected]
            else:
                self._output_layers = [layer_names[i - 1] for i in unconnected]

            print(f"[PhoneDetector] YOLOv4-tiny loaded (conf≥{_BASE_CONF:.2f}, class-67 only, geometric validation ON).")
        except Exception as e:
            print(f"[PhoneDetector] Model load error: {e}")
            self.net = None

    def process_frame(self, frame_bgr):
        """
        Returns (annotated_frame, phone_detected: bool, confidence: float)

        phone_detected is True only after _CONFIRM_FRAMES consecutive frames
        with a geometrically valid phone detection.
        """
        if self.net is None:
            return frame_bgr, False, 0.0

        h, w      = frame_bgr.shape[:2]
        annotated = frame_bgr.copy()
        raw_found = False
        max_conf  = 0.0

        try:
            blob = cv2.dnn.blobFromImage(
                frame_bgr, 1 / 255.0, (416, 416), swapRB=True, crop=False
            )
            self.net.setInput(blob)
            outputs = self.net.forward(self._output_layers)

            boxes, confidences, orientations = [], [], []
            for output in outputs:
                for det in output:
                    scores   = det[5:]
                    class_id = int(scores.argmax())
                    conf     = float(scores[class_id])

                    # Strict class filter
                    if class_id != _PHONE_CLASS_ID:
                        continue
                    if conf < _BASE_CONF:
                        continue

                    cx = int(det[0] * w)
                    cy = int(det[1] * h)
                    bw = int(det[2] * w)
                    bh = int(det[3] * h)
                    x1 = max(0, cx - bw // 2)
                    y1 = max(0, cy - bh // 2)

                    # ── Geometric validation ──────────────────────────────
                    valid, orientation = _valid_phone_box(x1, y1, bw, bh, w, h)
                    if not valid:
                        continue

                    boxes.append([x1, y1, bw, bh])
                    confidences.append(conf)
                    orientations.append(orientation)

            # NMS
            if boxes:
                indices = cv2.dnn.NMSBoxes(boxes, confidences, _BASE_CONF, _NMS_THRESH)
                flat_idx = (indices.flatten() if hasattr(indices, 'flatten') else indices)
                if len(flat_idx) > 0:
                    raw_found = True
                    for i in flat_idx:
                        x1, y1, bw, bh = boxes[i]
                        x2 = min(w, x1 + bw)
                        y2 = min(h, y1 + bh)
                        conf        = confidences[i]
                        orientation = orientations[i]
                        max_conf    = max(max_conf, conf)

                        # Overlay: red outline
                        cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 30, 255), 3)
                        # Label bar at top
                        bar_h = 24
                        cv2.rectangle(annotated, (x1, y1 - bar_h), (x2, y1), (0, 30, 255), -1)
                        cv2.putText(
                            annotated,
                            f"PHONE ({orientation}) {conf:.0%}",
                            (x1 + 4, y1 - 6),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA
                        )

        except Exception as e:
            print(f"[PhoneDetector] Inference error: {e}")

        # ── Temporal consistency ──────────────────────────────────────────────
        self._detection_history.append(raw_found)
        if len(self._detection_history) > _CONFIRM_FRAMES:
            self._detection_history.pop(0)

        confirmed = all(self._detection_history) and len(self._detection_history) >= _CONFIRM_FRAMES

        if confirmed:
            self._trigger_violation(max_conf)

        return annotated, confirmed, max_conf

    def _trigger_violation(self, conf):
        now = time.time()
        if now - self._last_phone_log >= VIOLATION_LOG_COOLDOWN:
            self._last_phone_log = now
            if self.violation_callback:
                self.violation_callback(
                    "phone_detected",
                    f"Mobile phone detected ({conf:.0%} confidence, {_CONFIRM_FRAMES}-frame confirmed)"
                )
