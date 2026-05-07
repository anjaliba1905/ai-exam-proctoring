# dashboard/teacher_dashboard.py — v8 UI on v7 DB (merged)
# Full v8 redesign: sidebar nav, refined cards, Toast, GLOBAL_STYLE
# DB calls use the actual schema: id, start_time, end_time, status, score,
# risk_score, risk_level, student_id, name, department, details

import sys, os, csv
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QTableWidget, QTableWidgetItem,
    QStackedWidget, QLineEdit, QMessageBox, QHeaderView,
    QSplitter, QScrollArea, QFileDialog, QSizePolicy, QApplication
)
from PyQt5.QtCore  import Qt, QTimer, pyqtSignal
from PyQt5.QtGui   import QFont, QColor

from database import (get_all_students, add_student, delete_student,
                      get_all_sessions, get_violations, get_violation_counts,
                      init_exam_config)
from ai_modules.risk_scoring import RiskScorer
from dashboard.exam_config_tab import ExamConfigTab
from ui.risk_timeline_widget import RiskTimelineWidget

# ═══════════════════════════════════════════════════════════════════
#  DESIGN TOKENS
# ═══════════════════════════════════════════════════════════════════
COLOR = {
    "bg_base":        "#0a0d12",
    "bg_surface":     "#10151e",
    "bg_elevated":    "#161d2b",
    "bg_card":        "#1a2234",
    "bg_hover":       "#1e2840",
    "border":         "#252f44",
    "border_strong":  "#2e3d5a",
    "text_primary":   "#e8edf5",
    "text_secondary": "#8892a4",
    "text_muted":     "#4a5568",
    "accent_blue":    "#3b82f6",
    "accent_green":   "#22c55e",
    "accent_orange":  "#f59e0b",
    "accent_red":     "#ef4444",
    "accent_purple":  "#a78bfa",
}

RISK_PALETTE = {
    "Low Risk":    {"fg": "#22c55e", "bg": "#052e16", "border": "#166534"},
    "Medium Risk": {"fg": "#f59e0b", "bg": "#1c1501", "border": "#92400e"},
    "High Risk":   {"fg": "#ef4444", "bg": "#2d0505", "border": "#991b1b"},
}

VIOL_COLORS = {
    "phone_detected": "#ef4444",
    "multiple_faces": "#f59e0b",
    "no_face":        "#eab308",
    "gaze_away":      "#60a5fa",
    "tab_switch":     "#c084fc",
    "audio_alert":    "#fb923c",
}
VIOL_ICONS = {
    "phone_detected": "📱", "multiple_faces": "👥", "no_face": "👤",
    "gaze_away": "👁", "tab_switch": "🖥", "audio_alert": "🔊",
}

GLOBAL_STYLE = f"""
QMainWindow, QWidget {{
    background: {COLOR['bg_base']};
    color: {COLOR['text_primary']};
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 13px;
}}
QFrame#sidebar {{
    background: {COLOR['bg_surface']};
    border-right: 1px solid {COLOR['border']};
}}
QPushButton#navBtn {{
    background: transparent; color: {COLOR['text_secondary']};
    border: none; border-radius: 8px; padding: 11px 16px;
    text-align: left; font-size: 13px;
}}
QPushButton#navBtn:hover {{ background: {COLOR['bg_hover']}; color: {COLOR['text_primary']}; }}
QPushButton#navBtnActive {{
    background: {COLOR['bg_elevated']}; color: {COLOR['accent_blue']};
    border: none; border-left: 3px solid {COLOR['accent_blue']};
    border-radius: 8px; padding: 11px 16px;
    text-align: left; font-size: 13px; font-weight: bold;
}}
QFrame#card {{
    background: {COLOR['bg_card']}; border: 1px solid {COLOR['border']};
    border-radius: 12px;
}}
QFrame#statCard {{
    background: {COLOR['bg_elevated']}; border: 1px solid {COLOR['border']};
    border-radius: 10px; min-width: 120px;
}}
QTableWidget {{
    background: {COLOR['bg_elevated']}; border: 1px solid {COLOR['border']};
    border-radius: 10px; gridline-color: {COLOR['border']};
    outline: none; selection-background-color: transparent;
    alternate-background-color: {COLOR['bg_card']};
}}
QTableWidget::item {{
    padding: 10px 14px; border-bottom: 1px solid {COLOR['border']};
    color: {COLOR['text_primary']};
}}
QTableWidget::item:selected {{ background: {COLOR['bg_hover']}; color: {COLOR['text_primary']}; }}
QTableWidget::item:hover {{ background: {COLOR['bg_hover']}; }}
QHeaderView::section {{
    background: {COLOR['bg_surface']}; color: {COLOR['text_secondary']};
    padding: 11px 14px; border: none;
    border-bottom: 1px solid {COLOR['border_strong']};
    font-weight: bold; font-size: 11px; letter-spacing: 0.5px;
}}
QHeaderView {{ background: {COLOR['bg_surface']}; }}
QLineEdit {{
    background: {COLOR['bg_elevated']}; border: 1px solid {COLOR['border']};
    border-radius: 8px; padding: 9px 14px; color: {COLOR['text_primary']}; font-size: 13px;
}}
QLineEdit:focus {{ border: 1px solid {COLOR['accent_blue']}; background: {COLOR['bg_card']}; }}
QPushButton#btnPrimary {{
    background: {COLOR['accent_blue']}; color: white; border: none;
    border-radius: 8px; padding: 10px 20px; font-size: 13px; font-weight: bold;
}}
QPushButton#btnPrimary:hover {{ background: #2563eb; }}
QPushButton#btnPrimary:pressed {{ background: #1d4ed8; }}
QPushButton#btnDanger {{
    background: #dc2626; color: #ffffff;
    border: none; border-radius: 6px;
    padding: 7px 16px; font-size: 12px; font-weight: 600;
    min-width: 76px;
}}
QPushButton#btnDanger:hover {{ background: #b91c1c; }}
QPushButton#btnDanger:pressed {{ background: #991b1b; }}
QPushButton#btnSecondary {{
    background: {COLOR['bg_elevated']}; color: {COLOR['text_primary']};
    border: 1px solid {COLOR['border']}; border-radius: 8px; padding: 9px 18px; font-size: 12px;
}}
QPushButton#btnSecondary:hover {{ background: {COLOR['bg_hover']}; border-color: {COLOR['border_strong']}; }}
QPushButton#btnSuccess {{
    background: #052e16; color: {COLOR['accent_green']};
    border: 1px solid #166534; border-radius: 8px; padding: 9px 18px;
    font-size: 12px; font-weight: bold;
}}
QPushButton#btnSuccess:hover {{ background: #0a3d1f; border-color: {COLOR['accent_green']}; }}
QScrollBar:vertical {{ background: transparent; width: 6px; margin: 0; }}
QScrollBar::handle:vertical {{
    background: {COLOR['border_strong']}; border-radius: 3px; min-height: 40px;
}}
QScrollBar::handle:vertical:hover {{ background: {COLOR['text_muted']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QScrollBar:horizontal {{ background: transparent; height: 6px; }}
QScrollBar::handle:horizontal {{ background: {COLOR['border_strong']}; border-radius: 3px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QScrollArea {{ border: none; background: transparent; }}
QSplitter::handle {{ background: {COLOR['border']}; width: 1px; }}
QFrame#toast {{
    background: {COLOR['bg_card']}; border: 1px solid {COLOR['border_strong']};
    border-radius: 10px; padding: 12px 20px;
}}
"""


