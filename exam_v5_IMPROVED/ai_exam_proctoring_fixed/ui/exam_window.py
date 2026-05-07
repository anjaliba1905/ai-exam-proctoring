# ui/exam_window.py  –  STUDENT Exam Window (v5 clean)
# Only shows: questions, timer, small camera preview, basic status dots.
# All AI panels (Risk Timeline, Intent, Predictions, Invisible) removed from here.
# All AI data is still computed and logged — just not shown to the student.

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QFrame, QRadioButton, QButtonGroup,
    QProgressBar, QMessageBox, QScrollArea, QSizePolicy
)
from PyQt5.QtCore import Qt, QTimer, pyqtSlot
from PyQt5.QtGui  import QFont, QPixmap, QImage, QColor

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
    border-radius:12px;
    padding:20px;
}
QLabel#questionNum  { color:#58a6ff; font-size:12px; font-weight:bold; }
QLabel#questionText { font-size:15px; color:#e6edf3; line-height:1.5; }
QLabel#timerLabel   { font-size:30px; font-weight:bold; color:#3fb950; letter-spacing:2px; }
QLabel#timerOk      { color:#3fb950; }
QLabel#timerWarn    { color:#f0883e; }
QLabel#timerDanger  { color:#f85149; }
QLabel#examTitle    { font-size:12px; color:#8b949e; font-style:italic; }
QLabel#statusDot    { font-size:11px; }
QRadioButton {
    font-size:14px; color:#c9d1d9;
    padding:10px 8px; spacing:10px;
    border:1px solid transparent;
    border-radius:8px;
}
QRadioButton:hover  { background:#161b22; border-color:#30363d; }
QRadioButton::indicator { width:18px; height:18px; border-radius:9px; border:2px solid #30363d; }
QRadioButton::indicator:checked { background:#58a6ff; border-color:#58a6ff; }
QPushButton#navBtn {
    background:#21262d; color:#c9d1d9;
    border:1px solid #30363d; border-radius:7px;
    padding:9px 18px; font-size:13px; min-width:90px;
}
QPushButton#navBtn:hover  { background:#30363d; }
QPushButton#navBtn:disabled { color:#484f58; }
QPushButton#submitBtn {
    background:#238636; color:white;
    border:none; border-radius:9px;
    padding:13px 28px; font-size:15px; font-weight:bold;
}
QPushButton#submitBtn:hover { background:#2ea043; }
QProgressBar {
    background:#21262d; border-radius:5px;
    height:10px; text-align:center;
    color:transparent;
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

        self.session_id       = start_session(student["student_id"])
        self.answers          = {}
        self.current_q        = 0
        self.risk_scorer      = RiskScorer()
        self.remaining_secs   = self.duration_minutes * 60
        self.violation_count  = 0
        self._current_risk_score = 0.0
        self._current_risk_level = "Low Risk"

        self.setWindowTitle(
            f"AI Exam  —  {student['name']}  [{student['student_id']}]"
        )
        self.setMinimumSize(980, 700)
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

        # ── LEFT Sidebar (narrow — status + camera only) ───────────────────
        sidebar = QFrame(); sidebar.setObjectName("sidebar"); sidebar.setFixedWidth(240)
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(14, 16, 14, 16)
        sl.setSpacing(8)

        # Student info
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

        # Duration badge
        dur_badge = QLabel(f"⏱  {self.duration_minutes} min  ·  {len(self.questions)} Questions")
        dur_badge.setStyleSheet(
            "background:#1f3a5f; color:#79c0ff; border-radius:6px;"
            " padding:6px 10px; font-size:11px;"
        )
        sl.addWidget(dur_badge)

        # Timer
        self.timer_label = QLabel(f"{self.duration_minutes:02d}:00")
        self.timer_label.setObjectName("timerLabel")
        self.timer_label.setAlignment(Qt.AlignCenter)
        sl.addWidget(self.timer_label)

        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(max(len(self.questions), 1))
        self.progress_bar.setValue(0)
        sl.addWidget(self.progress_bar)
        prog_lbl = QLabel("Questions answered")
        prog_lbl.setStyleSheet("color:#8b949e; font-size:10px;")
        sl.addWidget(prog_lbl)

        sl.addWidget(self._divider())

        # Camera preview — small, lets student know they're being watched
        cam_hdr = QLabel("📷  Live Camera")
        cam_hdr.setStyleSheet("font-weight:bold; font-size:11px; color:#8b949e;")
        sl.addWidget(cam_hdr)

        self.cam_label = QLabel("Initialising…")
        self.cam_label.setObjectName("camLabel")
        self.cam_label.setFixedSize(210, 158)
        self.cam_label.setAlignment(Qt.AlignCenter)
        self.cam_label.setStyleSheet("color:#484f58; font-size:11px; background:#0a0e14; border-radius:8px;")
        sl.addWidget(self.cam_label)

        # Simple status dots — face/audio/focus only, no AI details shown to student
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

        # Proctoring notice
        notice = QLabel("🔒  This exam is monitored by AI proctoring.")
        notice.setWordWrap(True)
        notice.setStyleSheet("color:#484f58; font-size:10px; text-align:center;")
        notice.setAlignment(Qt.AlignCenter)
        sl.addWidget(notice)

        root.addWidget(sidebar)

        # ── MAIN: Question area ────────────────────────────────────────────
        main_area = QWidget()
        ml = QVBoxLayout(main_area)
        ml.setContentsMargins(28, 24, 28, 18)
        ml.setSpacing(16)

        # Question card
        qcard = QFrame(); qcard.setObjectName("questionCard")
        qcl   = QVBoxLayout(qcard); qcl.setSpacing(14)

        self.q_num_lbl = QLabel(f"Question 1 of {len(self.questions)}")
        self.q_num_lbl.setObjectName("questionNum")
        qcl.addWidget(self.q_num_lbl)

        self.q_text_lbl = QLabel()
        self.q_text_lbl.setObjectName("questionText")
        self.q_text_lbl.setWordWrap(True)
        qcl.addWidget(self.q_text_lbl)

        div2 = QFrame(); div2.setFrameShape(QFrame.HLine)
        div2.setStyleSheet("border-color:#30363d; margin:4px 0;")
        qcl.addWidget(div2)

        self.option_group  = QButtonGroup()
        self.option_radios = {}
        for opt in ["A", "B", "C", "D"]:
            rb = QRadioButton()
            self.option_radios[opt] = rb
            self.option_group.addButton(rb)
            qcl.addWidget(rb)

        ml.addWidget(qcard, stretch=1)

        # Question grid + navigation
        nav = QHBoxLayout()

        self.prev_btn = QPushButton("← Previous"); self.prev_btn.setObjectName("navBtn")
        self.prev_btn.clicked.connect(self._prev_question)
        nav.addWidget(self.prev_btn)
        nav.addSpacing(8)

        # Scrollable question grid
        grid_scroll = QScrollArea()
        grid_scroll.setWidgetResizable(True)
        grid_scroll.setFixedHeight(44)
        grid_inner  = QWidget()
        grid_layout = QHBoxLayout(grid_inner)
        grid_layout.setSpacing(4); grid_layout.setContentsMargins(0, 0, 0, 0)
        self.q_grid_btns = []
        for i in range(len(self.questions)):
            btn = QPushButton(str(i + 1))
            btn.setFixedSize(34, 34)
            btn.setStyleSheet(
                "QPushButton{background:#21262d;color:#8b949e;border:1px solid #30363d;"
                "border-radius:5px;font-size:11px;}"
                "QPushButton:hover{background:#30363d;}"
            )
            btn.clicked.connect(lambda _, idx=i: self._jump_to(idx))
            self.q_grid_btns.append(btn)
            grid_layout.addWidget(btn)
        grid_layout.addStretch()
        grid_scroll.setWidget(grid_inner)
        nav.addWidget(grid_scroll, stretch=1)
        nav.addSpacing(8)

        self.next_btn = QPushButton("Next →"); self.next_btn.setObjectName("navBtn")
        self.next_btn.clicked.connect(self._next_question)
        nav.addWidget(self.next_btn)
        ml.addLayout(nav)

        # Submit row
        sub_row = QHBoxLayout()
        sub_row.addStretch()
        self.submit_btn = QPushButton("✔  Submit Exam")
        self.submit_btn.setObjectName("submitBtn")
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
        self.q_num_lbl.setText(f"Question {self.current_q + 1} of {len(self.questions)}")
        self.q_text_lbl.setText(q["question"])
        opts = {"A": q["option_a"], "B": q["option_b"],
                "C": q["option_c"], "D": q["option_d"]}
        for letter, text in opts.items():
            self.option_radios[letter].setText(f"  {letter}.   {text}")
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
                self.answers[q["id"]] = letter; return

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
        for i, btn in enumerate(self.q_grid_btns):
            qid = self.questions[i]["id"]
            if i == self.current_q:
                btn.setStyleSheet(
                    "QPushButton{background:#1f6feb;color:white;border:none;border-radius:5px;font-size:11px;}")
            elif qid in self.answers:
                btn.setStyleSheet(
                    "QPushButton{background:#238636;color:white;border:none;border-radius:5px;font-size:11px;}")
            else:
                btn.setStyleSheet(
                    "QPushButton{background:#21262d;color:#8b949e;border:1px solid #30363d;"
                    "border-radius:5px;font-size:11px;}")
        self.progress_bar.setValue(len(self.answers))

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
        # Advanced signals connected but output goes to DB only, not shown to student
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
        self.face_dot.setText("● Camera")
        self.face_dot.setStyleSheet(STATUS_OK)

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

    # Advanced signals → log silently to DB, nothing shown to student
    @pyqtSlot(str, str, int, int)
    def _on_intent_silent(self, name, description, risk_boost, confidence):
        pass   # Intent data is displayed in teacher dashboard only

    @pyqtSlot(str, float, str)
    def _on_prediction_silent(self, label, confidence, risk_level):
        pass   # Prediction data is displayed in teacher dashboard only

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
            reply = QMessageBox.question(
                self, "Submit Exam",
                f"You have answered {ans} of {len(self.questions)} questions.\n\nSubmit now?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.No:
                self._submitted = False; return

        if self._exam_timer:
            self._exam_timer.stop()
        self._stop_monitoring()

        correct = 0
        for q in self.questions:
            ans = self.answers.get(q["id"])
            ok  = (ans == q["answer"]) if ans else False
            if ok: correct += 1
            save_answer(self.session_id, self.student["student_id"], q["id"], ans or "", ok)

        vcounts    = get_violation_counts(self.session_id)
        risk_score, risk_level = self.risk_scorer.calculate(vcounts)
        score_pct  = (correct / len(self.questions)) * 100
        end_session(self.session_id, score_pct, risk_score, risk_level)

        rc = {"Low Risk":"#3fb950","Medium Risk":"#f0883e","High Risk":"#f85149"}.get(risk_level,"white")
        msg = QMessageBox(self)
        msg.setWindowTitle("Exam Submitted")
        msg.setText(
            f"<b>Exam Complete!</b><br><br>"
            f"Score: <b>{correct}/{len(self.questions)} ({score_pct:.0f}%)</b><br>"
            f"Violations logged: <b>{self.violation_count}</b><br>"
            f"<span style='color:{rc}'>Results will be reviewed by your teacher.</span>"
        )
        msg.setStyleSheet("QLabel{color:white;} QMessageBox{background:#161b22;}")
        msg.exec_()
        self.close()

    def closeEvent(self, event):
        self._stop_monitoring(); event.accept()
