# ui/risk_timeline_widget.py - Risk Timeline Graph Widget
# Replaces simple alerts with a live, animated risk curve showing:
#   📈 Rising risk curve (smoothed)
#   🔴 Behavior spikes (violation events)
#   🔮 Prediction points (forecasted risk from PredictiveEngine)
#   💡 Intent markers (from IntentDetector)

import time
from collections import deque
from typing import List, Dict, Optional, Tuple

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy
from PyQt5.QtCore import Qt, QTimer, QPointF, QRectF
from PyQt5.QtGui import (QPainter, QPen, QBrush, QColor, QLinearGradient,
                          QFont, QPainterPath, QPolygonF)


# ─── Data Structures ──────────────────────────────────────────────────────────

class TimelinePoint:
    """A single data point on the risk timeline."""
    __slots__ = ("timestamp", "risk_score", "point_type", "label", "color")

    def __init__(self, timestamp: float, risk_score: float,
                 point_type: str = "normal", label: str = "", color: str = "#58a6ff"):
        self.timestamp  = timestamp
        self.risk_score = risk_score
        self.point_type = point_type   # "normal" | "spike" | "prediction" | "intent"
        self.label      = label
        self.color      = color


# ─── Canvas Widget ────────────────────────────────────────────────────────────

class RiskTimelineCanvas(QWidget):
    """
    Custom-painted risk timeline.
    Renders directly in QPainter — no matplotlib dependency.
    """

    DISPLAY_WINDOW = 120   # seconds of history to show on graph
    SMOOTH_ALPHA   = 0.25  # EMA smoothing factor (0 = very smooth, 1 = raw)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(300, 160)

        # Risk curve: rolling deque of (timestamp, smoothed_score)
        self._curve: deque = deque(maxlen=500)
        # Event markers: list of TimelinePoint (spikes / intents / predictions)
        self._markers: deque = deque(maxlen=200)
        # Prediction horizon points
        self._predictions: deque = deque(maxlen=20)

        self._smoothed_score: float = 0.0
        self._current_risk: float = 0.0
        self._current_level: str = "Low Risk"

        # Colors
        self._bg       = QColor("#0d1117")
        self._grid     = QColor("#21262d")
        self._axis     = QColor("#30363d")
        self._curve_lo = QColor("#3fb950")
        self._curve_md = QColor("#f0883e")
        self._curve_hi = QColor("#f85149")
        self._text     = QColor("#8b949e")
        self._white    = QColor("#e6edf3")

    # ─── Public API ──────────────────────────────────────────────────────

    def push_score(self, risk_score: float):
        """Push current risk score — call every ~1 second."""
        now = time.time()
        # EMA smoothing
        self._smoothed_score = (self.SMOOTH_ALPHA * risk_score +
                                (1 - self.SMOOTH_ALPHA) * self._smoothed_score)
        self._current_risk = risk_score
        self._curve.append((now, self._smoothed_score))
        self.update()

    def push_spike(self, label: str, risk_score: float, color: str = "#f85149"):
        """Mark a violation spike on the timeline."""
        now = time.time()
        self._markers.append(TimelinePoint(
            now, risk_score, point_type="spike", label=label, color=color
        ))
        self.update()

    def push_intent(self, label: str, risk_score: float, color: str = "#f0883e"):
        """Mark a detected intent on the timeline."""
        now = time.time()
        self._markers.append(TimelinePoint(
            now, risk_score, point_type="intent", label=label, color=color
        ))
        self.update()

    def push_prediction(self, label: str, predicted_score: float,
                        seconds_ahead: float = 15, color: str = "#58a6ff"):
        """Add a future prediction point."""
        future_ts = time.time() + seconds_ahead
        self._predictions.append(TimelinePoint(
            future_ts, predicted_score,
            point_type="prediction", label=label, color=color
        ))
        self.update()

    def set_risk_level(self, score: float, level: str):
        self._current_risk = score
        self._current_level = level

    # ─── Painting ────────────────────────────────────────────────────────

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        W, H = self.width(), self.height()
        # Layout margins
        mx, my = 48, 10   # left margin (for Y axis), top margin
        mb = 30            # bottom margin (for X axis)
        mr = 10            # right margin
        gw = W - mx - mr  # graph width
        gh = H - my - mb  # graph height

        now = time.time()
        t_start = now - self.DISPLAY_WINDOW
        t_end   = now + 20  # small lookahead for prediction markers

        def tx(ts: float) -> float:
            """Map timestamp to X pixel."""
            return mx + (ts - t_start) / (t_end - t_start) * gw

        def ty(score: float) -> float:
            """Map 0-100 risk score to Y pixel (inverted — 100 is top)."""
            return my + (1.0 - score / 100.0) * gh

        # ── Background ───────────────────────────────────────────────────
        painter.fillRect(0, 0, W, H, self._bg)

        # ── Grid lines ───────────────────────────────────────────────────
        painter.setPen(QPen(self._grid, 1, Qt.DashLine))
        for risk_level in [25, 50, 75, 100]:
            y = ty(risk_level)
            painter.drawLine(int(mx), int(y), int(mx + gw), int(y))

        # ── Risk zone shading ─────────────────────────────────────────────
        # Green zone (0-30)
        r_green = QRectF(mx, ty(30), gw, ty(0) - ty(30))
        painter.fillRect(r_green, QColor(63, 185, 80, 18))
        # Orange zone (30-60)
        r_orange = QRectF(mx, ty(60), gw, ty(30) - ty(60))
        painter.fillRect(r_orange, QColor(240, 136, 62, 18))
        # Red zone (60-100)
        r_red = QRectF(mx, ty(100), gw, ty(60) - ty(100))
        painter.fillRect(r_red, QColor(248, 81, 73, 18))

        # ── Y Axis labels ────────────────────────────────────────────────
        font_small = QFont("Segoe UI", 7)
        painter.setFont(font_small)
        for risk_level, label in [(0, "0"), (25, "25"), (50, "50"),
                                   (75, "75"), (100, "100")]:
            y = ty(risk_level)
            painter.setPen(self._text)
            painter.drawText(QRectF(0, y - 8, mx - 4, 16),
                             Qt.AlignRight | Qt.AlignVCenter, label)

        # ── X Axis ───────────────────────────────────────────────────────
        painter.setPen(QPen(self._axis, 1))
        painter.drawLine(int(mx), int(my + gh), int(mx + gw), int(my + gh))
        painter.drawLine(int(mx), int(my), int(mx), int(my + gh))

        # X axis time labels
        for offset in [0, 30, 60, 90, 120]:
            ts = t_start + offset
            if ts > t_end:
                break
            x = tx(ts)
            secs_ago = int(now - ts)
            lbl = f"-{secs_ago}s" if secs_ago > 0 else "now"
            painter.setPen(self._text)
            painter.drawText(QRectF(x - 20, H - mb + 4, 40, 16),
                             Qt.AlignCenter, lbl)

        # ── Risk Curve (filled gradient) ─────────────────────────────────
        # Prune old points
        while self._curve and self._curve[0][0] < t_start - 5:
            self._curve.popleft()

        curve_pts = [(ts, s) for ts, s in self._curve if t_start <= ts <= now]
        if len(curve_pts) >= 2:
            # Build path for filled area
            path = QPainterPath()
            path.moveTo(tx(curve_pts[0][0]), ty(0))
            for ts, s in curve_pts:
                path.lineTo(tx(ts), ty(s))
            path.lineTo(tx(curve_pts[-1][0]), ty(0))
            path.closeSubpath()

            # Gradient fill
            grad = QLinearGradient(0, my, 0, my + gh)
            grad.setColorAt(0.0, QColor(248, 81, 73, 80))
            grad.setColorAt(0.4, QColor(240, 136, 62, 60))
            grad.setColorAt(1.0, QColor(63, 185, 80, 20))
            painter.fillPath(path, QBrush(grad))

            # Curve stroke — color based on current risk
            cur_score = curve_pts[-1][1] if curve_pts else 0
            if cur_score > 60:
                stroke_color = self._curve_hi
            elif cur_score > 30:
                stroke_color = self._curve_md
            else:
                stroke_color = self._curve_lo

            pen = QPen(stroke_color, 2)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            stroke_path = QPainterPath()
            stroke_path.moveTo(tx(curve_pts[0][0]), ty(curve_pts[0][1]))
            for ts, s in curve_pts[1:]:
                stroke_path.lineTo(tx(ts), ty(s))
            painter.drawPath(stroke_path)

        # ── Prediction dotted line ────────────────────────────────────────
        now_x = tx(now)
        last_score = curve_pts[-1][1] if curve_pts else self._smoothed_score

        # Prune expired predictions
        while self._predictions and self._predictions[0].timestamp < now - 5:
            self._predictions.popleft()

        for pred in self._predictions:
            if pred.timestamp < now:
                continue
            pred_x = tx(pred.timestamp)
            pred_y = ty(pred.risk_score)

            pen = QPen(QColor(pred.color), 1, Qt.DashLine)
            painter.setPen(pen)
            painter.drawLine(int(now_x), int(ty(last_score)),
                             int(pred_x), int(pred_y))

            # Prediction diamond marker
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(pred.color)))
            diamond = QPolygonF([
                QPointF(pred_x,     pred_y - 7),
                QPointF(pred_x + 5, pred_y),
                QPointF(pred_x,     pred_y + 7),
                QPointF(pred_x - 5, pred_y),
            ])
            painter.drawPolygon(diamond)

            # Prediction label
            painter.setPen(QColor(pred.color))
            font_pred = QFont("Segoe UI", 7)
            painter.setFont(font_pred)
            painter.drawText(QRectF(pred_x - 50, pred_y - 22, 100, 14),
                             Qt.AlignCenter, f"⟡ {pred.label[:16]}")

        # ── Spike / Intent Markers ────────────────────────────────────────
        # Prune old markers
        while self._markers and self._markers[0].timestamp < t_start - 2:
            self._markers.popleft()

        # Deduplicate overlapping labels (group within 3s)
        rendered_labels: List[Tuple[float, str]] = []
        for marker in self._markers:
            if marker.timestamp < t_start:
                continue
            x = tx(marker.timestamp)
            y = ty(marker.risk_score)
            color = QColor(marker.color)

            if marker.point_type == "spike":
                # Vertical spike line
                painter.setPen(QPen(color, 1, Qt.DotLine))
                painter.drawLine(int(x), int(ty(0)), int(x), int(my))
                # Circle dot at score level
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(color))
                painter.drawEllipse(QPointF(x, y), 5, 5)
                # Tiny label (suppress if too close to recent one)
                too_close = any(abs(x - rx) < 30 and rl == marker.label
                                for rx, rl in rendered_labels)
                if not too_close:
                    painter.setPen(color)
                    painter.setFont(QFont("Segoe UI", 7))
                    painter.drawText(QRectF(x - 30, my + 2, 60, 12),
                                     Qt.AlignCenter, marker.label[:14])
                    rendered_labels.append((x, marker.label))

            elif marker.point_type == "intent":
                # Intent triangle
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(color))
                tri = QPolygonF([
                    QPointF(x,     y - 8),
                    QPointF(x + 6, y + 4),
                    QPointF(x - 6, y + 4),
                ])
                painter.drawPolygon(tri)

        # ── "Now" vertical line ───────────────────────────────────────────
        painter.setPen(QPen(QColor("#58a6ff"), 1, Qt.SolidLine))
        painter.drawLine(int(now_x), int(my), int(now_x), int(my + gh))
        painter.setPen(QColor("#58a6ff"))
        painter.setFont(QFont("Segoe UI", 7, QFont.Bold))
        painter.drawText(int(now_x) - 12, int(my) - 2, "NOW")

        # ── Current risk readout ──────────────────────────────────────────
        if self._current_risk > 60:
            readout_color = self._curve_hi
        elif self._current_risk > 30:
            readout_color = self._curve_md
        else:
            readout_color = self._curve_lo

        painter.setFont(QFont("Segoe UI", 10, QFont.Bold))
        painter.setPen(readout_color)
        painter.drawText(QRectF(mx + 4, my + 2, 120, 20), Qt.AlignLeft,
                         f"Risk: {self._current_risk:.0f}/100")

        painter.setFont(QFont("Segoe UI", 8))
        painter.setPen(readout_color)
        painter.drawText(QRectF(mx + 4, my + 18, 120, 16), Qt.AlignLeft,
                         self._current_level)

        painter.end()