# ═══════════════════════════════════════════════════════════════════
#  STUDENT LIST ITEM
# ═══════════════════════════════════════════════════════════════════

class StudentListItem(QFrame):
    clicked = pyqtSignal(str)

    def __init__(self, student_id, name, dept, risk_score, risk_level, viol_count, parent=None):
        super().__init__(parent)
        self.student_id = student_id
        self.setFixedHeight(72)
        self.setCursor(Qt.PointingHandCursor)
        rp = RISK_PALETTE.get(risk_level, {"fg": COLOR["text_primary"],
                                            "bg": COLOR["bg_card"], "border": COLOR["border"]})
        self.setStyleSheet(
            f"QFrame{{background:{COLOR['bg_elevated']};border:none;"
            f"border-bottom:1px solid {COLOR['border']};padding:0;}}"
            f"QFrame:hover{{background:{COLOR['bg_hover']};}}"
        )
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 10, 16, 10)
        row.setSpacing(12)

        badge = QLabel(f"{risk_score:.0f}")
        badge.setFixedSize(44, 44)
        badge.setAlignment(Qt.AlignCenter)
        badge.setFont(QFont("Segoe UI", 14, QFont.Bold))
        badge.setStyleSheet(
            f"background:{rp['bg']};color:{rp['fg']};"
            f"border-radius:22px;border:1px solid {rp['border']};"
        )
        row.addWidget(badge)

        info = QVBoxLayout(); info.setSpacing(2)
        name_lbl = QLabel(name)
        name_lbl.setFont(QFont("Segoe UI", 13, QFont.Bold))
        name_lbl.setStyleSheet(f"color:{COLOR['text_primary']};border:none;background:transparent;")
        sub = QLabel(f"{student_id}  ·  {dept}")
        sub.setStyleSheet(f"color:{COLOR['text_secondary']};font-size:11px;border:none;background:transparent;")
        info.addWidget(name_lbl)
        info.addWidget(sub)
        row.addLayout(info, stretch=1)

        risk_pill = QLabel(risk_level.replace(" Risk", ""))
        risk_pill.setStyleSheet(
            f"color:{rp['fg']};font-size:11px;font-weight:bold;"
            f"background:{rp['bg']};border:1px solid {rp['border']};"
            f"border-radius:5px;padding:3px 8px;"
        )
        row.addWidget(risk_pill)

        if viol_count > 0:
            vc = QLabel(f"⚠ {viol_count}")
            vc.setStyleSheet(
                f"color:{COLOR['accent_red']};font-size:11px;font-weight:bold;"
                f"background:#2d050566;border:1px solid {COLOR['accent_red']}55;"
                f"border-radius:5px;padding:3px 8px;"
            )
            row.addWidget(vc)

    def mousePressEvent(self, _event):
        self.clicked.emit(self.student_id)


# ═══════════════════════════════════════════════════════════════════
#  TOAST
# ═══════════════════════════════════════════════════════════════════

class Toast(QFrame):
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("toast")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        self._icon = QLabel("✓")
        self._icon.setFont(QFont("Segoe UI", 14))
        self._msg  = QLabel("")
        self._msg.setFont(QFont("Segoe UI", 12))
        lay.addWidget(self._icon)
        lay.addWidget(self._msg)
        self.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_message(self, msg, ok=True):
        self._icon.setText("✓" if ok else "✕")
        self._icon.setStyleSheet(
            f"color:{'#22c55e' if ok else '#ef4444'};background:transparent;border:none;"
        )
        self._msg.setText(msg)
        self._msg.setStyleSheet(f"color:{COLOR['text_primary']};background:transparent;border:none;")
        self.adjustSize()
        if self.parent():
            self.move(self.parent().width() - self.width() - 24, 24)
        self.show(); self.raise_()
        self._timer.start(3200)


# ═══════════════════════════════════════════════════════════════════
#  MAIN DASHBOARD
# ═══════════════════════════════════════════════════════════════════

