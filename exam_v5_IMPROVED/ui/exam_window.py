# ui/exam_window.py  –  STUDENT Exam Window (v6 FIXED)
# Fixes:
#   1. Beautiful result dialog with score gauge + breakdown table
#   2. Improved question card layout — readable, well-spaced options
#   3. Leave/Submit button redesigned with warning colour + icon
#   4. No _ready attribute bug — graceful error handling

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QGridLayout,
    QLabel, QPushButton, QFrame, QRadioButton, QButtonGroup,
    QProgressBar, QMessageBox, QScrollArea, QSizePolicy, QDialog,
    QTableWidget, QTableWidgetItem, QHeaderView, QGraphicsDropShadowEffect
)
from PyQt5.QtCore import Qt, QTimer, pyqtSlot, QRectF
from PyQt5.QtGui  import (QFont, QPixmap, QImage, QColor, QPainter,
                           QPen, QBrush, QConicalGradient, QLinearGradient)

from database import (start_session, end_session, log_violation,
                      get_active_questions, save_answer,
                      get_violation_counts, get_exam_config, init_exam_config)
from monitoring.camera_monitor import CameraMonitor
from monitoring.audio_monitor  import AudioMonitor
from monitoring.screen_monitor import ScreenMonitor
from ai_modules.risk_scoring   import RiskScorer

STYLE = """
QMainWindow, QWidget {
    background:#0d1117; color:#e6edf3;
    font-family:'Segoe UI', Arial, sans-serif;
}
QFrame#sidebar {
    background:#111318;
    border-right:2px solid #21262d;
}
QFrame#questionCard {
    background:#161b22;
    border:1px solid #30363d;
    border-radius:14px;
}
QLabel#questionNum  { color:#58a6ff; font-size:13px; font-weight:bold; letter-spacing:1px; }
QLabel#questionText { font-size:16px; color:#e6edf3; line-height:1.7; }
QLabel#timerLabel   { font-size:30px; font-weight:bold; color:#3fb950; letter-spacing:2px; }
QLabel#examTitle    { font-size:12px; color:#8b949e; font-style:italic; }
QRadioButton {
    font-size:14px; color:#c9d1d9;
    padding:13px 16px; spacing:12px;
    border:1.5px solid #30363d;
    border-radius:10px;
    min-height:22px;
}
QRadioButton:hover  { background:#1c2230; border-color:#58a6ff44; color:#e6edf3; }
QRadioButton:checked { background:#1a2d4d; border-color:#58a6ff; color:#79c0ff; font-weight:bold; }
QRadioButton::indicator { width:20px; height:20px; border-radius:10px; border:2px solid #30363d; }
QRadioButton::indicator:checked { background:#58a6ff; border-color:#58a6ff; }
QPushButton#navBtn {
    background:#21262d; color:#c9d1d9;
    border:1px solid #30363d; border-radius:8px;
    padding:10px 20px; font-size:13px; min-width:100px;
}
QPushButton#navBtn:hover  { background:#30363d; border-color:#58a6ff55; }
QPushButton#navBtn:disabled { color:#484f58; background:#161b22; }
QPushButton#submitBtn {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #b91c1c, stop:1 #dc2626);
    color:white; border:none; border-radius:10px;
    padding:14px 32px; font-size:15px; font-weight:bold;
    min-width:180px;
}
QPushButton#submitBtn:hover {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #dc2626, stop:1 #ef4444);
}
QProgressBar {
    background:#21262d; border-radius:5px;
    height:8px; color:transparent;
}
QProgressBar::chunk { background:#58a6ff; border-radius:5px; }
QLabel#camLabel  { background:#0a0e14; border-radius:8px; border:1px solid #21262d; }
QLabel#violBadge {
    color:#f85149; font-size:12px; font-weight:bold;
    background:rgba(248,81,73,0.12); border:1px solid rgba(248,81,73,0.4);
    border-radius:6px; padding:5px 10px;
}
QScrollArea { border:none; background:transparent; }
"""

STATUS_OK   = "color:#3fb950; font-size:11px;"
STATUS_WARN = "color:#f85149; font-size:11px; font-weight:bold;"
STATUS_IDLE = "color:#484f58; font-size:11px;"


# ─── Beautiful Result Dialog ──────────────────────────────────────────────────