# ─── Full Timeline Widget ─────────────────────────────────────────────────────

class RiskTimelineWidget(QWidget):
    """
    Complete risk timeline panel with header, canvas, and legend.
    Drop this into any QVBoxLayout/QHBoxLayout.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:#0d1117;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Header
        header = QLabel("📈  Risk Timeline")
        header.setStyleSheet("color:#e6edf3; font-size:12px; font-weight:bold; padding:4px 0;")
        layout.addWidget(header)

        # Canvas
        self.canvas = RiskTimelineCanvas()
        layout.addWidget(self.canvas)

        # Legend row
        legend = QHBoxLayout()
        legend.setSpacing(12)
        for color, label in [("#3fb950", "Low"),
                              ("#f0883e", "Medium"),
                              ("#f85149", "High"),
                              ("#58a6ff", "Prediction")]:
            dot = QLabel(f"● {label}")
            dot.setStyleSheet(f"color:{color}; font-size:9px;")
            legend.addWidget(dot)
        legend.addStretch()
        layout.addLayout(legend)

        # Auto-update timer: push score every second
        self._auto_score: float = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._auto_push)
        self._timer.start(1000)

    # ─── Public API ──────────────────────────────────────────────────────

    def update_risk(self, score: float, level: str):
        """Call every second with current risk score + level."""
        self._auto_score = score
        self.canvas.set_risk_level(score, level)

    def record_spike(self, violation_type: str, current_score: float):
        """Call when a violation fires — creates a spike marker."""
        label_map = {
            "phone_detected":  "📱Phone",
            "multiple_faces":  "👥Multi",
            "no_face":         "❌NoFace",
            "gaze_away":       "👁Gaze",
            "tab_switch":      "🖥Tab",
            "audio_alert":     "🔊Audio",
        }
        label = label_map.get(violation_type, violation_type[:8])
        self.canvas.push_spike(label, current_score)

    def record_intent(self, intent_label: str, current_score: float,
                      color: str = "#f0883e"):
        """Call when intent engine flags a pattern."""
        self.canvas.push_intent(intent_label[:14], current_score, color)

    def record_prediction(self, prediction_label: str, predicted_score: float,
                          seconds_ahead: float = 15, color: str = "#58a6ff"):
        """Call when predictive engine forecasts a future risk."""
        self.canvas.push_prediction(prediction_label[:14], predicted_score,
                                    seconds_ahead, color)

    def _auto_push(self):
        self.canvas.push_score(self._auto_score)

    def stop(self):
        self._timer.stop()
