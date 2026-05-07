# dashboard/teacher_dashboard.py  –  Teacher Dashboard (v5)
# Layout: left panel = student list ranked by risk | right panel = selected student detail
# Detail panel shows: Live Risk Timeline, Intent, Predictions, Invisible Cheat, Violations

import sys, os, csv
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QTableWidget, QTableWidgetItem,
    QTabWidget, QLineEdit, QMessageBox, QHeaderView,
    QSplitter, QScrollArea, QFileDialog, QListWidget, QListWidgetItem
)
from PyQt5.QtCore  import Qt, QTimer, pyqtSignal
from PyQt5.QtGui   import QFont, QColor

from database import (get_all_students, add_student, delete_student,
                      get_all_sessions, get_violations, get_violation_counts,
                      init_exam_config)
from ai_modules.risk_scoring import RiskScorer
from dashboard.exam_config_tab import ExamConfigTab
from ui.risk_timeline_widget import RiskTimelineWidget

STYLE = """
QMainWindow, QWidget {
    background:#0d1117; color:#e6edf3;
    font-family:'Segoe UI', Arial, sans-serif;
}
QTabWidget::pane  { border:1px solid #30363d; background:#161b22; border-radius:8px; }
QTabBar::tab      { background:#21262d; color:#8b949e; padding:10px 20px;
                    border-radius:6px 6px 0 0; margin-right:3px; font-size:13px; }
QTabBar::tab:selected { background:#161b22; color:#58a6ff;
                         border-bottom:2px solid #58a6ff; font-weight:bold; }
QTabBar::tab:hover    { background:#30363d; }
QTableWidget          { background:#161b22; border:1px solid #30363d;
                        border-radius:8px; gridline-color:#21262d; }
QTableWidget::item    { padding:7px; }
QTableWidget::item:selected { background:#1f6feb; color:white; }
QHeaderView::section  { background:#21262d; color:#8b949e; padding:9px;
                        border:none; font-weight:bold; font-size:12px; }
QListWidget           { background:#111318; border:none; outline:none; }
QListWidget::item     { border-bottom:1px solid #21262d; padding:0; }
QListWidget::item:selected { background:#1c2128; }
QLineEdit             { background:#0d1117; border:1px solid #30363d;
                        border-radius:6px; padding:9px 12px; color:#e6edf3; }
QLineEdit:focus       { border-color:#58a6ff; }
QPushButton#addBtn    { background:#238636; color:white; border:none;
                        border-radius:7px; padding:10px 18px; font-size:13px; font-weight:bold; }
QPushButton#addBtn:hover   { background:#2ea043; }
QPushButton#delBtn         { background:#da3633; color:white; border:none;
                              border-radius:6px; padding:6px 12px; font-size:12px; }
QPushButton#delBtn:hover   { background:#f85149; }
QPushButton#refreshBtn     { background:#21262d; color:#c9d1d9;
                              border:1px solid #30363d; border-radius:6px;
                              padding:8px 16px; font-size:12px; }
QPushButton#refreshBtn:hover { background:#30363d; color:#58a6ff; }
QPushButton#exportBtn      { background:#1f6feb; color:white; border:none;
                              border-radius:6px; padding:8px 16px; font-size:12px; }
QPushButton#exportBtn:hover  { background:#388bfd; }
QFrame#statCard            { background:#161b22; border:1px solid #30363d;
                              border-radius:10px; padding:14px; min-width:130px; }
QFrame#detailCard          { background:#161b22; border:1px solid #30363d;
                              border-radius:10px; padding:12px; }
QSplitter::handle          { background:#21262d; width:2px; }
"""

RISK_COLORS = {
    "Low Risk":    ("#3fb950", "#0d2a13"),
    "Medium Risk": ("#f0883e", "#2d1b08"),
    "High Risk":   ("#f85149", "#2d0d0c"),
}
VIOL_COLORS = {
    "phone_detected": "#f85149",
    "multiple_faces": "#f0883e",
    "no_face":        "#e3b341",
    "gaze_away":      "#79c0ff",
    "tab_switch":     "#d2a8ff",
    "audio_alert":    "#ff7b72",
}


