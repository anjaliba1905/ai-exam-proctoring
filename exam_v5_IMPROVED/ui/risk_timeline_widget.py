# ui/risk_timeline_widget.py  –  Risk Timeline (v9 REDESIGNED)
# Improvements:
#   ✦ Larger minimum size — no cramped rendering
#   ✦ Readable axis labels (never overlapping)
#   ✦ Risk zone colour bands with clear boundary labels
#   ✦ Smoothed curve with per-segment colour (green/orange/red by value)
#   ✦ Spike markers shown as clean circles + tooltip text
#   ✦ Grid lines at 25/50/75 with dashed style
#   ✦ Legend inside canvas (bottom-left)
#   ✦ Current score large display in top-right
#   ✦ No text rendered if insufficient width

import time
from collections import deque
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QSizePolicy
from PyQt5.QtCore    import Qt, QRectF, QPointF
from PyQt5.QtGui     import (QPainter, QPen, QBrush, QColor, QFont,
                              QPainterPath, QLinearGradient)


class RiskTimelineCanvas(QWidget):
    DISPLAY_WINDOW = 120   # seconds shown
    SMOOTH_ALPHA   = 0.20  # EMA factor

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(320, 200)   # ← increased from 160

        self._curve       = deque(maxlen=600)
        self._markers     = deque(maxlen=100)
        self._predictions = deque(maxlen=20)
        self._smoothed    = 0.0
        self._current     = 0.0
        self._level       = "Low Risk"

    # ── Public API ────────────────────────────────────────────────────────────

    def push_score(self, risk_score: float):
        now = time.time()
        self._smoothed = self.SMOOTH_ALPHA * risk_score + (1 - self.SMOOTH_ALPHA) * self._smoothed
        self._current  = risk_score
        self._curve.append((now, self._smoothed))
        self.update()

    def push_spike(self, label: str, risk_score: float, color: str = "#ef4444"):
        self._markers.append((time.time(), risk_score, label, color, "spike"))
        self.update()

    def push_intent(self, label: str, risk_score: float, color: str = "#f59e0b"):
        self._markers.append((time.time(), risk_score, label, color, "intent"))
        self.update()

    def push_prediction(self, label: str, predicted_score: float,
                        seconds_ahead: float = 15, color: str = "#3b82f6"):
        self._predictions.append((time.time() + seconds_ahead, predicted_score, label, color))
        self.update()

    def set_risk_level(self, score: float, level: str):
        self._current = score
        self._level   = level

    # ── Colours ──────────────────────────────────────────────────────────────

    @staticmethod
    def _risk_color(score: float) -> QColor:
        if score < 30:
            return QColor("#22c55e")
        elif score < 60:
            return QColor("#f59e0b")
        return QColor("#ef4444")

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        W, H  = self.width(), self.height()
        # Layout margins — enough for axis labels
        ml, mt, mb, mr = 50, 12, 36, 16
        gw = W - ml - mr
        gh = H - mt - mb
        now     = time.time()
        t_start = now - self.DISPLAY_WINDOW
        t_end   = now + 15  # small lookahead for predictions

        def tx(ts):
            return ml + (ts - t_start) / (t_end - t_start) * gw

        def ty(score):
            clamped = max(0.0, min(100.0, score))
            return mt + (1.0 - clamped / 100.0) * gh

        # Background
        painter.fillRect(0, 0, W, H, QColor("#10151e"))

        # Risk zone fills — subtle
        zones = [
            (0,  30, QColor(34, 197, 94,   16)),   # green
            (30, 60, QColor(245, 158, 11, 16)),  # amber
            (60, 100, QColor(239, 68, 68,  20)),   # red
        ]
        for lo, hi, col in zones:
            y_top = ty(hi)
            y_bot = ty(lo)
            painter.fillRect(QRectF(ml, y_top, gw, y_bot - y_top), col)

        # Grid lines at 25, 50, 75
        grid_pen = QPen(QColor("#252f44"), 1, Qt.DashLine)
        grid_pen.setDashPattern([4, 6])
        painter.setPen(grid_pen)
        for lvl in [25, 50, 75]:
            y = ty(lvl)
            painter.drawLine(int(ml), int(y), int(ml + gw), int(y))

        # Zone boundary labels  (right side, inside)
        font_xs = QFont("Segoe UI", 8)
        painter.setFont(font_xs)
        for score, label, color in [(30, "Low", "#22c55e"), (60, "Med", "#f59e0b"), (100, "High", "#ef4444")]:
            y = ty(score)
            painter.setPen(QColor(color))
            painter.drawText(QRectF(ml + gw - 28, y - 9, 28, 14), Qt.AlignRight | Qt.AlignVCenter, label)

        # Y-axis
        axis_pen = QPen(QColor("#252f44"), 1)
        painter.setPen(axis_pen)
        painter.drawLine(int(ml), int(mt), int(ml), int(mt + gh))

        # Y-axis labels (0, 25, 50, 75, 100)
        font_s = QFont("Segoe UI", 9)
        painter.setFont(font_s)
        for lvl in [0, 25, 50, 75, 100]:
            y = ty(lvl)
            painter.setPen(QColor("#4a5568"))
            r = QRectF(0, y - 8, ml - 6, 16)
            painter.drawText(r, Qt.AlignRight | Qt.AlignVCenter, str(lvl))

        # X-axis
        painter.setPen(QPen(QColor("#252f44"), 1))
        painter.drawLine(int(ml), int(mt + gh), int(ml + gw), int(mt + gh))

        # X-axis labels — spaced at 30s intervals, no overlap
        label_positions = []
        for offset in range(0, self.DISPLAY_WINDOW + 1, 30):
            ts  = t_start + offset
            if ts > now + 5:
                break
            x   = tx(ts)
            secs_ago = int(now - ts)
            lbl = "now" if secs_ago <= 2 else f"-{secs_ago}s"
            # Check horizontal overlap before drawing
            too_close = any(abs(x - px) < 38 for px in label_positions)
            if not too_close:
                label_positions.append(x)
                painter.setPen(QColor("#4a5568"))
                painter.setFont(font_s)
                painter.drawText(QRectF(x - 18, mt + gh + 6, 36, 18), Qt.AlignCenter, lbl)
                # Tick mark
                painter.setPen(QPen(QColor("#252f44"), 1))
                painter.drawLine(int(x), int(mt + gh), int(x), int(mt + gh + 4))

        # ── Risk curve ────────────────────────────────────────────────────────
        # Prune stale points
        while self._curve and self._curve[0][0] < t_start - 5:
            self._curve.popleft()

        pts = [(ts, s) for ts, s in self._curve if t_start <= ts <= now]

        if len(pts) >= 2:
            # Draw coloured segments (colour changes based on risk value)
            seg_pen = QPen()
            seg_pen.setWidth(2)
            seg_pen.setCapStyle(Qt.RoundCap)
            seg_pen.setJoinStyle(Qt.RoundJoin)
            for j in range(1, len(pts)):
                x1, y1 = tx(pts[j-1][0]), ty(pts[j-1][1])
                x2, y2 = tx(pts[j][0]),   ty(pts[j][1])
                mid_score = (pts[j-1][1] + pts[j][1]) / 2
                seg_pen.setColor(self._risk_color(mid_score))
                painter.setPen(seg_pen)
                painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

            # Filled area under curve (subtle)
            fill_path = QPainterPath()
            fill_path.moveTo(tx(pts[0][0]), ty(0))
            for ts, s in pts:
                fill_path.lineTo(tx(ts), ty(s))
            fill_path.lineTo(tx(pts[-1][0]), ty(0))
            fill_path.closeSubpath()
            last_score = pts[-1][1]
            fill_color = self._risk_color(last_score)
            fill_color.setAlpha(18)
            painter.fillPath(fill_path, QBrush(fill_color))

            # Current score endpoint dot
            ex, ey = tx(pts[-1][0]), ty(pts[-1][1])
            dot_color = self._risk_color(pts[-1][1])
            painter.setPen(QPen(dot_color, 2))
            painter.setBrush(QBrush(dot_color))
            painter.drawEllipse(QPointF(ex, ey), 4, 4)

        # ── Spike/intent markers ──────────────────────────────────────────────
        for (ts, score, label, color, mtype) in self._markers:
            if not (t_start <= ts <= now):
                continue
            x, y = tx(ts), ty(score)
            c = QColor(color)

            if mtype == "spike":
                # Diamond shape
                painter.setPen(QPen(c, 1))
                painter.setBrush(QBrush(c))
                path = QPainterPath()
                path.moveTo(x, y - 7)
                path.lineTo(x + 5, y)
                path.lineTo(x, y + 7)
                path.lineTo(x - 5, y)
                path.closeSubpath()
                painter.drawPath(path)
            else:
                # Circle
                painter.setPen(QPen(c, 1.5))
                painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(QPointF(x, y), 5, 5)

            # Label — only if enough horizontal space
            if x + 60 < W - mr:
                c.setAlpha(200)
                painter.setPen(c)
                painter.setFont(QFont("Segoe UI", 8))
                painter.drawText(QRectF(x + 8, y - 8, 80, 16), Qt.AlignLeft | Qt.AlignVCenter, label[:14])

        # ── Predictions ───────────────────────────────────────────────────────
        for (ts, score, label, color) in self._predictions:
            if not (now <= ts <= t_end):
                continue
            x, y = tx(ts), ty(score)
            c = QColor(color)
            pen = QPen(c, 1.5, Qt.DotLine)
            painter.setPen(pen)
            if pts:
                painter.drawLine(QPointF(tx(pts[-1][0]), ty(pts[-1][1])), QPointF(x, y))
            painter.setPen(QPen(c, 1.5))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QPointF(x, y), 5, 5)

        # ── Current score display (top right corner) ──────────────────────────
        if self._current > 0:
            score_str  = f"{self._current:.0f}"
            score_col  = self._risk_color(self._current)
            font_big   = QFont("Segoe UI", 20, QFont.Bold)
            painter.setFont(font_big)
            painter.setPen(score_col)
            painter.drawText(QRectF(W - mr - 55, mt, 55, 32), Qt.AlignRight | Qt.AlignTop, score_str)

            font_sm = QFont("Segoe UI", 9)
            painter.setFont(font_sm)
            score_col.setAlpha(180)
            painter.setPen(score_col)
            painter.drawText(QRectF(W - mr - 60, mt + 28, 60, 14), Qt.AlignRight | Qt.AlignTop, "risk")

        # ── Legend (bottom left, inside graph) ───────────────────────────────
        lx, ly = ml + 8, mt + gh - 22
        if gw > 200:
            font_leg = QFont("Segoe UI", 8)
            painter.setFont(font_leg)
            for i, (legend_txt, legend_col) in enumerate([
                ("● Low", "#22c55e"), ("● Med", "#f59e0b"), ("● High", "#ef4444"),
                ("◆ Event", "#ef4444"), ("○ Intent", "#f59e0b"),
            ]):
                c = QColor(legend_col)
                painter.setPen(c)
                painter.drawText(QRectF(lx + i * 56, ly, 52, 14), Qt.AlignLeft | Qt.AlignVCenter, legend_txt)

        painter.end()


class RiskTimelineWidget(QWidget):
    """Container widget — canvas + optional title label."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self._canvas = RiskTimelineCanvas(self)
        lay.addWidget(self._canvas, stretch=1)

    def push_score(self, s):       self._canvas.push_score(s)
    def push_spike(self, *a, **k): self._canvas.push_spike(*a, **k)
    def push_intent(self, *a, **k):self._canvas.push_intent(*a, **k)
    def push_prediction(self, *a, **k): self._canvas.push_prediction(*a, **k)
    def set_risk_level(self, s, l):self._canvas.set_risk_level(s, l)
