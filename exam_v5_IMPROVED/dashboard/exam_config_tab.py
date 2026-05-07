# dashboard/exam_config_tab.py - Exam Configuration Tab for Teacher Dashboard
# Allows teacher to: set duration, pick questions, add/edit/delete questions

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QTableWidget, QTableWidgetItem, QHeaderView,
    QLineEdit, QComboBox, QSpinBox, QTextEdit, QCheckBox,
    QMessageBox, QDialog, QDialogButtonBox, QFormLayout,
    QGroupBox, QScrollArea, QSplitter, QTabWidget, QSizePolicy
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QColor

from database import (
    get_exam_config, set_exam_config,
    get_all_questions, get_active_questions,
    set_question_active, set_all_questions_active,
    add_question, delete_question, update_question,
    init_exam_config
)
from dashboard.pdf_importer import PdfImporterDialog

DIFF_COLORS = {
    "Easy":   ("#3fb950", "#0d2a13"),
    "Medium": ("#f0883e", "#2d1b08"),
    "Hard":   ("#f85149", "#2d0d0c"),
}

BTN_STYLE = """
QPushButton {{ background:{bg}; color:white; border:none; border-radius:6px;
               padding:8px 16px; font-size:12px; font-weight:bold; }}
QPushButton:hover {{ background:{hover}; }}
"""

# Improved action button style for table cells
ACTION_BTN_STYLE = """
QPushButton {{
    background: {bg};
    color: white;
    border: none;
    border-radius: 5px;
    padding: 5px 10px;
    font-size: 11px;
    font-weight: bold;
    min-width: 60px;
    min-height: 26px;
}}
QPushButton:hover {{ background: {hover}; }}
QPushButton:pressed {{ background: {pressed}; }}
"""