class StudentListItem(QFrame):
    """Custom widget for each student row in the monitoring list."""

    clicked = pyqtSignal(str)   # student_id

    def __init__(self, student_id, name, dept, risk_score, risk_level, viol_count, parent=None):
        super().__init__(parent)
        self.student_id = student_id
        self.setFixedHeight(68)
        self.setCursor(Qt.PointingHandCursor)

        rc, rb = RISK_COLORS.get(risk_level, ("#e6edf3", "#161b22"))
        self.setStyleSheet(
            f"QFrame{{background:#111318; border-left:3px solid {rc}; padding:0;}}"
            f"QFrame:hover{{background:#1c2128;}}"
        )

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(10)

        # Risk badge
        badge = QLabel(f"{risk_score:.0f}")
        badge.setFixedSize(42, 42)
        badge.setAlignment(Qt.AlignCenter)
        badge.setFont(QFont("Segoe UI", 13, QFont.Bold))
        badge.setStyleSheet(
            f"background:{rb}; color:{rc}; border-radius:21px; border:1px solid {rc}55;"
        )
        lay.addWidget(badge)

        # Name + dept
        info = QVBoxLayout(); info.setSpacing(1)
        name_lbl = QLabel(name)
        name_lbl.setFont(QFont("Segoe UI", 12, QFont.Bold))
        name_lbl.setStyleSheet("color:#e6edf3;")
        dept_lbl = QLabel(f"{student_id}  ·  {dept}")
        dept_lbl.setStyleSheet("color:#8b949e; font-size:11px;")
        info.addWidget(name_lbl)
        info.addWidget(dept_lbl)
        lay.addLayout(info, stretch=1)

        # Violation count
        if viol_count > 0:
            vc_lbl = QLabel(f"⚠ {viol_count}")
            vc_lbl.setStyleSheet(
                f"color:{rc}; font-size:12px; font-weight:bold;"
                f" background:{rb}; border-radius:5px; padding:3px 7px;"
            )
            lay.addWidget(vc_lbl)

    def mousePressEvent(self, _event):
        self.clicked.emit(self.student_id)


