# ai_modules/phone_detection.py
# Phone detection using YOLOv4-tiny via OpenCV DNN (pure C++ — no PyTorch).
# FIX v3:
#   • ONLY detects "cell phone" (COCO class 67) — no other object is flagged.
#   • Higher confidence threshold (0.55) to eliminate false positives.
#   • NMS (Non-Maximum Suppression) applied to avoid duplicate boxes.
#   • Bottles, books, laptops, tablets etc. are explicitly ignored even if
#     YOLO misclassifies them, by filtering on class_id strictly == 67.

import cv2, time, os, urllib.request
from config import PHONE_CONFIDENCE_THRESHOLD, VIOLATION_LOG_COOLDOWN, MODELS_DIR

# COCO class index for "cell phone" in the 80-class model = 67 (0-based)
_PHONE_CLASS_ID = 67

# YOLOv4-tiny model files (OpenCV DNN — no PyTorch)
_CFG_URL     = "https://raw.githubusercontent.com/AlexeyAB/darknet/master/cfg/yolov4-tiny.cfg"
_W_URL       = "https://github.com/AlexeyAB/darknet/releases/download/darknet_yolo_v4_pre/yolov4-tiny.weights"
_NAMES_URL   = "https://raw.githubusercontent.com/AlexeyAB/darknet/master/data/coco.names"

_CFG_PATH    = os.path.join(MODELS_DIR, "yolov4-tiny.cfg")
_W_PATH      = os.path.join(MODELS_DIR, "yolov4-tiny.weights")
_NAMES_PATH  = os.path.join(MODELS_DIR, "coco.names")

# Minimum confidence to even consider a detection
_MIN_CONF    = max(PHONE_CONFIDENCE_THRESHOLD, 0.55)

# NMS threshold
_NMS_THRESH  = 0.4

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


class PhoneDetector:
    """
    Detects ONLY mobile/cell phones using YOLOv4-tiny + OpenCV DNN.
    No PyTorch dependency.  Strict class-id filter — no other object triggers.
    """

    def __init__(self, violation_callback=None):
        self.violation_callback = violation_callback
        self._last_phone_log    = 0
        self.net                = None
        self._output_layers     = []
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
            # Handle both old (list-of-lists) and new (flat) OpenCV returns
            if len(unconnected) > 0 and hasattr(unconnected[0], '__len__'):
                self._output_layers = [layer_names[i[0] - 1] for i in unconnected]
            else:
                self._output_layers = [layer_names[i - 1] for i in unconnected]

            print("[PhoneDetector] YOLOv4-tiny loaded — only 'cell phone' (class 67) triggers.")
        except Exception as e:
            print(f"[PhoneDetector] Model load error: {e}")
            self.net = None

    def process_frame(self, frame_bgr):
        """
        Returns (annotated_frame, phone_detected: bool, confidence: float)
        ONLY triggers for COCO class 67 (cell phone), nothing else.
        """
        if self.net is None:
            return frame_bgr, False, 0.0

        h, w = frame_bgr.shape[:2]
        annotated   = frame_bgr.copy()
        phone_found = False
        max_conf    = 0.0

        try:
            blob = cv2.dnn.blobFromImage(
                frame_bgr, 1 / 255.0, (416, 416), swapRB=True, crop=False
            )
            self.net.setInput(blob)
            outputs = self.net.forward(self._output_layers)

            # Collect phone boxes for NMS
            boxes, confidences = [], []
            for output in outputs:
                for det in output:
                    scores   = det[5:]
                    class_id = int(scores.argmax())
                    conf     = float(scores[class_id])

                    # ── STRICT FILTER: only cell phone ──────────────────────
                    if class_id != _PHONE_CLASS_ID:
                        continue
                    if conf < _MIN_CONF:
                        continue

                    cx = int(det[0] * w)
                    cy = int(det[1] * h)
                    bw = int(det[2] * w)
                    bh = int(det[3] * h)
                    x1 = max(0, cx - bw // 2)
                    y1 = max(0, cy - bh // 2)
                    boxes.append([x1, y1, bw, bh])
                    confidences.append(conf)

            # Apply NMS to remove duplicates
            if boxes:
                indices = cv2.dnn.NMSBoxes(boxes, confidences, _MIN_CONF, _NMS_THRESH)
                if len(indices) > 0:
                    phone_found = True
                    for i in (indices.flatten() if hasattr(indices, 'flatten') else indices):
                        x1, y1, bw, bh = boxes[i]
                        x2 = min(w, x1 + bw)
                        y2 = min(h, y1 + bh)
                        conf = confidences[i]
                        max_conf = max(max_conf, conf)
                        cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 0, 255), 3)
                        cv2.putText(
                            annotated, f"PHONE {conf:.0%}",
                            (x1, max(0, y1 - 10)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2
                        )

        except Exception as e:
            print(f"[PhoneDetector] Inference error: {e}")

        if phone_found:
            self._trigger_violation(max_conf)

        return annotated, phone_found, max_conf

    def _trigger_violation(self, conf):
        now = time.time()
        if now - self._last_phone_log >= VIOLATION_LOG_COOLDOWN:
            self._last_phone_log = now
            if self.violation_callback:
                self.violation_callback(
                    "phone_detected",
                    f"Mobile phone detected ({conf:.0%} confidence)"
                )