class ExamConfigTab(QWidget):
    """
    Full exam configuration panel embedded as a tab in the Teacher Dashboard.
    Features:
      - Set exam duration (minutes)
      - Set exam title
      - Toggle individual questions on/off
      - Add / Edit / Delete questions
      - Select all / deselect all
      - Live counter showing active question count
    """

    config_changed = pyqtSignal()   # Emitted when settings are saved

    def __init__(self, parent=None):
        super().__init__(parent)
        init_exam_config()
        self._build_ui()
        self._load_all()

    # ─────────────────────────── UI BUILD ─────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(14)

        # ── Section header ────────────────────────────────────────────────
        hdr = QHBoxLayout()
        title = QLabel("⚙  Exam Configuration")
        title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        title.setStyleSheet("color:#58a6ff;")
        hdr.addWidget(title)
        hdr.addStretch()
        self.active_q_lbl = QLabel("Active Questions: —")
        self.active_q_lbl.setStyleSheet("color:#3fb950; font-size:13px; font-weight:bold;")
        hdr.addWidget(self.active_q_lbl)
        root.addLayout(hdr)

        # ── Settings cards row ─────────────────────────────────────────────
        settings_row = QHBoxLayout()
        settings_row.setSpacing(12)

        # --- Duration card ---
        dur_card = self._group_box("⏱  Exam Duration")
        dl = QVBoxLayout(dur_card)
        dl.setSpacing(8)
        dur_inner = QHBoxLayout()
        self.duration_spin = QSpinBox()
        self.duration_spin.setRange(5, 180)
        self.duration_spin.setValue(30)
        self.duration_spin.setSuffix("  min")
        self.duration_spin.setFixedWidth(110)
        self.duration_spin.setStyleSheet("""
            QSpinBox { background:#0d1117; border:1px solid #30363d; border-radius:6px;
                       padding:8px; font-size:18px; font-weight:bold; color:#58a6ff; }
            QSpinBox::up-button, QSpinBox::down-button { width:24px; }
        """)
        dur_inner.addWidget(self.duration_spin)
        dur_inner.addWidget(QLabel("minutes"))
        dur_inner.addStretch()
        dl.addLayout(dur_inner)

        quick_row = QHBoxLayout()
        for mins in [15, 30, 45, 60, 90]:
            b = QPushButton(f"{mins}m")
            b.setFixedSize(44, 28)
            b.setStyleSheet("QPushButton{background:#21262d;color:#8b949e;border:1px solid #30363d;border-radius:4px;font-size:11px;} QPushButton:hover{background:#30363d;color:#58a6ff;}")
            b.clicked.connect(lambda _, m=mins: self.duration_spin.setValue(m))
            quick_row.addWidget(b)
        quick_row.addStretch()
        dl.addLayout(quick_row)
        settings_row.addWidget(dur_card)

        # --- Title card ---
        title_card = self._group_box("📝  Exam Title")
        tl = QVBoxLayout(title_card)
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("e.g. Midterm Computer Science Exam")
        self.title_edit.setStyleSheet("QLineEdit{background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:10px;font-size:13px;color:#e6edf3;} QLineEdit:focus{border-color:#58a6ff;}")
        tl.addWidget(self.title_edit)
        settings_row.addWidget(title_card, stretch=2)

        # --- Summary card ---
        sum_card = self._group_box("📊  Current Config")
        sl = QFormLayout(sum_card)
        sl.setSpacing(8)
        self.sum_duration = QLabel("—")
        self.sum_total_q  = QLabel("—")
        self.sum_active_q = QLabel("—")
        for lbl, val in [("Duration:", self.sum_duration),
                          ("Total Qs:", self.sum_total_q),
                          ("Active Qs:", self.sum_active_q)]:
            lk = QLabel(lbl); lk.setStyleSheet("color:#8b949e; font-size:12px;")
            val.setStyleSheet("color:#e6edf3; font-weight:bold; font-size:13px;")
            sl.addRow(lk, val)
        settings_row.addWidget(sum_card)

        root.addLayout(settings_row)

        # Save settings button
        save_btn = QPushButton("💾  Save Exam Settings")
        save_btn.setStyleSheet(BTN_STYLE.format(bg="#1f6feb", hover="#388bfd"))
        save_btn.setFixedHeight(40)
        save_btn.clicked.connect(self._save_settings)
        root.addWidget(save_btn, alignment=Qt.AlignLeft)

        # Divider
        div = QFrame(); div.setFrameShape(QFrame.HLine)
        div.setStyleSheet("border-color:#30363d;")
        root.addWidget(div)

        # ── Question Management ────────────────────────────────────────────
        q_hdr = QHBoxLayout()
        q_hdr.setSpacing(10)
        ql = QLabel("📋  Question Bank")
        ql.setFont(QFont("Segoe UI", 14, QFont.Bold))
        ql.setStyleSheet("color:#e6edf3;")
        q_hdr.addWidget(ql)
        q_hdr.addStretch()

        sel_all_btn = QPushButton("✓ Select All")
        sel_all_btn.setStyleSheet(BTN_STYLE.format(bg="#238636", hover="#2ea043"))
        sel_all_btn.setFixedHeight(36)
        sel_all_btn.clicked.connect(lambda: self._toggle_all(True))
        q_hdr.addWidget(sel_all_btn)

        desel_btn = QPushButton("✗ Deselect All")
        desel_btn.setStyleSheet(BTN_STYLE.format(bg="#6e7681", hover="#8b949e"))
        desel_btn.setFixedHeight(36)
        desel_btn.clicked.connect(lambda: self._toggle_all(False))
        q_hdr.addWidget(desel_btn)

        add_q_btn = QPushButton("＋  Add Question")
        add_q_btn.setStyleSheet(BTN_STYLE.format(bg="#8957e5", hover="#a371f7"))
        add_q_btn.setFixedHeight(36)
        add_q_btn.clicked.connect(self._open_add_dialog)
        q_hdr.addWidget(add_q_btn)

        import_pdf_btn = QPushButton("📄  Import from PDF / File")
        import_pdf_btn.setStyleSheet(BTN_STYLE.format(bg="#f0883e", hover="#ffa657"))
        import_pdf_btn.setFixedHeight(36)
        import_pdf_btn.clicked.connect(self._open_pdf_importer)
        q_hdr.addWidget(import_pdf_btn)

        root.addLayout(q_hdr)

        # Question table — improved sizing and row height
        self.q_table = QTableWidget()
        self.q_table.setColumnCount(8)
        self.q_table.setHorizontalHeaderLabels([
            "✓ Active", "ID", "Category", "Difficulty", "Question", "Answer", "Edit", "Delete"
        ])
        self.q_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.q_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.q_table.verticalHeader().setVisible(False)
        self.q_table.setShowGrid(True)
        self.q_table.setAlternatingRowColors(True)
        self.q_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        # Make the table take up remaining vertical space
        self.q_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # Larger default row height for readability
        self.q_table.verticalHeader().setDefaultSectionSize(46)
        self.q_table.setMinimumHeight(350)
        self.q_table.setStyleSheet("""
            QTableWidget {
                background:#161b22; border:1px solid #30363d; border-radius:8px;
                gridline-color:#21262d;
            }
            QTableWidget::item { padding:8px 6px; font-size:12px; color:#e6edf3; }
            QTableWidget::item:selected { background:#1f3a5f; color:#e6edf3; }
            QHeaderView::section {
                background:#21262d; color:#8b949e; padding:12px 8px;
                border:none; font-weight:bold; font-size:12px;
                border-bottom: 2px solid #388bfd;
            }
            QTableWidget { alternate-background-color:#0f1923; }
            QScrollBar:vertical { background:#161b22; width:10px; border-radius:5px; }
            QScrollBar::handle:vertical { background:#30363d; border-radius:5px; min-height:30px; }
            QScrollBar::handle:vertical:hover { background:#484f58; }
        """)
        root.addWidget(self.q_table, stretch=1)

    # ─────────────────────────── LOAD DATA ────────────────────────────────

    def _load_all(self):
        self._load_settings()
        self._load_questions()

    def _load_settings(self):
        cfg = get_exam_config()
        self.duration_spin.setValue(int(cfg.get("exam_duration_minutes", 30)))
        self.title_edit.setText(cfg.get("exam_title", "General Knowledge Exam"))
        self._update_summary()

    def _load_questions(self):
        questions = get_all_questions()
        active_ids = {q["id"] for q in get_active_questions()}

        t = self.q_table
        t.setRowCount(0)
        t.setColumnWidth(0, 75)    # Active checkbox
        t.setColumnWidth(1, 45)    # ID
        t.setColumnWidth(2, 145)   # Category
        t.setColumnWidth(3, 90)    # Difficulty
        # Column 4 (Question) is stretch
        t.setColumnWidth(5, 75)    # Answer
        t.setColumnWidth(6, 80)    # Edit
        t.setColumnWidth(7, 80)    # Delete

        for q in questions:
            r = t.rowCount(); t.insertRow(r)
            t.setRowHeight(r, 46)

            # Checkbox — centred
            chk_widget = QWidget()
            chk_layout = QHBoxLayout(chk_widget)
            chk_layout.setContentsMargins(0, 0, 0, 0)
            chk_layout.setAlignment(Qt.AlignCenter)
            chk = QCheckBox()
            chk.setChecked(q["id"] in active_ids)
            chk.setStyleSheet("""
                QCheckBox::indicator { width:18px; height:18px; border-radius:4px;
                    border:2px solid #30363d; background:#0d1117; }
                QCheckBox::indicator:checked { background:#238636; border-color:#2ea043; }
                QCheckBox::indicator:hover { border-color:#58a6ff; }
            """)
            chk.stateChanged.connect(lambda state, qid=q["id"]: self._toggle_question(qid, state == Qt.Checked))
            chk_layout.addWidget(chk)
            t.setCellWidget(r, 0, chk_widget)

            t.setItem(r, 1, QTableWidgetItem(str(q["id"])))
            t.setItem(r, 2, QTableWidgetItem(q.get("category", "General")))

            # Difficulty badge
            diff_item = QTableWidgetItem(q.get("difficulty", "Medium"))
            colors = DIFF_COLORS.get(q.get("difficulty", "Medium"), ("#e6edf3", "#161b22"))
            diff_item.setForeground(QColor(colors[0]))
            diff_item.setBackground(QColor(colors[1]))
            diff_item.setFont(QFont("Segoe UI", 10, QFont.Bold))
            diff_item.setTextAlignment(Qt.AlignCenter)
            t.setItem(r, 3, diff_item)

            # Question text (truncated with tooltip)
            q_text = q["question"]
            q_item = QTableWidgetItem(q_text[:90] + ("…" if len(q_text) > 90 else ""))
            q_item.setToolTip(q_text)
            t.setItem(r, 4, q_item)

            ans_item = QTableWidgetItem(q["answer"])
            ans_item.setForeground(QColor("#3fb950"))
            ans_item.setFont(QFont("Segoe UI", 11, QFont.Bold))
            ans_item.setTextAlignment(Qt.AlignCenter)
            t.setItem(r, 5, ans_item)

            # Edit button — proper styling
            edit_btn = QPushButton("✏  Edit")
            edit_btn.setStyleSheet(ACTION_BTN_STYLE.format(
                bg="#1f6feb", hover="#388bfd", pressed="#1158c7"
            ))
            edit_btn.setCursor(Qt.PointingHandCursor)
            edit_btn.clicked.connect(lambda _, row_q=q: self._open_edit_dialog(row_q))
            t.setCellWidget(r, 6, self._wrap_btn(edit_btn))

            # Delete button — proper styling
            del_btn = QPushButton("🗑  Del")
            del_btn.setStyleSheet(ACTION_BTN_STYLE.format(
                bg="#da3633", hover="#f85149", pressed="#b91c1a"
            ))
            del_btn.setCursor(Qt.PointingHandCursor)
            del_btn.clicked.connect(lambda _, qid=q["id"]: self._delete_question(qid))
            t.setCellWidget(r, 7, self._wrap_btn(del_btn))

        self._update_summary()

    @staticmethod
    def _wrap_btn(btn):
        """Wrap a button in a centred container widget for table cells."""
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setAlignment(Qt.AlignCenter)
        lay.addWidget(btn)
        return w

    def _update_summary(self):
        all_q = get_all_questions()
        active_q = get_active_questions()
        dur = self.duration_spin.value()
        self.sum_duration.setText(f"{dur} minutes")
        self.sum_total_q.setText(str(len(all_q)))
        self.sum_active_q.setText(str(len(active_q)))
        self.active_q_lbl.setText(f"Active Questions: {len(active_q)} / {len(all_q)}")

    # ─────────────────────────── ACTIONS ──────────────────────────────────

    def _save_settings(self):
        duration = self.duration_spin.value()
        title = self.title_edit.text().strip() or "General Knowledge Exam"
        set_exam_config("exam_duration_minutes", str(duration))
        set_exam_config("exam_title", title)
        self._update_summary()
        self.config_changed.emit()
        QMessageBox.information(self, "Saved",
            f"✅ Exam settings saved!\n\nTitle: {title}\nDuration: {duration} minutes\nActive questions: {len(get_active_questions())}")

    def _toggle_question(self, question_id: int, is_active: bool):
        set_question_active(question_id, is_active)
        self._update_summary()

    def _toggle_all(self, active: bool):
        set_all_questions_active(active)
        self._load_questions()

    def _open_add_dialog(self):
        dlg = QuestionDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.get_data()
            if not data["question"].strip():
                QMessageBox.warning(self, "Error", "Question text cannot be empty.")
                return
            for letter in ["option_a", "option_b", "option_c", "option_d"]:
                if not data[letter].strip():
                    QMessageBox.warning(self, "Error", f"Option {letter[-1].upper()} cannot be empty.")
                    return
            add_question(**data)
            self._load_questions()
            QMessageBox.information(self, "Added", "✅ Question added to the bank.")

    def _open_edit_dialog(self, q: dict):
        dlg = QuestionDialog(self, question_data=q)
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.get_data()
            if not data["question"].strip():
                QMessageBox.warning(self, "Error", "Question text cannot be empty.")
                return
            for letter in ["option_a", "option_b", "option_c", "option_d"]:
                if not data[letter].strip():
                    QMessageBox.warning(self, "Error", f"Option {letter[-1].upper()} cannot be empty.")
                    return
            update_question(
                q["id"], data["question"], data["option_a"], data["option_b"],
                data["option_c"], data["option_d"], data["answer"],
                data["category"], data["difficulty"]
            )
            self._load_questions()

    def _delete_question(self, question_id: int):
        reply = QMessageBox.question(
            self, "Delete Question",
            "Permanently delete this question?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            delete_question(question_id)
            self._load_questions()

    def _open_pdf_importer(self):
        dlg = PdfImporterDialog(self)
        dlg.questions_imported.connect(self._on_questions_imported)
        dlg.exec_()

    def _on_questions_imported(self, count: int):
        self._load_questions()
        self.config_changed.emit()

    @staticmethod
    def _group_box(title: str) -> QGroupBox:
        gb = QGroupBox(title)
        gb.setStyleSheet("""
            QGroupBox { background:#161b22; border:1px solid #30363d; border-radius:10px;
                        margin-top:12px; font-size:12px; font-weight:bold; color:#8b949e; padding:10px; }
            QGroupBox::title { subcontrol-origin:margin; left:10px; padding:0 6px; color:#8b949e; }
        """)
        return gb


# ─────────────────────────── Question Dialog ──────────────────────────────────

class QuestionDialog(QDialog):
    """Add / Edit question popup dialog."""

    def __init__(self, parent=None, question_data: dict = None):
        super().__init__(parent)
        self.setWindowTitle("Add Question" if question_data is None else "Edit Question")
        self.setMinimumWidth(640)
        self.setStyleSheet("""
            QDialog { background:#161b22; color:#e6edf3; }
            QLabel { color:#c9d1d9; font-size:13px; }
            QLineEdit, QTextEdit, QComboBox {
                background:#0d1117; border:1px solid #30363d; border-radius:6px;
                padding:8px; font-size:13px; color:#e6edf3;
            }
            QLineEdit:focus, QTextEdit:focus, QComboBox:focus { border-color:#58a6ff; }
            QPushButton { background:#238636; color:white; border:none; border-radius:6px;
                          padding:10px 20px; font-size:13px; font-weight:bold; }
            QPushButton:hover { background:#2ea043; }
        """)
        self._build_ui(question_data)

    def _build_ui(self, q):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight)

        self.q_text = QTextEdit()
        self.q_text.setFixedHeight(80)
        self.q_text.setPlaceholderText("Enter full question here...")
        form.addRow("Question:", self.q_text)

        self.opt = {}
        for letter in ["A", "B", "C", "D"]:
            le = QLineEdit()
            le.setPlaceholderText(f"Option {letter}")
            self.opt[letter] = le
            form.addRow(f"Option {letter}:", le)

        self.answer_combo = QComboBox()
        self.answer_combo.addItems(["A", "B", "C", "D"])
        self.answer_combo.setFixedWidth(100)
        form.addRow("Correct Answer:", self.answer_combo)

        self.category_edit = QLineEdit()
        self.category_edit.setPlaceholderText("e.g. Python, Database, Networking")
        form.addRow("Category:", self.category_edit)

        self.diff_combo = QComboBox()
        self.diff_combo.addItems(["Easy", "Medium", "Hard"])
        self.diff_combo.setFixedWidth(120)
        form.addRow("Difficulty:", self.diff_combo)

        layout.addLayout(form)

        if q:
            self.q_text.setPlainText(q.get("question", ""))
            self.opt["A"].setText(q.get("option_a", ""))
            self.opt["B"].setText(q.get("option_b", ""))
            self.opt["C"].setText(q.get("option_c", ""))
            self.opt["D"].setText(q.get("option_d", ""))
            self.answer_combo.setCurrentText(q.get("answer", "A"))
            self.category_edit.setText(q.get("category", "General"))
            self.diff_combo.setCurrentText(q.get("difficulty", "Medium"))

        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        btns.setStyleSheet("QPushButton { padding:8px 18px; }")
        layout.addWidget(btns)

    def get_data(self) -> dict:
        return {
            "question":   self.q_text.toPlainText().strip(),
            "option_a":   self.opt["A"].text().strip(),
            "option_b":   self.opt["B"].text().strip(),
            "option_c":   self.opt["C"].text().strip(),
            "option_d":   self.opt["D"].text().strip(),
            "answer":     self.answer_combo.currentText(),
            "category":   self.category_edit.text().strip() or "General",
            "difficulty": self.diff_combo.currentText(),
        }