class TeacherDashboard(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Teacher Dashboard  —  AI Exam Proctoring")
        self.setMinimumSize(1440, 860)
        self.setStyleSheet(STYLE)
        self.risk_scorer      = RiskScorer()
        self._selected_student = None   # student_id of currently selected student
        self._sessions_cache  = []
        init_exam_config()
        self._build_ui()
        self._refresh_all()

        self._auto_timer = QTimer(self)
        self._auto_timer.timeout.connect(self._refresh_all)
        self._auto_timer.start(12_000)  # refresh every 12 s

    # ── MAIN UI BUILD ─────────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # ── Header ─────────────────────────────────────────────────────────
        hdr = QHBoxLayout()
        title = QLabel("🎓  Teacher Dashboard")
        title.setFont(QFont("Segoe UI", 20, QFont.Bold))
        title.setStyleSheet("color:#58a6ff;")
        hdr.addWidget(title)
        hdr.addStretch()
        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("color:#3fb950; font-size:12px;")
        hdr.addWidget(self._status_lbl)
        ref_btn = QPushButton("⟳  Refresh")
        ref_btn.setObjectName("refreshBtn")
        ref_btn.clicked.connect(self._refresh_all)
        hdr.addWidget(ref_btn)
        root.addLayout(hdr)

        # ── Stat cards ─────────────────────────────────────────────────────
        sr = QHBoxLayout(); sr.setSpacing(10)
        self._sc_students = self._stat_card("0", "Students",       "#58a6ff")
        self._sc_sessions = self._stat_card("0", "Sessions",       "#3fb950")
        self._sc_viol     = self._stat_card("0", "Violations",     "#f0883e")
        self._sc_high     = self._stat_card("0", "High Risk",      "#f85149")
        self._sc_active   = self._stat_card("0", "Active Exams",   "#a371f7")
        for card, _, _ in [self._sc_students, self._sc_sessions,
                            self._sc_viol, self._sc_high, self._sc_active]:
            sr.addWidget(card)
        sr.addStretch()
        root.addLayout(sr)

        # ── Tabs ───────────────────────────────────────────────────────────
        self.tabs = QTabWidget()
        self.tabs.addTab(self._monitoring_tab(),  "  📡 Live Monitoring  ")
        self.tabs.addTab(self._students_tab(),    "  👥 Students  ")
        self.tabs.addTab(self._sessions_tab(),    "  📋 Sessions  ")
        self.tabs.addTab(self._violations_tab(),  "  ⚠ Violations  ")
        self.config_tab = ExamConfigTab()
        self.config_tab.config_changed.connect(self._on_config_saved)
        self.tabs.addTab(self.config_tab,         "  ⚙ Exam Config  ")
        root.addWidget(self.tabs)

    def _stat_card(self, value, label, color):
        card = QFrame(); card.setObjectName("statCard")
        cl   = QVBoxLayout(card)
        num  = QLabel(value)
        num.setStyleSheet(f"font-size:28px; font-weight:bold; color:{color};")
        lbl  = QLabel(label)
        lbl.setStyleSheet("font-size:11px; color:#8b949e;")
        cl.addWidget(num); cl.addWidget(lbl)
        return card, num, lbl

    # ── MONITORING TAB ────────────────────────────────────────────────────────

    def _monitoring_tab(self):
        """
        Split view:
          LEFT  – student list ranked by risk (highest first), colour-coded
          RIGHT – detail panel for selected student (timeline + AI panels + violations)
        """
        w = QWidget()
        lay = QHBoxLayout(w); lay.setContentsMargins(0, 8, 0, 0); lay.setSpacing(0)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(2)

        # ── Left: student list ─────────────────────────────────────────────
        left = QWidget(); left.setMinimumWidth(280); left.setMaximumWidth(360)
        ll = QVBoxLayout(left); ll.setContentsMargins(8, 0, 0, 0); ll.setSpacing(6)

        list_hdr = QLabel("Students  (ranked by risk)")
        list_hdr.setStyleSheet("color:#8b949e; font-size:11px; font-weight:bold; padding:4px 0;")
        ll.addWidget(list_hdr)

        self._student_list_scroll = QScrollArea()
        self._student_list_scroll.setWidgetResizable(True)
        self._student_list_scroll.setStyleSheet("QScrollArea{border:none;}")
        self._student_list_inner  = QWidget()
        self._student_list_layout = QVBoxLayout(self._student_list_inner)
        self._student_list_layout.setContentsMargins(0, 0, 0, 0)
        self._student_list_layout.setSpacing(1)
        self._student_list_layout.addStretch()
        self._student_list_scroll.setWidget(self._student_list_inner)
        ll.addWidget(self._student_list_scroll)
        splitter.addWidget(left)

        # ── Right: detail panel ────────────────────────────────────────────
        right = QWidget()
        rl = QVBoxLayout(right); rl.setContentsMargins(12, 0, 8, 0); rl.setSpacing(10)

        self._detail_placeholder = QLabel(
            "👈  Select a student from the list to view their monitoring detail"
        )
        self._detail_placeholder.setAlignment(Qt.AlignCenter)
        self._detail_placeholder.setStyleSheet("color:#484f58; font-size:14px;")
        rl.addWidget(self._detail_placeholder)

        # Selected student header
        self._detail_header = QFrame()
        self._detail_header.setStyleSheet(
            "background:#161b22; border-radius:10px; padding:10px;"
        )
        dhl = QHBoxLayout(self._detail_header)
        self._detail_name   = QLabel("—")
        self._detail_name.setFont(QFont("Segoe UI", 16, QFont.Bold))
        self._detail_risk   = QLabel("")
        self._detail_risk.setFont(QFont("Segoe UI", 14, QFont.Bold))
        dhl.addWidget(self._detail_name)
        dhl.addStretch()
        dhl.addWidget(self._detail_risk)
        self._detail_header.hide()
        rl.addWidget(self._detail_header)

        # AI panels row (Timeline + Intent/Predictions/Invisible)
        ai_row = QHBoxLayout(); ai_row.setSpacing(10)

        # Risk Timeline
        tl_card = QFrame(); tl_card.setObjectName("detailCard")
        tlc = QVBoxLayout(tl_card); tlc.setContentsMargins(8, 8, 8, 8)
        self._teacher_timeline = RiskTimelineWidget()
        self._teacher_timeline.setMinimumHeight(220)
        tlc.addWidget(self._teacher_timeline)
        ai_row.addWidget(tl_card, stretch=3)

        # Right AI panels (Intent + Predictions + Invisible)
        right_ai = QVBoxLayout(); right_ai.setSpacing(8)

        # Intent Detection
        intent_card = QFrame(); intent_card.setObjectName("detailCard")
        ic = QVBoxLayout(intent_card); ic.setSpacing(4)
        ic.addWidget(self._panel_header("🧠  Intent Detection"))
        self._teacher_intent_lbl = QLabel("No suspicious intent detected")
        self._teacher_intent_lbl.setStyleSheet("color:#3fb950; font-size:11px;")
        self._teacher_intent_lbl.setWordWrap(True)
        ic.addWidget(self._teacher_intent_lbl)
        right_ai.addWidget(intent_card)

        # Predictions
        pred_card = QFrame(); pred_card.setObjectName("detailCard")
        pc = QVBoxLayout(pred_card); pc.setSpacing(4)
        pc.addWidget(self._panel_header("🔮  Behavior Forecast"))
        self._teacher_pred_lbl = QLabel("No high-risk predictions")
        self._teacher_pred_lbl.setStyleSheet("color:#3fb950; font-size:11px;")
        self._teacher_pred_lbl.setWordWrap(True)
        pc.addWidget(self._teacher_pred_lbl)
        right_ai.addWidget(pred_card)

        # Invisible Cheat
        inv_card = QFrame(); inv_card.setObjectName("detailCard")
        vc = QVBoxLayout(inv_card); vc.setSpacing(4)
        vc.addWidget(self._panel_header("👻  Invisible Cheat Radar"))
        self._teacher_inv_lbl = QLabel("No hidden cheating detected")
        self._teacher_inv_lbl.setStyleSheet("color:#3fb950; font-size:11px;")
        self._teacher_inv_lbl.setWordWrap(True)
        vc.addWidget(self._teacher_inv_lbl)
        right_ai.addWidget(inv_card)

        ai_row.addLayout(right_ai, stretch=2)

        self._ai_row_widget = QWidget()
        self._ai_row_widget.setLayout(ai_row)
        self._ai_row_widget.hide()
        rl.addWidget(self._ai_row_widget)

        # Violations for selected student
        viol_hdr = QHBoxLayout()
        self._sel_viol_hdr = QLabel("Recent Violations")
        self._sel_viol_hdr.setStyleSheet(
            "color:#e6edf3; font-size:12px; font-weight:bold;"
        )
        viol_hdr.addWidget(self._sel_viol_hdr)
        viol_hdr.addStretch()
        self._sel_viol_hdr.hide()
        rl.addLayout(viol_hdr)

        self._sel_viol_table = self._make_table(
            ["Timestamp", "Violation Type", "Details"])
        self._sel_viol_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._sel_viol_table.setMaximumHeight(200)
        self._sel_viol_table.hide()
        rl.addWidget(self._sel_viol_table)

        rl.addStretch()
        splitter.addWidget(right)
        splitter.setSizes([300, 900])
        lay.addWidget(splitter)
        return w

    @staticmethod
    def _panel_header(text):
        lbl = QLabel(text)
        lbl.setStyleSheet("color:#e6edf3; font-size:11px; font-weight:bold;")
        return lbl

    # ── STUDENTS TAB ──────────────────────────────────────────────────────────

    def _students_tab(self):
        w = QWidget()
        l = QVBoxLayout(w); l.setContentsMargins(12, 12, 12, 12); l.setSpacing(12)

        form = QFrame()
        form.setStyleSheet(
            "QFrame{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px;}"
        )
        fl = QVBoxLayout(form)
        fl.addWidget(QLabel("➕  Add New Student",
                            styleSheet="font-weight:bold;font-size:14px;color:#58a6ff;"))
        row = QHBoxLayout()
        self.add_sid   = QLineEdit(); self.add_sid.setPlaceholderText("Student ID  (e.g. STU010)")
        self.add_name  = QLineEdit(); self.add_name.setPlaceholderText("Full Name")
        self.add_email = QLineEdit(); self.add_email.setPlaceholderText("Email Address")
        self.add_dept  = QLineEdit(); self.add_dept.setPlaceholderText("Department")
        self.add_pwd   = QLineEdit(); self.add_pwd.setPlaceholderText("Password")
        self.add_pwd.setEchoMode(QLineEdit.Password)
        for f in [self.add_sid, self.add_name, self.add_email, self.add_dept, self.add_pwd]:
            row.addWidget(f)
        fl.addLayout(row)
        add_btn = QPushButton("Add Student"); add_btn.setObjectName("addBtn")
        add_btn.clicked.connect(self._add_student)
        fl.addWidget(add_btn, alignment=Qt.AlignLeft)
        l.addWidget(form)

        self.student_table = self._make_table(
            ["ID", "Student ID", "Name", "Email", "Department", "Created", "Action"])
        self.student_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        l.addWidget(self.student_table)
        return w

    # ── SESSIONS TAB ──────────────────────────────────────────────────────────

    def _sessions_tab(self):
        w = QWidget()
        l = QVBoxLayout(w); l.setContentsMargins(12, 12, 12, 12); l.setSpacing(6)
        tb = QHBoxLayout(); tb.addStretch()
        exp = QPushButton("⬇  Export CSV"); exp.setObjectName("exportBtn")
        exp.clicked.connect(self._export_sessions_csv)
        tb.addWidget(exp); l.addLayout(tb)
        self.session_table = self._make_table([
            "Session ID", "Student ID", "Name", "Dept",
            "Start", "End", "Score %", "Violations",
            "Risk Score", "Risk Level", "Status"
        ])
        self.session_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        l.addWidget(self.session_table)
        return w

    # ── VIOLATIONS TAB ────────────────────────────────────────────────────────

    def _violations_tab(self):
        w = QWidget()
        l = QVBoxLayout(w); l.setContentsMargins(12, 12, 12, 12); l.setSpacing(8)
        fr = QHBoxLayout()
        fr.addWidget(QLabel("Filter by Student ID:"))
        self.viol_filter = QLineEdit(); self.viol_filter.setPlaceholderText("Leave blank for all")
        self.viol_filter.setFixedWidth(200); fr.addWidget(self.viol_filter)
        fb = QPushButton("Apply"); fb.setObjectName("refreshBtn")
        fb.clicked.connect(self._load_violations); fr.addWidget(fb)
        fr.addStretch()
        exp2 = QPushButton("⬇  Export CSV"); exp2.setObjectName("exportBtn")
        exp2.clicked.connect(self._export_violations_csv); fr.addWidget(exp2)
        l.addLayout(fr)
        self.violation_table = self._make_table(
            ["ID", "Session", "Student ID", "Timestamp", "Violation Type", "Details"])
        self.violation_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        l.addWidget(self.violation_table)
        return w

    @staticmethod
    def _make_table(headers):
        t = QTableWidget()
        t.setColumnCount(len(headers)); t.setHorizontalHeaderLabels(headers)
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        t.setSelectionBehavior(QTableWidget.SelectRows)
        t.verticalHeader().setVisible(False)
        t.setAlternatingRowColors(True)
        t.setStyleSheet("QTableWidget{alternate-background-color:#0f1923;}")
        return t

    # ── REFRESH ───────────────────────────────────────────────────────────────

    def _refresh_all(self):
        self._sessions_cache = get_all_sessions()
        self._load_students()
        self._load_monitoring_list()
        self._load_sessions()
        self._load_violations()
        if self._selected_student:
            self._show_student_detail(self._selected_student)
        self._status_lbl.setText("✓  Refreshed")
        QTimer.singleShot(2500, lambda: self._status_lbl.setText(""))

    def _on_config_saved(self):
        self.setWindowTitle("Teacher Dashboard  —  ✅ Config Saved")
        QTimer.singleShot(3000, lambda:
            self.setWindowTitle("Teacher Dashboard  —  AI Exam Proctoring"))

    # ── MONITORING LIST ───────────────────────────────────────────────────────

    def _load_monitoring_list(self):
        """Rebuild the left-panel student list, sorted highest risk first."""
        # Clear existing items (keep the stretch)
        while self._student_list_layout.count() > 1:
            item = self._student_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        students = get_all_students()
        ranked   = []
        active_count = 0

        for s in students:
            # Find most recent session
            sessions = [sx for sx in self._sessions_cache
                        if sx["student_id"] == s["student_id"]]
            if not sessions:
                ranked.append((s, 0.0, "Low Risk", 0, False))
                continue
            latest = max(sessions, key=lambda x: x["id"])
            vcounts = get_violation_counts(latest["id"])
            vt      = sum(vcounts.values())
            score, level = self.risk_scorer.calculate(vcounts)
            is_active = (latest.get("status") == "active")
            if is_active:
                active_count += 1
            ranked.append((s, score, level, vt, is_active))

        # Sort: active first, then by risk score desc
        ranked.sort(key=lambda x: (not x[4], -x[1]))
        self._sc_active[1].setText(str(active_count))

        for s, score, level, vt, is_active in ranked:
            item_widget = StudentListItem(
                s["student_id"], s["name"],
                s.get("department", "—"),
                score, level, vt
            )
            item_widget.clicked.connect(self._show_student_detail)
            self._student_list_layout.insertWidget(
                self._student_list_layout.count() - 1,  # before stretch
                item_widget
            )

    # ── DETAIL PANEL ──────────────────────────────────────────────────────────

    def _show_student_detail(self, student_id: str):
        self._selected_student = student_id

        # Find student info
        students = get_all_students()
        stu = next((s for s in students if s["student_id"] == student_id), None)
        if not stu:
            return

        # Find sessions for this student
        sessions = [s for s in self._sessions_cache
                    if s["student_id"] == student_id]
        if not sessions:
            self._detail_placeholder.show()
            self._detail_header.hide()
            self._ai_row_widget.hide()
            self._sel_viol_hdr.hide()
            self._sel_viol_table.hide()
            return

        latest = max(sessions, key=lambda x: x["id"])
        vcounts = get_violation_counts(latest["id"])
        score, level = self.risk_scorer.calculate(vcounts)
        vt = sum(vcounts.values())

        rc, rb = RISK_COLORS.get(level, ("#e6edf3", "#161b22"))

        # Show header
        self._detail_placeholder.hide()
        self._detail_name.setText(f"  {stu['name']}  —  {student_id}")
        self._detail_risk.setText(f"{score:.0f}/100  {level}")
        self._detail_risk.setStyleSheet(f"color:{rc}; font-size:14px; font-weight:bold;")
        self._detail_header.setStyleSheet(
            f"background:{rb}; border-left:4px solid {rc}; border-radius:10px; padding:10px;"
        )
        self._detail_header.show()

        # Risk timeline — push current score
        self._teacher_timeline.update_risk(score, level)

        # Populate AI panels from violation data
        intent_lines, pred_lines, inv_lines = [], [], []
        viols = get_violations(student_id=student_id)
        for v in viols:
            vtype = v["violation_type"]
            if vtype.startswith("invisible_"):
                inv_lines.append(
                    f"<span style='color:#a371f7'>👻 {vtype.replace('invisible_','')}</span>"
                    f"  <span style='color:#8b949e; font-size:10px;'>{v.get('details','')[:60]}</span>"
                )
            elif vtype in ("gaze_away", "tab_switch"):
                intent_lines.append(
                    f"<span style='color:#f0883e'>🎯 {vtype}</span>"
                    f"  <span style='color:#8b949e; font-size:10px;'>{v.get('details','')[:60]}</span>"
                )

        self._teacher_intent_lbl.setText(
            "<br>".join(intent_lines[-3:]) if intent_lines
            else "No suspicious intent detected"
        )
        self._teacher_intent_lbl.setStyleSheet(
            "font-size:11px;" if intent_lines else "color:#3fb950; font-size:11px;"
        )

        risk_trend = score - (latest.get("risk_score") or 0)
        if score > 60:
            pred_lines.append(
                f"<span style='color:#f85149'>🔮 High violation rate — intervention recommended</span>"
            )
        elif score > 35:
            pred_lines.append(
                f"<span style='color:#f0883e'>🔮 Medium risk — monitor closely</span>"
            )
        self._teacher_pred_lbl.setText(
            "<br>".join(pred_lines) if pred_lines else "No high-risk predictions"
        )
        self._teacher_pred_lbl.setStyleSheet(
            "font-size:11px;" if pred_lines else "color:#3fb950; font-size:11px;"
        )

        self._teacher_inv_lbl.setText(
            "<br>".join(inv_lines[-3:]) if inv_lines
            else "No hidden cheating detected"
        )
        self._teacher_inv_lbl.setStyleSheet(
            "font-size:11px;" if inv_lines else "color:#3fb950; font-size:11px;"
        )

        # Violations table
        all_viols = get_violations(student_id=student_id)
        recent    = all_viols[-20:]  # last 20
        t = self._sel_viol_table; t.setRowCount(0)
        for v in reversed(recent):
            r = t.rowCount(); t.insertRow(r)
            vtype = v["violation_type"]
            color = VIOL_COLORS.get(vtype.replace("invisible_",""), "#a371f7"
                                    if vtype.startswith("invisible_") else "#e6edf3")
            for col, val in enumerate([
                str(v["timestamp"])[:19], vtype, v.get("details","")[:80]
            ]):
                item = QTableWidgetItem(val)
                if col == 1:
                    item.setForeground(QColor(color))
                    item.setFont(QFont("Segoe UI", 10, QFont.Bold))
                t.setItem(r, col, item)

        self._ai_row_widget.show()
        self._sel_viol_hdr.setText(
            f"Recent Violations  ({len(all_viols)} total)"
        )
        self._sel_viol_hdr.show()
        self._sel_viol_table.show()

    # ── DATA LOADERS ──────────────────────────────────────────────────────────

    def _load_students(self):
        students = get_all_students()
        t = self.student_table; t.setRowCount(0)
        for s in students:
            r = t.rowCount(); t.insertRow(r)
            for col, val in enumerate([
                str(s["id"]), s["student_id"], s["name"],
                s["email"], s.get("department",""),
                str(s.get("created_at",""))[:10]
            ]):
                t.setItem(r, col, QTableWidgetItem(val))
            del_btn = QPushButton("Delete"); del_btn.setObjectName("delBtn")
            del_btn.clicked.connect(
                lambda _, sid=s["student_id"]: self._delete_student(sid)
            )
            t.setCellWidget(r, 6, del_btn)
        self._sc_students[1].setText(str(len(students)))

    def _load_sessions(self):
        sessions = self._sessions_cache
        t = self.session_table; t.setRowCount(0)
        high_risk = total_viol = 0
        for s in sessions:
            vcounts = get_violation_counts(s["id"])
            vt = sum(vcounts.values()); total_viol += vt
            score, level = self.risk_scorer.calculate(vcounts)
            if level == "High Risk": high_risk += 1
            r = t.rowCount(); t.insertRow(r)
            vals = [
                str(s["id"]), s["student_id"], s.get("name",""), s.get("department",""),
                str(s.get("start_time",""))[:19],
                str(s.get("end_time","") or "Active")[:19],
                f"{s.get('score',0):.1f}%", str(vt),
                f"{score:.0f}/100", level, s.get("status","").capitalize()
            ]
            for col, val in enumerate(vals):
                item = QTableWidgetItem(val)
                if col == 9:
                    rc, rb = RISK_COLORS.get(level, ("#e6edf3","#161b22"))
                    item.setForeground(QColor(rc)); item.setBackground(QColor(rb))
                    item.setFont(QFont("Segoe UI", 10, QFont.Bold))
                t.setItem(r, col, item)
        self._sc_sessions[1].setText(str(len(sessions)))
        self._sc_viol[1].setText(str(total_viol))
        self._sc_high[1].setText(str(high_risk))

    def _load_violations(self):
        sid   = self.viol_filter.text().strip() or None
        viols = get_violations(student_id=sid)
        t = self.violation_table; t.setRowCount(0)
        for v in viols:
            r = t.rowCount(); t.insertRow(r)
            vtype = v["violation_type"]
            color = VIOL_COLORS.get(vtype.replace("invisible_",""),
                                    "#a371f7" if vtype.startswith("invisible_") else "#e6edf3")
            for col, val in enumerate([
                str(v["id"]), str(v["session_id"]), v["student_id"],
                str(v["timestamp"])[:19], vtype, v.get("details","")
            ]):
                item = QTableWidgetItem(val)
                if col == 4:
                    item.setForeground(QColor(color))
                    item.setFont(QFont("Segoe UI", 10, QFont.Bold))
                t.setItem(r, col, item)

    # ── EXPORT ────────────────────────────────────────────────────────────────

    def _export_sessions_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Sessions", "sessions.csv", "CSV (*.csv)")
        if not path: return
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["Session ID","Student ID","Name","Dept","Start","End",
                             "Score%","Violations","Risk","Level","Status"])
                for s in self._sessions_cache:
                    vc = get_violation_counts(s["id"])
                    vt = sum(vc.values())
                    rs, rl = self.risk_scorer.calculate(vc)
                    w.writerow([s["id"], s["student_id"], s.get("name",""),
                                 s.get("department",""),
                                 str(s.get("start_time",""))[:19],
                                 str(s.get("end_time","") or "Active")[:19],
                                 f"{s.get('score',0):.1f}", vt,
                                 f"{rs:.0f}", rl, s.get("status","").capitalize()])
            QMessageBox.information(self, "Export", f"Saved:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))

    def _export_violations_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Violations", "violations.csv", "CSV (*.csv)")
        if not path: return
        try:
            sid = self.viol_filter.text().strip() or None
            viols = get_violations(student_id=sid)
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["ID","Session ID","Student ID","Timestamp","Type","Details"])
                for v in viols:
                    w.writerow([v["id"], v["session_id"], v["student_id"],
                                 str(v["timestamp"])[:19], v["violation_type"],
                                 v.get("details","")])
            QMessageBox.information(self, "Export", f"Saved:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def _add_student(self):
        sid, name = self.add_sid.text().strip(), self.add_name.text().strip()
        email, dept = self.add_email.text().strip(), self.add_dept.text().strip()
        pwd = self.add_pwd.text().strip()
        if not all([sid, name, email, pwd]):
            QMessageBox.warning(self, "Missing Fields",
                "Student ID, Name, Email and Password are required.")
            return
        ok, msg = add_student(sid, name, email, pwd, dept)
        if ok:
            QMessageBox.information(self, "Success", msg)
            for f in [self.add_sid, self.add_name, self.add_email,
                      self.add_dept, self.add_pwd]:
                f.clear()
            self._load_students()
        else:
            QMessageBox.critical(self, "Error", msg)

    def _delete_student(self, student_id):
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Delete student '{student_id}'?  This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            delete_student(student_id)
            self._load_students()