class TeacherDashboard(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("ProctorAI  —  Teacher Dashboard")
        self.setMinimumSize(1440, 900)
        self.setStyleSheet(GLOBAL_STYLE)

        self.risk_scorer       = RiskScorer()
        self._selected_student = None
        self._sessions_cache   = []
        init_exam_config()

        self._build_ui()
        self._refresh_all()

        self._auto_timer = QTimer(self)
        self._auto_timer.timeout.connect(self._refresh_all)
        self._auto_timer.start(12_000)

    # ── BUILD ─────────────────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_sidebar())

        self._stack = QStackedWidget()
        self._stack.addWidget(self._monitoring_page())   # 0
        self._stack.addWidget(self._students_page())     # 1
        self._stack.addWidget(self._sessions_page())     # 2
        self._stack.addWidget(self._violations_page())   # 3
        self._exam_config = ExamConfigTab()
        self._exam_config.config_changed.connect(self._on_config_saved)
        self._stack.addWidget(self._exam_config)         # 4
        root.addWidget(self._stack, stretch=1)

        self._toast = Toast(central)
        self._toast.setFixedWidth(300)

    def _build_sidebar(self):
        sb = QFrame(); sb.setObjectName("sidebar"); sb.setFixedWidth(220)
        lay = QVBoxLayout(sb); lay.setContentsMargins(12, 20, 12, 20); lay.setSpacing(4)

        brand = QLabel("🎓  ProctorAI")
        brand.setFont(QFont("Segoe UI", 15, QFont.Bold))
        brand.setStyleSheet(f"color:{COLOR['text_primary']};padding:0 8px 16px 8px;background:transparent;")
        lay.addWidget(brand)

        div = QFrame(); div.setFrameShape(QFrame.HLine)
        div.setStyleSheet(f"border:none;border-top:1px solid {COLOR['border']};margin-bottom:12px;")
        lay.addWidget(div)

        self._nav_btns = []
        for label, idx in [("  📡   Live Monitor", 0), ("  👥   Students", 1),
                            ("  📋   Sessions", 2),    ("  ⚠    Violations", 3),
                            ("  ⚙    Exam Config", 4)]:
            btn = QPushButton(label); btn.setObjectName("navBtn")
            btn.clicked.connect(lambda _, i=idx: self._nav(i))
            btn.setCursor(Qt.PointingHandCursor)
            lay.addWidget(btn)
            self._nav_btns.append(btn)

        lay.addStretch()

        ref = QPushButton("  ⟳   Refresh Data"); ref.setObjectName("btnSecondary")
        ref.clicked.connect(self._refresh_all); ref.setCursor(Qt.PointingHandCursor)
        lay.addWidget(ref)

        self._status_dot = QLabel("● Live")
        self._status_dot.setStyleSheet(
            f"color:{COLOR['accent_green']};font-size:11px;padding:4px 8px;background:transparent;"
        )
        lay.addWidget(self._status_dot)
        return sb

    def _nav(self, idx):
        self._stack.setCurrentIndex(idx)
        for i, btn in enumerate(self._nav_btns):
            btn.setObjectName("navBtnActive" if i == idx else "navBtn")
            btn.setStyleSheet("")
        self.setStyleSheet(GLOBAL_STYLE)

    # ── STAT CARDS ────────────────────────────────────────────────────────────

    def _stat_cards_row(self):
        row = QHBoxLayout(); row.setSpacing(10)
        self._stat_labels = {}
        for label, val, color, icon in [
            ("Students",     "0", COLOR["accent_blue"],   "👥"),
            ("Sessions",     "0", COLOR["accent_green"],  "📋"),
            ("Violations",   "0", COLOR["accent_orange"], "⚠"),
            ("High Risk",    "0", COLOR["accent_red"],    "🔴"),
            ("Active Exams", "0", COLOR["accent_purple"], "🟣"),
        ]:
            card = QFrame(); card.setObjectName("statCard")
            cl = QVBoxLayout(card); cl.setContentsMargins(16, 14, 16, 14); cl.setSpacing(4)
            top = QHBoxLayout()
            num = QLabel(val); num.setFont(QFont("Segoe UI", 26, QFont.Bold))
            num.setStyleSheet(f"color:{color};border:none;background:transparent;")
            ic  = QLabel(icon); ic.setFont(QFont("Segoe UI", 16))
            ic.setStyleSheet("border:none;background:transparent;")
            top.addWidget(num); top.addStretch(); top.addWidget(ic)
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color:{COLOR['text_secondary']};font-size:11px;border:none;background:transparent;")
            cl.addLayout(top); cl.addWidget(lbl)
            self._stat_labels[label] = num
            row.addWidget(card)
        row.addStretch()
        return row

    # ── MONITORING PAGE ───────────────────────────────────────────────────────

    def _monitoring_page(self):
        page = QWidget()
        lay  = QVBoxLayout(page)
        lay.setContentsMargins(24, 20, 24, 20); lay.setSpacing(16)

        hdr = QHBoxLayout()
        title = QLabel("Live Monitoring"); title.setFont(QFont("Segoe UI", 18, QFont.Bold))
        hdr.addWidget(title); hdr.addStretch()
        self._live_time = QLabel("")
        self._live_time.setStyleSheet(f"color:{COLOR['text_secondary']};font-size:12px;background:transparent;")
        hdr.addWidget(self._live_time)
        lay.addLayout(hdr)
        lay.addLayout(self._stat_cards_row())

        splitter = QSplitter(Qt.Horizontal); splitter.setHandleWidth(1)

        # ── LEFT: student list ─────────────────────────────────────────────
        left = QWidget()
        ll = QVBoxLayout(left); ll.setContentsMargins(0, 0, 8, 0); ll.setSpacing(8)

        list_hdr = QHBoxLayout()
        list_title = QLabel("Students"); list_title.setFont(QFont("Segoe UI", 13, QFont.Bold))
        self._list_count_badge = QLabel("0")
        self._list_count_badge.setStyleSheet(
            f"background:{COLOR['bg_elevated']};color:{COLOR['text_secondary']};"
            f"border-radius:10px;padding:2px 8px;font-size:11px;"
        )
        list_hdr.addWidget(list_title); list_hdr.addWidget(self._list_count_badge); list_hdr.addStretch()
        ll.addLayout(list_hdr)

        hint = QLabel("Ranked by risk  ·  highest first")
        hint.setStyleSheet(f"color:{COLOR['text_muted']};font-size:11px;background:transparent;")
        ll.addWidget(hint)

        self._student_list_scroll  = QScrollArea(); self._student_list_scroll.setWidgetResizable(True)
        self._student_list_inner   = QWidget()
        self._student_list_layout  = QVBoxLayout(self._student_list_inner)
        self._student_list_layout.setContentsMargins(0, 0, 0, 0); self._student_list_layout.setSpacing(0)
        self._student_list_layout.addStretch()
        self._student_list_scroll.setWidget(self._student_list_inner)
        self._student_list_inner.setStyleSheet(
            f"background:{COLOR['bg_elevated']};border-radius:10px;border:1px solid {COLOR['border']};"
        )
        ll.addWidget(self._student_list_scroll)
        splitter.addWidget(left)

        # ── RIGHT: detail ──────────────────────────────────────────────────
        right = QScrollArea(); right.setWidgetResizable(True)
        right_inner = QWidget()
        rl = QVBoxLayout(right_inner); rl.setContentsMargins(12, 0, 0, 0); rl.setSpacing(12)

        self._detail_placeholder = QLabel("← Select a student to view their monitoring detail")
        self._detail_placeholder.setAlignment(Qt.AlignCenter)
        self._detail_placeholder.setStyleSheet(
            f"color:{COLOR['text_muted']};font-size:14px;padding:60px;background:transparent;"
        )
        rl.addWidget(self._detail_placeholder)

        # Header card
        self._detail_header_card = QFrame(); self._detail_header_card.setObjectName("card")
        dhl = QHBoxLayout(self._detail_header_card); dhl.setContentsMargins(20, 14, 20, 14)
        self._detail_name = QLabel("—"); self._detail_name.setFont(QFont("Segoe UI", 16, QFont.Bold))
        self._detail_dept = QLabel("")
        self._detail_dept.setStyleSheet(f"color:{COLOR['text_secondary']};font-size:12px;background:transparent;")
        nc = QVBoxLayout(); nc.setSpacing(2); nc.addWidget(self._detail_name); nc.addWidget(self._detail_dept)
        dhl.addLayout(nc); dhl.addStretch()
        self._detail_risk = QLabel(""); self._detail_risk.setFont(QFont("Segoe UI", 14, QFont.Bold))
        dhl.addWidget(self._detail_risk)
        self._detail_header_card.hide()
        rl.addWidget(self._detail_header_card)

        # Alert banner
        self._alert_banner = QFrame()
        self._alert_banner.setStyleSheet(
            f"background:#2d050566;border:1px solid {COLOR['accent_red']}77;border-radius:8px;"
        )
        ab_lay = QHBoxLayout(self._alert_banner); ab_lay.setContentsMargins(14, 10, 14, 10)
        ab_icon = QLabel("⚠"); ab_icon.setFont(QFont("Segoe UI", 14))
        ab_icon.setStyleSheet(f"color:{COLOR['accent_red']};background:transparent;border:none;")
        self._alert_text = QLabel("")
        self._alert_text.setWordWrap(True)
        self._alert_text.setStyleSheet(
            f"color:{COLOR['accent_red']};font-size:12px;font-weight:bold;background:transparent;border:none;"
        )
        ab_lay.addWidget(ab_icon); ab_lay.addWidget(self._alert_text, stretch=1)
        self._alert_banner.hide()
        rl.addWidget(self._alert_banner)
        self._alert_clear = QTimer(self); self._alert_clear.setSingleShot(True)
        self._alert_clear.timeout.connect(self._alert_banner.hide)

        # AI row
        ai_row = QHBoxLayout(); ai_row.setSpacing(10)

        tl_card = QFrame(); tl_card.setObjectName("card")
        tlc = QVBoxLayout(tl_card); tlc.setContentsMargins(14, 12, 14, 12)
        tl_hdr = QHBoxLayout()
        tl_hdr_lbl = QLabel("📈  Risk Timeline")
        tl_hdr_lbl.setFont(QFont("Segoe UI", 12, QFont.Bold))
        tl_hdr_lbl.setStyleSheet(f"color:{COLOR['text_primary']};background:transparent;border:none;")
        tl_hdr.addWidget(tl_hdr_lbl); tl_hdr.addStretch()
        self._tl_current_lbl = QLabel("—")
        self._tl_current_lbl.setStyleSheet(f"color:{COLOR['text_secondary']};font-size:11px;background:transparent;")
        tl_hdr.addWidget(self._tl_current_lbl)
        tlc.addLayout(tl_hdr)

        legend = QHBoxLayout(); legend.setSpacing(16)
        for lbl, col in [("● Low (0–35)", "#22c55e"), ("● Med (35–65)", "#f59e0b"), ("● High (65+)", "#ef4444")]:
            d = QLabel("●"); d.setStyleSheet(f"color:{col};font-size:10px;background:transparent;")
            t = QLabel(lbl.split(" ", 1)[1])
            t.setStyleSheet(f"color:{COLOR['text_secondary']};font-size:10px;background:transparent;")
            rr = QHBoxLayout(); rr.setSpacing(4); rr.addWidget(d); rr.addWidget(t)
            legend.addLayout(rr)
        legend.addStretch()
        tlc.addLayout(legend)

        self._timeline_widget = RiskTimelineWidget()
        self._timeline_widget.setMinimumHeight(200)
        tlc.addWidget(self._timeline_widget, stretch=1)
        ai_row.addWidget(tl_card, stretch=3)

        ai_right = QVBoxLayout(); ai_right.setSpacing(8)

        # 📷 Camera
        self._cam_card = QFrame(); self._cam_card.setObjectName("card")
        cc = QVBoxLayout(self._cam_card); cc.setContentsMargins(14, 10, 14, 10); cc.setSpacing(6)
        cam_hdr = QHBoxLayout()
        cam_hdr_lbl = QLabel("📷  Live Camera")
        cam_hdr_lbl.setFont(QFont("Segoe UI", 11, QFont.Bold))
        cam_hdr_lbl.setStyleSheet(f"color:{COLOR['text_secondary']};background:transparent;border:none;")
        self._cam_status_dot = QLabel("●")
        self._cam_status_dot.setStyleSheet(f"color:{COLOR['accent_green']};font-size:9px;background:transparent;")
        cam_hdr.addWidget(cam_hdr_lbl); cam_hdr.addStretch(); cam_hdr.addWidget(self._cam_status_dot)
        cc.addLayout(cam_hdr)
        self._cam_thumb = QLabel()
        self._cam_thumb.setAlignment(Qt.AlignCenter)
        self._cam_thumb.setFixedSize(180, 110)
        self._cam_thumb.setStyleSheet(
            f"background:{COLOR['bg_base']};border:1px solid {COLOR['border']};"
            f"border-radius:6px;color:{COLOR['text_muted']};font-size:10px;"
        )
        self._cam_thumb.setText("📷  No feed\n(camera off)")
        cc.addWidget(self._cam_thumb, alignment=Qt.AlignCenter)
        ai_right.addWidget(self._cam_card)

        self._intent_card    = self._info_panel("🧠  Intent Analysis",   "No suspicious intent detected")
        self._predict_card   = self._info_panel("🔮  Risk Prediction",   "No high-risk predictions")
        self._invisible_card = self._info_panel("👻  Invisible Signals", "No hidden cheating detected")
        ai_right.addWidget(self._intent_card[0])
        ai_right.addWidget(self._predict_card[0])
        ai_right.addWidget(self._invisible_card[0])
        ai_row.addLayout(ai_right, stretch=2)
        rl.addLayout(ai_row)

        # Violations mini-table
        viol_hdr = QLabel("Recent Violations")
        viol_hdr.setFont(QFont("Segoe UI", 13, QFont.Bold))
        viol_hdr.setStyleSheet("background:transparent;")
        rl.addWidget(viol_hdr)

        self._detail_viol_table = QTableWidget()
        self._detail_viol_table.setColumnCount(3)
        self._detail_viol_table.setHorizontalHeaderLabels(["Time", "Type", "Detail"])
        self._detail_viol_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._detail_viol_table.setColumnWidth(0, 90); self._detail_viol_table.setColumnWidth(1, 150)
        self._detail_viol_table.verticalHeader().setVisible(False)
        self._detail_viol_table.setShowGrid(False)
        self._detail_viol_table.setSelectionMode(QTableWidget.NoSelection)
        self._detail_viol_table.setMinimumHeight(180)
        self._detail_viol_table.setMaximumHeight(260)
        rl.addWidget(self._detail_viol_table)
        rl.addStretch()

        right.setWidget(right_inner)
        splitter.addWidget(right)
        splitter.setSizes([300, 920])
        lay.addWidget(splitter, stretch=1)
        return page

    def _info_panel(self, title, placeholder):
        card = QFrame(); card.setObjectName("card")
        cl = QVBoxLayout(card); cl.setContentsMargins(14, 10, 14, 10); cl.setSpacing(5)
        hdr = QLabel(title); hdr.setFont(QFont("Segoe UI", 11, QFont.Bold))
        hdr.setStyleSheet(f"color:{COLOR['text_secondary']};background:transparent;border:none;")
        body = QLabel(placeholder); body.setFont(QFont("Segoe UI", 11))
        body.setWordWrap(True)
        body.setStyleSheet(f"color:{COLOR['accent_green']};background:transparent;border:none;")
        cl.addWidget(hdr); cl.addWidget(body)
        return card, body

    # ── STUDENTS PAGE ─────────────────────────────────────────────────────────

    def _students_page(self):
        page = QWidget()
        lay  = QVBoxLayout(page); lay.setContentsMargins(24, 20, 24, 20); lay.setSpacing(16)
        hdr = QLabel("Student Management"); hdr.setFont(QFont("Segoe UI", 18, QFont.Bold))
        lay.addWidget(hdr)

        form = QFrame(); form.setObjectName("card")
        fl = QVBoxLayout(form); fl.setContentsMargins(20, 16, 20, 16); fl.setSpacing(12)
        ft = QLabel("Add New Student"); ft.setFont(QFont("Segoe UI", 13, QFont.Bold))
        fl.addWidget(ft)
        fr = QHBoxLayout(); fr.setSpacing(10)
        self._f_sid   = QLineEdit(); self._f_sid.setPlaceholderText("Student ID")
        self._f_name  = QLineEdit(); self._f_name.setPlaceholderText("Full Name")
        self._f_email = QLineEdit(); self._f_email.setPlaceholderText("Email")
        self._f_dept  = QLineEdit(); self._f_dept.setPlaceholderText("Department")
        self._f_pass  = QLineEdit(); self._f_pass.setPlaceholderText("Password")
        self._f_pass.setEchoMode(QLineEdit.Password)
        for f in [self._f_sid, self._f_name, self._f_email, self._f_dept, self._f_pass]:
            fr.addWidget(f)
        add_btn = QPushButton("  + Add Student"); add_btn.setObjectName("btnPrimary")
        add_btn.clicked.connect(self._add_student); add_btn.setCursor(Qt.PointingHandCursor)
        fr.addWidget(add_btn)
        fl.addLayout(fr)
        lay.addWidget(form)

        self._students_table = QTableWidget()
        self._students_table.setColumnCount(6)
        self._students_table.setHorizontalHeaderLabels(
            ["Student ID", "Name", "Email", "Department", "Sessions", "Action"])
        self._students_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._students_table.setColumnWidth(0, 110); self._students_table.setColumnWidth(4, 80)
        self._students_table.setColumnWidth(5, 110)
        self._students_table.verticalHeader().setVisible(False)
        self._students_table.setShowGrid(False)
        self._students_table.setAlternatingRowColors(True)
        lay.addWidget(self._students_table, stretch=1)
        return page

    # ── SESSIONS PAGE ─────────────────────────────────────────────────────────

    def _sessions_page(self):
        page = QWidget()
        lay  = QVBoxLayout(page); lay.setContentsMargins(24, 20, 24, 20); lay.setSpacing(16)
        hr = QHBoxLayout()
        hdr = QLabel("Exam Sessions"); hdr.setFont(QFont("Segoe UI", 18, QFont.Bold))
        hr.addWidget(hdr); hr.addStretch()
        exp = QPushButton("  ⬇  Export CSV"); exp.setObjectName("btnSecondary")
        exp.clicked.connect(self._export_sessions); exp.setCursor(Qt.PointingHandCursor)
        hr.addWidget(exp)
        lay.addLayout(hr)

        self._sessions_table = QTableWidget()
        self._sessions_table.setColumnCount(8)
        self._sessions_table.setHorizontalHeaderLabels(
            ["ID", "Student", "Department", "Start", "End", "Score%", "Risk Score", "Risk Level"])
        self._sessions_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._sessions_table.setColumnWidth(0, 55); self._sessions_table.setColumnWidth(1, 130)
        self._sessions_table.setColumnWidth(3, 140); self._sessions_table.setColumnWidth(4, 120)
        self._sessions_table.setColumnWidth(5, 75);  self._sessions_table.setColumnWidth(6, 100)
        self._sessions_table.setColumnWidth(7, 110)
        self._sessions_table.verticalHeader().setVisible(False)
        self._sessions_table.setShowGrid(False)
        self._sessions_table.setAlternatingRowColors(True)
        lay.addWidget(self._sessions_table, stretch=1)
        return page

    # ── VIOLATIONS PAGE ───────────────────────────────────────────────────────

    def _violations_page(self):
        page = QWidget()
        lay  = QVBoxLayout(page); lay.setContentsMargins(24, 20, 24, 20); lay.setSpacing(16)
        hr = QHBoxLayout()
        hdr = QLabel("Violation Log"); hdr.setFont(QFont("Segoe UI", 18, QFont.Bold))
        hr.addWidget(hdr); hr.addStretch()
        self._viol_filter = QLineEdit(); self._viol_filter.setPlaceholderText("Filter by Student ID…")
        self._viol_filter.setFixedWidth(200)
        hr.addWidget(self._viol_filter)
        fb = QPushButton("Apply"); fb.setObjectName("btnSecondary")
        fb.clicked.connect(self._load_violations); fb.setCursor(Qt.PointingHandCursor)
        hr.addWidget(fb)
        exp2 = QPushButton("  ⬇  Export CSV"); exp2.setObjectName("btnSecondary")
        exp2.clicked.connect(self._export_violations); exp2.setCursor(Qt.PointingHandCursor)
        hr.addWidget(exp2)
        lay.addLayout(hr)

        self._violations_table = QTableWidget()
        self._violations_table.setColumnCount(5)
        self._violations_table.setHorizontalHeaderLabels(
            ["Session", "Student ID", "Time", "Type", "Detail"])
        self._violations_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self._violations_table.setColumnWidth(0, 70); self._violations_table.setColumnWidth(1, 130)
        self._violations_table.setColumnWidth(2, 150); self._violations_table.setColumnWidth(3, 150)
        self._violations_table.verticalHeader().setVisible(False)
        self._violations_table.setShowGrid(False)
        self._violations_table.setAlternatingRowColors(True)
        lay.addWidget(self._violations_table, stretch=1)
        return page

    # ── REFRESH ───────────────────────────────────────────────────────────────

    def _refresh_all(self):
        from datetime import datetime
        self._live_time.setText(f"Updated {datetime.now().strftime('%H:%M:%S')}")
        self._sessions_cache = get_all_sessions()
        self._load_student_list()
        self._load_students_table()
        self._load_sessions_table()
        self._load_violations()
        if self._selected_student:
            self._select_student(self._selected_student)

    def _on_config_saved(self):
        self._toast.show_message("Exam configuration saved ✓")

    # ── STUDENT LIST (monitoring) ─────────────────────────────────────────────

    def _load_student_list(self):
        lay = self._student_list_layout
        while lay.count() > 1:
            item = lay.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        students = get_all_students()
        self._list_count_badge.setText(str(len(students)))

        ranked = []
        active_count = high_count = 0
        for s in students:
            sid = s["student_id"]
            s_sessions = [x for x in self._sessions_cache if x["student_id"] == sid]
            if not s_sessions:
                ranked.append((s, 0.0, "Low Risk", 0)); continue
            latest  = max(s_sessions, key=lambda x: x["id"])
            vcounts = get_violation_counts(latest["id"])
            score, level = self.risk_scorer.calculate(vcounts)
            vt = sum(vcounts.values())
            if latest.get("status") == "active": active_count += 1
            if level == "High Risk": high_count += 1
            ranked.append((s, score, level, vt))

        ranked.sort(key=lambda x: -x[1])
        self._stat_labels["Students"].setText(str(len(students)))
        self._stat_labels["Active Exams"].setText(str(active_count))
        self._stat_labels["High Risk"].setText(str(high_count))

        for s, score, level, vt in ranked:
            item = StudentListItem(
                s["student_id"], s["name"], s.get("department", "—"), score, level, vt)
            item.clicked.connect(self._select_student)
            lay.insertWidget(lay.count() - 1, item)

    # ── STUDENT DETAIL ────────────────────────────────────────────────────────

    def _select_student(self, student_id: str):
        self._selected_student = student_id
        students = get_all_students()
        stu = next((s for s in students if s["student_id"] == student_id), None)
        if not stu: return

        s_sessions = [x for x in self._sessions_cache if x["student_id"] == student_id]
        if not s_sessions:
            self._detail_placeholder.show(); self._detail_header_card.hide()
            return

        latest  = max(s_sessions, key=lambda x: x["id"])
        vcounts = get_violation_counts(latest["id"])
        score, level = self.risk_scorer.calculate(vcounts)
        vt = sum(vcounts.values())
        rp = RISK_PALETTE.get(level, {"fg": COLOR["text_primary"],
                                       "bg": COLOR["bg_card"], "border": COLOR["border"]})

        self._detail_placeholder.hide()
        self._detail_header_card.show()
        self._detail_name.setText(stu["name"])
        self._detail_name.setStyleSheet("background:transparent;")
        self._detail_dept.setText(f"{student_id}  ·  {stu.get('department', '—')}")
        self._detail_risk.setText(level)
        self._detail_risk.setStyleSheet(
            f"color:{rp['fg']};background:{rp['bg']};border:1px solid {rp['border']};"
            f"border-radius:6px;padding:4px 12px;font-size:12px;font-weight:bold;"
        )

        if level == "High Risk":
            self._alert_banner.show()
            self._alert_text.setText(
                f"High risk: {student_id}  ·  Score {score:.0f}/100  ·  {vt} violation(s)")
            self._alert_clear.start(9000)
        else:
            self._alert_banner.hide()

        # Timeline
        self._tl_current_lbl.setText(f"Score: {score:.1f}  |  {level}")
        if hasattr(self._timeline_widget, 'push_score'):
            self._timeline_widget.push_score(score)
        if hasattr(self._timeline_widget, 'set_risk_level'):
            self._timeline_widget.set_risk_level(score, level)

        # AI panels
        viols = get_violations(student_id=student_id)
        inv_types   = [v for v in viols if v["violation_type"].startswith("invisible_")]
        intent_types = [v for v in viols if v["violation_type"] in ("gaze_away", "tab_switch", "audio_alert")]

        if intent_types:
            last = intent_types[-1]
            ic = VIOL_COLORS.get(last["violation_type"], COLOR["accent_orange"])
            self._intent_card[1].setText(
                f"{VIOL_ICONS.get(last['violation_type'], '•')} {last['violation_type'].replace('_',' ')}"
                f" — {last.get('details','')[:55]}"
            )
            self._intent_card[1].setStyleSheet(f"color:{ic};background:transparent;border:none;")
        else:
            self._intent_card[1].setText("No suspicious intent detected")
            self._intent_card[1].setStyleSheet(f"color:{COLOR['accent_green']};background:transparent;border:none;")

        if score > 65:
            self._predict_card[1].setText("🔮 High violation rate — intervention recommended")
            self._predict_card[1].setStyleSheet(f"color:{COLOR['accent_red']};background:transparent;border:none;")
        elif score > 35:
            self._predict_card[1].setText("🔮 Medium risk — monitor closely")
            self._predict_card[1].setStyleSheet(f"color:{COLOR['accent_orange']};background:transparent;border:none;")
        else:
            self._predict_card[1].setText("No high-risk predictions")
            self._predict_card[1].setStyleSheet(f"color:{COLOR['accent_green']};background:transparent;border:none;")

        if inv_types:
            last_inv = inv_types[-1]
            self._invisible_card[1].setText(
                f"👻 {last_inv['violation_type'].replace('invisible_','')}  "
                f"— {last_inv.get('details','')[:55]}"
            )
            self._invisible_card[1].setStyleSheet(f"color:{COLOR['accent_purple']};background:transparent;border:none;")
        else:
            self._invisible_card[1].setText("No hidden cheating detected")
            self._invisible_card[1].setStyleSheet(f"color:{COLOR['accent_green']};background:transparent;border:none;")

        # Mini violation table
        recent = viols[-25:]
        vt_tbl = self._detail_viol_table
        vt_tbl.setRowCount(0)
        for v in reversed(recent):
            r = vt_tbl.rowCount(); vt_tbl.insertRow(r); vt_tbl.setRowHeight(r, 42)
            vtype = v["violation_type"]
            color = VIOL_COLORS.get(vtype.replace("invisible_", ""),
                                    COLOR["accent_purple"] if vtype.startswith("invisible_") else COLOR["text_primary"])
            icon  = VIOL_ICONS.get(vtype, "•")
            for col, val in enumerate([
                str(v["timestamp"])[-8:],
                f"{icon} {vtype.replace('_',' ')}",
                v.get("details", "")[:90]
            ]):
                item = QTableWidgetItem(val)
                if col == 1:
                    item.setForeground(QColor(color)); item.setFont(QFont("Segoe UI", 10, QFont.Bold))
                vt_tbl.setItem(r, col, item)

    # ── DATA LOADERS ──────────────────────────────────────────────────────────

    def _load_students_table(self):
        students = get_all_students()
        t = self._students_table; t.setRowCount(0)
        for s in students:
            sid = s["student_id"]
            r = t.rowCount(); t.insertRow(r); t.setRowHeight(r, 48)
            s_count = sum(1 for x in self._sessions_cache if x["student_id"] == sid)
            for col, val in enumerate([sid, s["name"], s.get("email", ""),
                                        s.get("department", ""), str(s_count)]):
                item = QTableWidgetItem(val)
                if col == 4: item.setTextAlignment(Qt.AlignCenter)
                t.setItem(r, col, item)

            del_btn = QPushButton("Delete"); del_btn.setObjectName("btnDanger")
            del_btn.setCursor(Qt.PointingHandCursor)
            del_btn.clicked.connect(lambda _, student_id=sid: self._delete_student(student_id))
            wrap = QWidget(); wl = QHBoxLayout(wrap)
            wl.setContentsMargins(4, 4, 4, 4); wl.setAlignment(Qt.AlignCenter)
            wl.addWidget(del_btn)
            t.setCellWidget(r, 5, wrap)

        self._stat_labels["Students"].setText(str(len(students)))

    def _load_sessions_table(self):
        t = self._sessions_table; t.setRowCount(0)
        viol_total = 0
        for s in self._sessions_cache:
            vcounts = get_violation_counts(s["id"])
            vt = sum(vcounts.values()); viol_total += vt
            score_db  = s.get("risk_score", 0) or 0
            level_db  = s.get("risk_level", "") or ""
            # If session has no saved risk, compute on-the-fly
            if not level_db:
                score_db, level_db = self.risk_scorer.calculate(vcounts)
            rp = RISK_PALETTE.get(level_db, {"fg": COLOR["text_secondary"]})

            r = t.rowCount(); t.insertRow(r); t.setRowHeight(r, 44)
            vals = [
                str(s["id"]), s["student_id"], s.get("department", ""),
                str(s.get("start_time", ""))[:16],
                str(s.get("end_time", "Active"))[:16] if s.get("end_time") else "Active",
                f"{s.get('score', 0) or 0:.1f}%",
                f"{score_db:.0f}/100",
                level_db or "—",
            ]
            for col, val in enumerate(vals):
                item = QTableWidgetItem(val)
                if col == 7:
                    item.setForeground(QColor(rp["fg"])); item.setFont(QFont("Segoe UI", 10, QFont.Bold))
                if col in (5, 6): item.setTextAlignment(Qt.AlignCenter)
                t.setItem(r, col, item)

        self._stat_labels["Sessions"].setText(str(len(self._sessions_cache)))
        self._stat_labels["Violations"].setText(str(viol_total))

    def _load_violations(self):
        sid   = getattr(self, "_viol_filter", None)
        sid   = sid.text().strip() if sid else None
        viols = get_violations(student_id=sid or None)
        t     = self._violations_table; t.setRowCount(0)
        for v in viols:
            r = t.rowCount(); t.insertRow(r); t.setRowHeight(r, 44)
            vtype = v["violation_type"]
            color = VIOL_COLORS.get(vtype.replace("invisible_", ""),
                                    COLOR["accent_purple"] if vtype.startswith("invisible_") else COLOR["text_primary"])
            icon  = VIOL_ICONS.get(vtype, "•")
            for col, val in enumerate([
                str(v.get("session_id", "")), v.get("student_id", ""),
                str(v.get("timestamp", ""))[:16],
                f"{icon} {vtype.replace('_', ' ')}",
                v.get("details", "")
            ]):
                item = QTableWidgetItem(val)
                if col == 3:
                    item.setForeground(QColor(color)); item.setFont(QFont("Segoe UI", 10, QFont.Bold))
                t.setItem(r, col, item)

    # ── ACTIONS ───────────────────────────────────────────────────────────────

    def _add_student(self):
        sid   = self._f_sid.text().strip()
        name  = self._f_name.text().strip()
        email = self._f_email.text().strip()
        dept  = self._f_dept.text().strip()
        pw    = self._f_pass.text().strip()
        if not all([sid, name, email, pw]):
            self._toast.show_message("Fill all required fields (ID, Name, Email, Password)", ok=False)
            return
        ok, msg = add_student(sid, name, email, pw, dept)
        if ok:
            for f in [self._f_sid, self._f_name, self._f_email, self._f_dept, self._f_pass]:
                f.clear()
            self._refresh_all()
            self._toast.show_message(f"Student '{name}' added ✓")
        else:
            self._toast.show_message(f"Error: {msg}", ok=False)

    def _delete_student(self, student_id: str):
        reply = QMessageBox.question(
            self, "Delete Student",
            f"Delete student {student_id}?\nThis removes all their sessions and violations.",
            QMessageBox.Yes | QMessageBox.Cancel
        )
        if reply == QMessageBox.Yes:
            delete_student(student_id)
            self._refresh_all()
            self._toast.show_message(f"Student {student_id} deleted")

    # ── EXPORT ────────────────────────────────────────────────────────────────

    def _export_sessions(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Sessions", "sessions.csv", "CSV (*.csv)")
        if not path: return
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["ID", "Student ID", "Start", "End", "Score%", "Risk Score", "Risk Level", "Status"])
                for s in self._sessions_cache:
                    w.writerow([s["id"], s["student_id"],
                                 str(s.get("start_time",""))[:19], str(s.get("end_time",""))[:19],
                                 s.get("score",""), s.get("risk_score",""),
                                 s.get("risk_level",""), s.get("status","")])
            self._toast.show_message(f"Exported → {path}")
        except Exception as e:
            self._toast.show_message(f"Export failed: {e}", ok=False)

    def _export_violations(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Violations", "violations.csv", "CSV (*.csv)")
        if not path: return
        try:
            sid   = getattr(self, "_viol_filter", None)
            sid   = sid.text().strip() if sid else None
            viols = get_violations(student_id=sid or None)
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["ID", "Session ID", "Student ID", "Timestamp", "Type", "Details"])
                for v in viols:
                    w.writerow([v["id"], v["session_id"], v["student_id"],
                                 str(v["timestamp"])[:19], v["violation_type"], v.get("details","")])
            self._toast.show_message(f"Exported → {path}")
        except Exception as e:
            self._toast.show_message(f"Export failed: {e}", ok=False)