class ResultDialog(QDialog):
    """Animated, beautiful result screen shown after exam submission."""

    def __init__(self, student, questions, answers, violation_count, 
                 risk_score, risk_level, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Exam Results")
        self.setModal(True)
        self.setMinimumSize(700, 600)
        self.setStyleSheet("""
            QDialog { background:#0d1117; color:#e6edf3; font-family:'Segoe UI',Arial,sans-serif; }
            QLabel  { color:#e6edf3; }
            QTableWidget {
                background:#161b22; color:#e6edf3;
                border:1px solid #30363d; border-radius:8px;
                gridline-color:#21262d; font-size:12px;
            }
            QTableWidget::item { padding:8px 12px; border-bottom:1px solid #21262d; }
            QTableWidget::item:selected { background:#1f3a5f; color:#79c0ff; }
            QHeaderView::section {
                background:#21262d; color:#8b949e;
                border:none; border-bottom:1px solid #30363d;
                padding:8px 12px; font-size:11px; font-weight:bold;
            }
            QPushButton#closeBtn {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #238636, stop:1 #2ea043);
                color:white; border:none; border-radius:10px;
                padding:14px 40px; font-size:16px; font-weight:bold;
            }
            QPushButton#closeBtn:hover {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #2ea043, stop:1 #3fb950);
            }
        """)

        correct = sum(
            1 for q in questions
            if answers.get(q["id"]) == q["answer"]
        )
        total     = len(questions)
        answered  = len(answers)
        score_pct = int((correct / total) * 100) if total else 0

        self._score_pct   = score_pct
        self._correct     = correct
        self._total       = total
        self._answered    = answered
        self._violations  = violation_count
        self._risk_score  = risk_score
        self._risk_level  = risk_level
        self._student     = student
        self._questions   = questions
        self._answers     = answers

        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Top banner ────────────────────────────────────────────────────
        banner = QFrame()
        banner.setFixedHeight(180)
        banner.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 #0d1117, stop:0.5 #161b22, stop:1 #0d1117);
                border-bottom: 2px solid #21262d;
            }
        """)
        banner_lay = QHBoxLayout(banner)
        banner_lay.setContentsMargins(40, 20, 40, 20)

        # Score gauge (drawn via paintEvent on a custom widget)
        gauge = ScoreGauge(self._score_pct)
        gauge.setFixedSize(140, 140)
        banner_lay.addWidget(gauge)

        banner_lay.addSpacing(32)

        # Student info & headline
        info_col = QVBoxLayout()
        info_col.setSpacing(6)

        done_lbl = QLabel("🎉  Exam Complete!")
        done_lbl.setFont(QFont("Segoe UI", 22, QFont.Bold))
        done_lbl.setStyleSheet("color:#58a6ff;")
        info_col.addWidget(done_lbl)

        name_lbl = QLabel(f"  {self._student.get('name', 'Student')}"
                          f"  ·  {self._student.get('student_id', '')}")
        name_lbl.setStyleSheet("color:#8b949e; font-size:13px;")
        info_col.addWidget(name_lbl)

        info_col.addSpacing(8)

        score_lbl = QLabel(f"{self._correct} / {self._total}  correct")
        score_lbl.setFont(QFont("Segoe UI", 18, QFont.Bold))
        color = self._grade_color(self._score_pct)
        score_lbl.setStyleSheet(f"color:{color};")
        info_col.addWidget(score_lbl)

        grade_lbl = QLabel(self._grade_label(self._score_pct))
        grade_lbl.setFont(QFont("Segoe UI", 13))
        grade_lbl.setStyleSheet(f"color:{color}; font-style:italic;")
        info_col.addWidget(grade_lbl)

        banner_lay.addLayout(info_col)
        banner_lay.addStretch()

        root.addWidget(banner)

        # ── Stats row ─────────────────────────────────────────────────────
        stats_row = QFrame()
        stats_row.setStyleSheet("QFrame { background:#111318; border-bottom:1px solid #21262d; }")
        stats_lay = QHBoxLayout(stats_row)
        stats_lay.setContentsMargins(40, 14, 40, 14)
        stats_lay.setSpacing(0)

        risk_color = {"Low Risk":"#3fb950","Medium Risk":"#f0883e","High Risk":"#f85149"}.get(
            self._risk_level, "#8b949e")

        for label, value, color in [
            ("Questions Answered", f"{self._answered}/{self._total}", "#79c0ff"),
            ("Correct Answers",    f"{self._correct}",               self._grade_color(self._score_pct)),
            ("Score",              f"{self._score_pct}%",            self._grade_color(self._score_pct)),
            ("Violations",         f"{self._violations}",            "#f85149" if self._violations else "#3fb950"),
            ("Risk Level",         self._risk_level,                 risk_color),
        ]:
            stat = self._stat_card(label, value, color)
            stats_lay.addWidget(stat, stretch=1)
            if label != "Risk Level":
                sep = QFrame(); sep.setFrameShape(QFrame.VLine)
                sep.setStyleSheet("border-color:#21262d;")
                stats_lay.addWidget(sep)

        root.addWidget(stats_row)

        # ── Question breakdown table ───────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background:#0d1117; border:none; }")

        inner = QWidget()
        inner.setStyleSheet("background:#0d1117;")
        inner_lay = QVBoxLayout(inner)
        inner_lay.setContentsMargins(32, 20, 32, 20)
        inner_lay.setSpacing(12)

        tbl_hdr = QLabel("📋  Question Breakdown")
        tbl_hdr.setFont(QFont("Segoe UI", 14, QFont.Bold))
        tbl_hdr.setStyleSheet("color:#e6edf3;")
        inner_lay.addWidget(tbl_hdr)

        tbl = QTableWidget()
        tbl.setColumnCount(5)
        tbl.setHorizontalHeaderLabels(["#", "Question", "Your Answer", "Correct Answer", "Result"])
        tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        tbl.setColumnWidth(0, 40)
        tbl.setColumnWidth(2, 120)
        tbl.setColumnWidth(3, 130)
        tbl.setColumnWidth(4, 80)
        tbl.verticalHeader().setVisible(False)
        tbl.setShowGrid(False)
        tbl.setSelectionMode(QTableWidget.NoSelection)
        tbl.setAlternatingRowColors(False)
        tbl.setRowCount(len(self._questions))

        for i, q in enumerate(self._questions):
            your_ans   = self._answers.get(q["id"], "—")
            correct_ans = q["answer"]
            is_correct  = (your_ans == correct_ans) if your_ans != "—" else False

            # Map answer letter → option text
            opt_map = {"A": q.get("option_a",""), "B": q.get("option_b",""),
                       "C": q.get("option_c",""), "D": q.get("option_d","")}
            your_text    = f"{your_ans}. {opt_map.get(your_ans,'—')}" if your_ans != "—" else "Not answered"
            correct_text = f"{correct_ans}. {opt_map.get(correct_ans,'')}"

            num_item = QTableWidgetItem(str(i + 1))
            num_item.setTextAlignment(Qt.AlignCenter)

            q_item   = QTableWidgetItem(q["question"][:90] + ("…" if len(q["question"]) > 90 else ""))
            ya_item  = QTableWidgetItem(your_text)
            ca_item  = QTableWidgetItem(correct_text)
            res_item = QTableWidgetItem("✓  Correct" if is_correct else ("✗  Wrong" if your_ans != "—" else "—  Skipped"))

            res_color = QColor("#3fb950") if is_correct else (QColor("#f85149") if your_ans != "—" else QColor("#8b949e"))

            for item in [num_item, q_item, ya_item, ca_item, res_item]:
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)

            ya_item.setForeground(QColor("#79c0ff") if is_correct else QColor("#f85149"))
            ca_item.setForeground(QColor("#3fb950"))
            res_item.setForeground(res_color)
            res_item.setTextAlignment(Qt.AlignCenter)
            num_item.setTextAlignment(Qt.AlignCenter)

            tbl.setItem(i, 0, num_item)
            tbl.setItem(i, 1, q_item)
            tbl.setItem(i, 2, ya_item)
            tbl.setItem(i, 3, ca_item)
            tbl.setItem(i, 4, res_item)
            tbl.setRowHeight(i, 46)

        inner_lay.addWidget(tbl)

        # Close button
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("✓  Done — Exit Exam")
        close_btn.setObjectName("closeBtn")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        btn_row.addStretch()
        inner_lay.addLayout(btn_row)

        scroll.setWidget(inner)
        root.addWidget(scroll, stretch=1)

    @staticmethod
    def _stat_card(label, value, color):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(4)
        v = QLabel(value)
        v.setFont(QFont("Segoe UI", 20, QFont.Bold))
        v.setStyleSheet(f"color:{color};")
        v.setAlignment(Qt.AlignCenter)
        l = QLabel(label)
        l.setStyleSheet("color:#8b949e; font-size:11px;")
        l.setAlignment(Qt.AlignCenter)
        lay.addWidget(v)
        lay.addWidget(l)
        return w

    @staticmethod
    def _grade_color(pct):
        if pct >= 80: return "#3fb950"
        if pct >= 60: return "#f0883e"
        return "#f85149"

    @staticmethod
    def _grade_label(pct):
        if pct >= 90: return "Excellent 🌟"
        if pct >= 80: return "Great Work 👍"
        if pct >= 60: return "Good Effort"
        if pct >= 40: return "Needs Improvement"
        return "Please Review Material"


class ScoreGauge(QWidget):
    """Circular gauge showing exam score percentage."""

    def __init__(self, score_pct, parent=None):
        super().__init__(parent)
        self._pct = score_pct

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        margin = 10
        rect = QRectF(margin, margin, w - 2*margin, h - 2*margin)

        # Background arc
        pen = QPen(QColor("#21262d"), 10)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawArc(rect, 225 * 16, -270 * 16)

        # Score arc
        color = QColor("#3fb950") if self._pct >= 80 else \
                QColor("#f0883e") if self._pct >= 60 else QColor("#f85149")
        pen2 = QPen(color, 10)
        pen2.setCapStyle(Qt.RoundCap)
        painter.setPen(pen2)
        span = int(-270 * 16 * (self._pct / 100))
        painter.drawArc(rect, 225 * 16, span)

        # Centre text
        painter.setPen(QPen(color))
        font = QFont("Segoe UI", 22, QFont.Bold)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignCenter, f"{self._pct}%")


# ─── Main Exam Window ─────────────────────────────────────────────────────────

class ExamWindow(QMainWindow):

    def __init__(self, student: dict):
        super().__init__()
        init_exam_config()
        cfg = get_exam_config()

        self.student          = student
        self.questions        = get_active_questions()
        self.duration_minutes = int(cfg.get("exam_duration_minutes", 30))
        self.exam_title       = cfg.get("exam_title", "General Knowledge Exam")

        self.cam_monitor    = None
        self.audio_monitor  = None
        self.screen_monitor = None
        self._exam_timer    = None
        self._submitted     = False

        if not self.questions:
            QMessageBox.critical(None, "No Questions",
                "No active questions found. Please ask your teacher to add questions.")
            return

        self.session_id          = start_session(student["student_id"])
        self.answers             = {}
        self.current_q           = 0
        self.risk_scorer         = RiskScorer()
        self.remaining_secs      = self.duration_minutes * 60
        self.violation_count     = 0
        self._current_risk_score = 0.0
        self._current_risk_level = "Low Risk"

        self.setWindowTitle(
            f"AI Exam  —  {student['name']}  [{student['student_id']}]"
        )
        self.setMinimumSize(1050, 720)
        self.setStyleSheet(STYLE)

        self._build_ui()
        self._load_question()
        self._start_timer()
        self._start_monitoring()

    # ── UI BUILD ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── LEFT Sidebar ───────────────────────────────────────────────────
        sidebar = QFrame(); sidebar.setObjectName("sidebar"); sidebar.setFixedWidth(248)
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(16, 18, 16, 16)
        sl.setSpacing(8)

        name_lbl = QLabel(f"👤  {self.student['name']}")
        name_lbl.setFont(QFont("Segoe UI", 12, QFont.Bold))
        sl.addWidget(name_lbl)

        sid_lbl = QLabel(f"ID: {self.student['student_id']}")
        sid_lbl.setStyleSheet("color:#8b949e; font-size:11px;")
        sl.addWidget(sid_lbl)

        title_lbl = QLabel(self.exam_title)
        title_lbl.setObjectName("examTitle"); title_lbl.setWordWrap(True)
        sl.addWidget(title_lbl)

        sl.addWidget(self._divider())

        dur_badge = QLabel(f"⏱  {self.duration_minutes} min  ·  {len(self.questions)} Questions")
        dur_badge.setStyleSheet(
            "background:#1f3a5f; color:#79c0ff; border-radius:6px;"
            " padding:6px 10px; font-size:11px;"
        )
        sl.addWidget(dur_badge)

        self.timer_label = QLabel(f"{self.duration_minutes:02d}:00")
        self.timer_label.setObjectName("timerLabel")
        self.timer_label.setAlignment(Qt.AlignCenter)
        sl.addWidget(self.timer_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(max(len(self.questions), 1))
        self.progress_bar.setValue(0)
        sl.addWidget(self.progress_bar)
        prog_lbl = QLabel("Questions answered")
        prog_lbl.setStyleSheet("color:#8b949e; font-size:10px;")
        sl.addWidget(prog_lbl)

        sl.addWidget(self._divider())

        cam_hdr = QLabel("📷  Live Camera")
        cam_hdr.setStyleSheet("font-weight:bold; font-size:11px; color:#8b949e;")
        sl.addWidget(cam_hdr)

        self.cam_label = QLabel("Initialising…")
        self.cam_label.setObjectName("camLabel")
        self.cam_label.setFixedSize(214, 162)
        self.cam_label.setAlignment(Qt.AlignCenter)
        self.cam_label.setStyleSheet("color:#484f58; font-size:11px; background:#0a0e14; border-radius:8px;")
        sl.addWidget(self.cam_label)

        sl.addWidget(self._divider())
        status_hdr = QLabel("Proctoring Status")
        status_hdr.setStyleSheet("color:#8b949e; font-size:10px; font-weight:bold;")
        sl.addWidget(status_hdr)

        self.face_dot  = self._dot("● Camera", STATUS_IDLE)
        self.audio_dot = self._dot("● Microphone", STATUS_IDLE)
        self.focus_dot = self._dot("● Window Focus", STATUS_IDLE)
        for d in [self.face_dot, self.audio_dot, self.focus_dot]:
            sl.addWidget(d)

        sl.addWidget(self._divider())
        self.viol_badge = QLabel("⚠  Violations: 0")
        self.viol_badge.setObjectName("violBadge")
        self.viol_badge.setAlignment(Qt.AlignCenter)
        sl.addWidget(self.viol_badge)

        sl.addStretch()

        notice = QLabel("🔒  This exam is monitored by AI proctoring.")
        notice.setWordWrap(True)
        notice.setStyleSheet("color:#484f58; font-size:10px; text-align:center;")
        notice.setAlignment(Qt.AlignCenter)
        sl.addWidget(notice)

        root.addWidget(sidebar)

        # ── MAIN: Question area ────────────────────────────────────────────
        main_area = QWidget()
        ml = QVBoxLayout(main_area)
        ml.setContentsMargins(32, 28, 32, 20)
        ml.setSpacing(20)

        # Question card
        qcard = QFrame(); qcard.setObjectName("questionCard")
        qcl   = QVBoxLayout(qcard)
        qcl.setContentsMargins(28, 24, 28, 24)
        qcl.setSpacing(0)

        # Question header: number badge + category
        q_header = QHBoxLayout()
        self.q_num_lbl = QLabel(f"Question  1  of  {len(self.questions)}")
        self.q_num_lbl.setObjectName("questionNum")
        q_header.addWidget(self.q_num_lbl)
        q_header.addStretch()
        self.q_cat_lbl = QLabel("")
        self.q_cat_lbl.setStyleSheet(
            "background:#21262d; color:#8b949e; border-radius:4px;"
            " padding:3px 10px; font-size:11px;"
        )
        q_header.addWidget(self.q_cat_lbl)
        qcl.addLayout(q_header)

        qcl.addSpacing(14)

        # Question text (scrollable if long)
        self.q_text_lbl = QLabel()
        self.q_text_lbl.setObjectName("questionText")
        self.q_text_lbl.setWordWrap(True)
        self.q_text_lbl.setMinimumHeight(60)
        self.q_text_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        qcl.addWidget(self.q_text_lbl)

        qcl.addSpacing(20)

        div2 = QFrame(); div2.setFrameShape(QFrame.HLine)
        div2.setStyleSheet("border:none; border-top:1px solid #21262d; margin:0;")
        qcl.addWidget(div2)

        qcl.addSpacing(16)

        # Answer options — grid 2×2 for compactness when needed
        opts_widget = QWidget()
        opts_lay = QVBoxLayout(opts_widget)
        opts_lay.setSpacing(10)
        opts_lay.setContentsMargins(0, 0, 0, 0)

        self.option_group  = QButtonGroup()
        self.option_radios = {}
        for opt in ["A", "B", "C", "D"]:
            rb = QRadioButton()
            rb.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
            rb.setMinimumHeight(50)
            self.option_radios[opt] = rb
            self.option_group.addButton(rb)
            opts_lay.addWidget(rb)

        qcl.addWidget(opts_widget)
        qcl.addStretch()

        ml.addWidget(qcard, stretch=1)

        # ── Navigation row ─────────────────────────────────────────────────
        nav = QHBoxLayout()
        nav.setSpacing(10)

        self.prev_btn = QPushButton("← Previous")
        self.prev_btn.setObjectName("navBtn")
        self.prev_btn.clicked.connect(self._prev_question)
        nav.addWidget(self.prev_btn)

        # Scrollable question grid
        grid_scroll = QScrollArea()
        grid_scroll.setWidgetResizable(True)
        grid_scroll.setFixedHeight(48)
        grid_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        grid_inner  = QWidget()
        grid_layout = QHBoxLayout(grid_inner)
        grid_layout.setSpacing(5)
        grid_layout.setContentsMargins(4, 4, 4, 4)
        self.q_grid_btns = []
        for i in range(len(self.questions)):
            btn = QPushButton(str(i + 1))
            btn.setFixedSize(36, 36)
            btn.setStyleSheet(
                "QPushButton{background:#21262d;color:#8b949e;border:1px solid #30363d;"
                "border-radius:6px;font-size:11px;font-weight:bold;}"
                "QPushButton:hover{background:#30363d;}"
            )
            btn.clicked.connect(lambda _, idx=i: self._jump_to(idx))
            self.q_grid_btns.append(btn)
            grid_layout.addWidget(btn)
        grid_layout.addStretch()
        grid_scroll.setWidget(grid_inner)
        nav.addWidget(grid_scroll, stretch=1)

        self.next_btn = QPushButton("Next →")
        self.next_btn.setObjectName("navBtn")
        self.next_btn.clicked.connect(self._next_question)
        nav.addWidget(self.next_btn)

        ml.addLayout(nav)

        # ── Submit row — prominent red warning button ───────────────────────
        sub_row = QHBoxLayout()
        sub_row.setContentsMargins(0, 4, 0, 0)

        answered_lbl = QLabel()
        answered_lbl.setObjectName("answeredCount")
        answered_lbl.setStyleSheet("color:#8b949e; font-size:12px;")
        self._answered_count_lbl = answered_lbl
        sub_row.addWidget(answered_lbl)
        sub_row.addStretch()

        self.submit_btn = QPushButton("⚠  End Exam & Submit")
        self.submit_btn.setObjectName("submitBtn")
        self.submit_btn.setMinimumHeight(50)
        self.submit_btn.clicked.connect(self._submit_exam)
        sub_row.addWidget(self.submit_btn)

        ml.addLayout(sub_row)

        root.addWidget(main_area, stretch=1)

    @staticmethod
    def _divider():
        d = QFrame(); d.setFrameShape(QFrame.HLine)
        d.setStyleSheet("border-color:#21262d; margin:2px 0;")
        return d

    @staticmethod
    def _dot(text, style):
        lbl = QLabel(text); lbl.setStyleSheet(style); return lbl

    # ── QUESTIONS ────────────────────────────────────────────────────────────

    def _load_question(self):
        q = self.questions[self.current_q]
        self.q_num_lbl.setText(
            f"Question  {self.current_q + 1}  of  {len(self.questions)}"
        )
        self.q_cat_lbl.setText(q.get("category", ""))
        self.q_text_lbl.setText(q["question"])

        opts = {
            "A": q["option_a"], "B": q["option_b"],
            "C": q["option_c"], "D": q["option_d"]
        }
        for letter, text in opts.items():
            self.option_radios[letter].setText(f"    {letter}.    {text}")
            self.option_radios[letter].setChecked(False)

        saved = self.answers.get(q["id"])
        if saved and saved in self.option_radios:
            self.option_radios[saved].setChecked(True)

        self.prev_btn.setEnabled(self.current_q > 0)
        self.next_btn.setEnabled(self.current_q < len(self.questions) - 1)
        self._refresh_grid()

    def _save_current_answer(self):
        q = self.questions[self.current_q]
        for letter, rb in self.option_radios.items():
            if rb.isChecked():
                self.answers[q["id"]] = letter
                return

    def _prev_question(self):
        self._save_current_answer()
        if self.current_q > 0:
            self.current_q -= 1; self._load_question()

    def _next_question(self):
        self._save_current_answer()
        if self.current_q < len(self.questions) - 1:
            self.current_q += 1; self._load_question()

    def _jump_to(self, idx):
        self._save_current_answer(); self.current_q = idx; self._load_question()

    def _refresh_grid(self):
        answered = 0
        for i, btn in enumerate(self.q_grid_btns):
            qid = self.questions[i]["id"]
            if i == self.current_q:
                btn.setStyleSheet(
                    "QPushButton{background:#1f6feb;color:white;border:none;"
                    "border-radius:6px;font-size:11px;font-weight:bold;}")
            elif qid in self.answers:
                btn.setStyleSheet(
                    "QPushButton{background:#238636;color:white;border:none;"
                    "border-radius:6px;font-size:11px;font-weight:bold;}")
                answered += 1
            else:
                btn.setStyleSheet(
                    "QPushButton{background:#21262d;color:#8b949e;border:1px solid #30363d;"
                    "border-radius:6px;font-size:11px;font-weight:bold;}")
        # Count current if answered
        cur_id = self.questions[self.current_q]["id"]
        if cur_id in self.answers:
            answered += 1
        self.progress_bar.setValue(len(self.answers))
        self._answered_count_lbl.setText(
            f"Answered: {len(self.answers)} / {len(self.questions)}"
        )

    # ── TIMER ────────────────────────────────────────────────────────────────

    def _start_timer(self):
        self._exam_timer = QTimer(self)
        self._exam_timer.timeout.connect(self._tick)
        self._exam_timer.start(1000)

    def _tick(self):
        self.remaining_secs -= 1
        mins, secs = divmod(self.remaining_secs, 60)
        self.timer_label.setText(f"{mins:02d}:{secs:02d}")
        if self.remaining_secs <= 120:
            self.timer_label.setStyleSheet("font-size:30px; font-weight:bold; color:#f85149; letter-spacing:2px;")
        elif self.remaining_secs <= 300:
            self.timer_label.setStyleSheet("font-size:30px; font-weight:bold; color:#f0883e; letter-spacing:2px;")
        if self.remaining_secs <= 0:
            self._exam_timer.stop(); self._submit_exam(auto=True)

    # ── MONITORING ───────────────────────────────────────────────────────────

    def _start_monitoring(self):
        self.cam_label.setText("Loading AI…")
        self.cam_monitor = CameraMonitor(camera_index=0)
        self.cam_monitor.frame_ready.connect(self._update_camera)
        self.cam_monitor.status_update.connect(self._update_ai_status)
        self.cam_monitor.violation_signal.connect(self._handle_violation)
        self.cam_monitor.init_done.connect(self._on_ai_ready)
        self.cam_monitor.intent_signal.connect(self._on_intent_silent)
        self.cam_monitor.prediction_signal.connect(self._on_prediction_silent)
        self.cam_monitor.invisible_signal.connect(self._on_invisible_silent)
        self.cam_monitor.start()

        self.audio_monitor = AudioMonitor()
        self.audio_monitor.audio_status.connect(self._update_audio_status)
        self.audio_monitor.violation_signal.connect(self._handle_violation)
        self.audio_monitor.start()

        self.screen_monitor = ScreenMonitor(target_window=self)
        self.screen_monitor.focus_status.connect(self._update_focus_status)
        self.screen_monitor.violation_signal.connect(self._handle_violation)
        self.screen_monitor.start()

    def _stop_monitoring(self):
        for attr in ["cam_monitor", "audio_monitor", "screen_monitor"]:
            m = getattr(self, attr, None)
            if m:
                try: m.stop()
                except Exception: pass
                setattr(self, attr, None)

    @pyqtSlot(str)
    def _on_ai_ready(self, msg):
        self.face_dot.setText("● Camera"); self.face_dot.setStyleSheet(STATUS_OK)

    @pyqtSlot(QImage)
    def _update_camera(self, img):
        pix = QPixmap.fromImage(img).scaled(
            self.cam_label.width(), self.cam_label.height(),
            Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.cam_label.setPixmap(pix)

    @pyqtSlot(object)
    def _update_ai_status(self, s):
        face_ok = "detected" in str(s.get("face_status", "")).lower()
        self.face_dot.setText(f"● Camera{'  ✓' if face_ok else '  !'}")
        self.face_dot.setStyleSheet(STATUS_OK if face_ok else STATUS_WARN)

    @pyqtSlot(str, float)
    def _update_audio_status(self, status, rms):
        if self.cam_monitor and hasattr(self.cam_monitor, "invisible_detector") \
                and self.cam_monitor.invisible_detector:
            try:
                self.cam_monitor.invisible_detector.feed_audio(rms, "ALERT" in status)
            except Exception:
                pass
        ok = "ALERT" not in status
        self.audio_dot.setText(f"● Microphone{'  ✓' if ok else '  !'}")
        self.audio_dot.setStyleSheet(STATUS_OK if ok else STATUS_WARN)

    @pyqtSlot(bool)
    def _update_focus_status(self, has_focus):
        self.focus_dot.setText(f"● Window Focus{'  ✓' if has_focus else '  !'}")
        self.focus_dot.setStyleSheet(STATUS_OK if has_focus else STATUS_WARN)

    @pyqtSlot(str, str)
    def _handle_violation(self, vtype, details):
        if vtype.startswith("invisible_"):
            return
        log_violation(self.session_id, self.student["student_id"], vtype, details)
        self.violation_count += 1
        self.viol_badge.setText(f"⚠  Violations: {self.violation_count}")
        vcounts = get_violation_counts(self.session_id)
        score, level = self.risk_scorer.calculate(vcounts)
        self._current_risk_score = score
        self._current_risk_level = level

    @pyqtSlot(str, str, int, int)
    def _on_intent_silent(self, name, description, risk_boost, confidence):
        pass

    @pyqtSlot(str, float, str)
    def _on_prediction_silent(self, label, confidence, risk_level):
        pass

    @pyqtSlot(str, str, float, float)
    def _on_invisible_silent(self, cheat_type, description, confidence, risk_score):
        log_violation(
            self.session_id, self.student["student_id"],
            f"invisible_{cheat_type}",
            f"[Inferred] {description} (confidence={confidence:.0f}%)"
        )
        self.violation_count += 1
        self.viol_badge.setText(f"⚠  Violations: {self.violation_count}")

    # ── SUBMIT ───────────────────────────────────────────────────────────────

    def _submit_exam(self, auto=False):
        if self._submitted:
            return
        self._submitted = True
        self._save_current_answer()

        if not auto:
            ans = len(self.answers)
            unanswered = len(self.questions) - ans
            warn_text = (
                f"You have answered <b>{ans} of {len(self.questions)}</b> questions."
            )
            if unanswered > 0:
                warn_text += f"<br><br><span style='color:#f0883e'>⚠  {unanswered} question(s) unanswered.</span>"
            warn_text += "<br><br>Are you sure you want to submit?"

            box = QMessageBox(self)
            box.setWindowTitle("Submit Exam?")
            box.setText(warn_text)
            box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            box.setDefaultButton(QMessageBox.No)
            box.setStyleSheet("QLabel{color:#e6edf3;} QMessageBox{background:#161b22;}")
            if box.exec_() == QMessageBox.No:
                self._submitted = False
                return

        if self._exam_timer:
            self._exam_timer.stop()
        self._stop_monitoring()

        # Calculate score
        correct = 0
        for q in self.questions:
            ans = self.answers.get(q["id"])
            ok  = (ans == q["answer"]) if ans else False
            if ok: correct += 1
            save_answer(self.session_id, self.student["student_id"], q["id"], ans or "", ok)

        vcounts = get_violation_counts(self.session_id)
        risk_score, risk_level = self.risk_scorer.calculate(vcounts)
        score_pct = (correct / len(self.questions)) * 100
        end_session(self.session_id, score_pct, risk_score, risk_level)

        # Show beautiful result dialog
        dlg = ResultDialog(
            student        = self.student,
            questions      = self.questions,
            answers        = self.answers,
            violation_count= self.violation_count,
            risk_score     = risk_score,
            risk_level     = risk_level,
            parent         = self
        )
        dlg.exec_()
        self.close()

    def closeEvent(self, event):
        self._stop_monitoring(); event.accept()
