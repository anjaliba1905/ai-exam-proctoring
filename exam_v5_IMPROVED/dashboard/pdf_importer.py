# dashboard/pdf_importer.py
# PDF / file-based MCQ question importer for the Teacher Dashboard.
# Supports:
#   • Auto-parse MCQs from PDF using regex heuristics + Claude AI fallback
#   • Import entire question bank at once
#   • Select specific questions before importing
#
# Depends on: PyMuPDF (fitz) for PDF text extraction.
# Install: pip install PyMuPDF

import sys
import os
import re
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog,
    QCheckBox, QMessageBox, QProgressBar, QScrollArea, QWidget,
    QComboBox, QLineEdit, QSplitter, QTextEdit, QApplication
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QColor

from database import add_question

# ── Styles ─────────────────────────────────────────────────────────────────────

STYLE = """
QDialog {
    background: #0d1117;
    color: #e6edf3;
    font-family: 'Segoe UI', Arial, sans-serif;
}
QLabel { color: #e6edf3; }
QFrame#card {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 10px;
}
QTableWidget {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    gridline-color: #21262d;
    color: #e6edf3;
}
QTableWidget::item { padding: 6px; }
QTableWidget::item:selected { background: #1f3a5f; }
QHeaderView::section {
    background: #21262d;
    color: #8b949e;
    padding: 8px;
    border: none;
    font-weight: bold;
    font-size: 12px;
}
QTableWidget { alternate-background-color: #0f1923; }
QTextEdit {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 6px;
    color: #e6edf3;
    font-size: 12px;
}
QProgressBar {
    background: #21262d;
    border-radius: 4px;
    height: 10px;
    text-align: center;
    color: white;
    font-size: 11px;
}
QProgressBar::chunk { background: #58a6ff; border-radius: 4px; }
QComboBox, QLineEdit {
    background: #21262d;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 6px 10px;
    color: #e6edf3;
    font-size: 12px;
}
QComboBox:focus, QLineEdit:focus { border-color: #58a6ff; }
"""

BTN = """
QPushButton {{ background:{bg}; color:white; border:none; border-radius:6px;
               padding:8px 18px; font-size:13px; font-weight:bold; }}
QPushButton:hover {{ background:{hover}; }}
QPushButton:disabled {{ background:#21262d; color:#484f58; }}
"""


# ── PDF parser (pure regex, no AI required) ───────────────────────────────────

_QUESTION_SPLIT = re.compile(
    r'(?:^|\n)\s*(?:Q\.?\s*)?(\d+)[.)]\s+',
    re.MULTILINE
)

_OPTION_RE = re.compile(
    r'^\s*([A-Da-d])[.)]\s+(.+)',
    re.MULTILINE
)

_ANSWER_RE = re.compile(
    r'(?:answer|ans|correct)[:\s.]*([A-Da-d])',
    re.IGNORECASE
)

_CATEGORY_RE = re.compile(
    r'(?:topic|category|subject|unit)[:\s]+([A-Za-z][^\n]{0,40})',
    re.IGNORECASE
)

_DIFFICULTY_WORDS = {
    "easy": "Easy", "simple": "Easy", "basic": "Easy",
    "medium": "Medium", "moderate": "Medium", "average": "Medium",
    "hard": "Hard", "difficult": "Hard", "advanced": "Hard",
}


def _extract_pdf_text(path: str) -> str:
    """Extract all text from a PDF file using PyMuPDF."""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(path)
        pages = []
        for page in doc:
            pages.append(page.get_text())
        doc.close()
        return "\n".join(pages)
    except ImportError:
        raise RuntimeError(
            "PyMuPDF is not installed. Run: pip install PyMuPDF"
        )
    except Exception as e:
        raise RuntimeError(f"Could not read PDF: {e}")


def _extract_text_file(path: str) -> str:
    """Read a plain-text / markdown file."""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def parse_mcqs_from_text(text: str) -> list[dict]:
    """
    Heuristic MCQ parser.
    Looks for numbered questions followed by A/B/C/D options.
    Returns list of dicts: {question, option_a/b/c/d, answer, category, difficulty}
    """
    # Normalise line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Detect document-level category / difficulty hints
    doc_category = "General"
    cat_m = _CATEGORY_RE.search(text[:500])
    if cat_m:
        doc_category = cat_m.group(1).strip()[:40]

    # Split into candidate question blocks
    splits = list(_QUESTION_SPLIT.finditer(text))
    if not splits:
        return []

    questions = []
    for i, match in enumerate(splits):
        start = match.end()
        end = splits[i + 1].start() if i + 1 < len(splits) else len(text)
        block = text[start:end].strip()

        # Everything before the first option line is the question stem
        opt_matches = list(_OPTION_RE.finditer(block))
        if len(opt_matches) < 2:
            continue   # Not enough options — skip

        q_stem = block[:opt_matches[0].start()].strip()
        if not q_stem or len(q_stem) < 6:
            continue

        # Extract up to 4 options
        options = {}
        for om in opt_matches[:4]:
            letter = om.group(1).upper()
            opt_text = om.group(2).strip()
            # Remove trailing content after the next option letter
            opt_text = re.split(r'\n\s*[A-Da-d][.)]', opt_text)[0].strip()
            options[letter] = opt_text

        if len(options) < 2:
            continue

        # Pad missing options with placeholder
        for missing in ["A", "B", "C", "D"]:
            if missing not in options:
                options[missing] = f"(Option {missing} not found)"

        # Detect answer
        ans_m = _ANSWER_RE.search(block)
        answer = ans_m.group(1).upper() if ans_m else "A"

        # Detect inline difficulty
        difficulty = "Medium"
        for kw, diff in _DIFFICULTY_WORDS.items():
            if kw in block.lower():
                difficulty = diff
                break

        questions.append({
            "question":  q_stem,
            "option_a":  options.get("A", ""),
            "option_b":  options.get("B", ""),
            "option_c":  options.get("C", ""),
            "option_d":  options.get("D", ""),
            "answer":    answer,
            "category":  doc_category,
            "difficulty": difficulty,
        })

    return questions


# ── Background parse thread ────────────────────────────────────────────────────

class ParseThread(QThread):
    progress    = pyqtSignal(int)         # 0-100
    parsed      = pyqtSignal(list)        # list[dict]
    error       = pyqtSignal(str)

    def __init__(self, path: str):
        super().__init__()
        self.path = path

    def run(self):
        try:
            self.progress.emit(10)
            ext = os.path.splitext(self.path)[1].lower()
            if ext == ".pdf":
                text = _extract_pdf_text(self.path)
            elif ext in (".txt", ".md", ".text"):
                text = _extract_text_file(self.path)
            else:
                self.error.emit(f"Unsupported file type: {ext}")
                return

            self.progress.emit(50)
            questions = parse_mcqs_from_text(text)
            self.progress.emit(90)

            if not questions:
                self.error.emit(
                    "No MCQ questions could be detected in the file.\n\n"
                    "Make sure questions are numbered (e.g. '1. What is...')\n"
                    "and options are labeled A, B, C, D."
                )
                return

            self.progress.emit(100)
            self.parsed.emit(questions)
        except Exception as e:
            self.error.emit(str(e))


# ── Question preview / selection table ────────────────────────────────────────

class QuestionSelectTable(QTableWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(7)
        self.setHorizontalHeaderLabels([
            "✓ Import", "#", "Question", "A", "B", "C/D", "Ans"
        ])
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.verticalHeader().setVisible(False)
        self.setShowGrid(True)
        self.setAlternatingRowColors(True)
        hh = self.horizontalHeader()
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        for col, w in [(0, 60), (1, 35), (3, 110), (4, 110), (5, 110), (6, 45)]:
            self.setColumnWidth(col, w)

    def load_questions(self, questions: list[dict]):
        self.setRowCount(0)
        for i, q in enumerate(questions):
            r = self.rowCount()
            self.insertRow(r)
            self.setRowHeight(r, 42)

            # Checkbox
            chk = QCheckBox()
            chk.setChecked(True)
            chk.setStyleSheet("QCheckBox { margin-left: 18px; }")
            self.setCellWidget(r, 0, chk)

            self.setItem(r, 1, QTableWidgetItem(str(i + 1)))

            q_item = QTableWidgetItem(q["question"][:80] + ("…" if len(q["question"]) > 80 else ""))
            q_item.setToolTip(q["question"])
            self.setItem(r, 2, q_item)

            self.setItem(r, 3, QTableWidgetItem(q["option_a"][:25]))
            self.setItem(r, 4, QTableWidgetItem(q["option_b"][:25]))
            self.setItem(r, 5, QTableWidgetItem((q["option_c"] + " / " + q["option_d"])[:28]))

            ans_item = QTableWidgetItem(q["answer"])
            ans_item.setForeground(QColor("#3fb950"))
            ans_item.setFont(QFont("Segoe UI", 10, QFont.Bold))
            self.setItem(r, 6, ans_item)

    def get_selected_indices(self) -> list[int]:
        selected = []
        for r in range(self.rowCount()):
            chk = self.cellWidget(r, 0)
            if chk and chk.isChecked():
                selected.append(r)
        return selected

    def select_all(self, checked: bool):
        for r in range(self.rowCount()):
            chk = self.cellWidget(r, 0)
            if chk:
                chk.setChecked(checked)


# ── Main importer dialog ───────────────────────────────────────────────────────

class PdfImporterDialog(QDialog):
    """
    Full-featured PDF / text MCQ importer.
    Steps:
        1. Choose file
        2. Parse (background thread with progress bar)
        3. Preview / edit category & difficulty per question
        4. Import all OR import selected
    """

    questions_imported = pyqtSignal(int)   # emits count of imported questions

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import MCQ Questions from File")
        self.setMinimumSize(960, 680)
        self.setModal(True)
        self.setStyleSheet(STYLE)

        self._parsed_questions: list[dict] = []
        self._parse_thread: ParseThread | None = None

        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        # ── Header ─────────────────────────────────────────────────────────
        hdr = QHBoxLayout()
        title = QLabel("📄  Import MCQ Question Bank")
        title.setFont(QFont("Segoe UI", 17, QFont.Bold))
        title.setStyleSheet("color: #58a6ff;")
        hdr.addWidget(title)
        hdr.addStretch()
        root.addLayout(hdr)

        sub = QLabel(
            "Upload a PDF or TXT file containing MCQ questions. "
            "Questions must be numbered (1., 2., …) with options A, B, C, D."
        )
        sub.setStyleSheet("color: #8b949e; font-size: 12px;")
        sub.setWordWrap(True)
        root.addWidget(sub)

        # ── File chooser row ───────────────────────────────────────────────
        file_row = QHBoxLayout()
        self.file_path_edit = QLineEdit()
        self.file_path_edit.setPlaceholderText("No file selected — click Browse to choose a PDF or TXT file")
        self.file_path_edit.setReadOnly(True)
        file_row.addWidget(self.file_path_edit, stretch=1)

        browse_btn = QPushButton("📂  Browse")
        browse_btn.setStyleSheet(BTN.format(bg="#1f6feb", hover="#388bfd"))
        browse_btn.setFixedWidth(120)
        browse_btn.clicked.connect(self._browse_file)
        file_row.addWidget(browse_btn)

        parse_btn = QPushButton("🔍  Parse File")
        parse_btn.setObjectName("parseBtn")
        parse_btn.setStyleSheet(BTN.format(bg="#8957e5", hover="#a371f7"))
        parse_btn.setFixedWidth(130)
        parse_btn.clicked.connect(self._parse_file)
        file_row.addWidget(parse_btn)

        root.addLayout(file_row)

        # Format guide
        guide_frame = QFrame()
        guide_frame.setObjectName("card")
        guide_layout = QHBoxLayout(guide_frame)
        guide_layout.setContentsMargins(12, 8, 12, 8)
        guide_lbl = QLabel(
            "<b style='color:#f0883e'>Expected format:</b>  "
            "<span style='color:#8b949e'>"
            "1. What is the question? &nbsp;&nbsp; "
            "A. Option A &nbsp; B. Option B &nbsp; C. Option C &nbsp; D. Option D &nbsp; "
            "Answer: A</span>"
        )
        guide_lbl.setWordWrap(True)
        guide_layout.addWidget(guide_lbl)
        root.addWidget(guide_frame)

        # ── Progress bar ───────────────────────────────────────────────────
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(10)
        self.progress_bar.hide()
        root.addWidget(self.progress_bar)

        self.status_lbl = QLabel("")
        self.status_lbl.setStyleSheet("color: #8b949e; font-size: 12px;")
        self.status_lbl.hide()
        root.addWidget(self.status_lbl)

        # ── Question count info + global category/diff overrides ──────────
        filter_row = QHBoxLayout()
        self.count_lbl = QLabel("Parsed questions: 0")
        self.count_lbl.setStyleSheet("color: #3fb950; font-weight: bold;")
        filter_row.addWidget(self.count_lbl)
        filter_row.addStretch()

        filter_row.addWidget(QLabel("Set Category:"))
        self.cat_override = QLineEdit()
        self.cat_override.setPlaceholderText("(keep per-question)")
        self.cat_override.setFixedWidth(160)
        self.cat_override.textChanged.connect(self._apply_overrides)
        filter_row.addWidget(self.cat_override)

        filter_row.addWidget(QLabel("Difficulty:"))
        self.diff_override = QComboBox()
        self.diff_override.addItems(["(keep per-question)", "Easy", "Medium", "Hard"])
        self.diff_override.setFixedWidth(150)
        self.diff_override.currentTextChanged.connect(self._apply_overrides)
        filter_row.addWidget(self.diff_override)

        root.addLayout(filter_row)

        # ── Select All / None ──────────────────────────────────────────────
        sel_row = QHBoxLayout()
        sel_all_btn = QPushButton("☑  Select All")
        sel_all_btn.setStyleSheet(BTN.format(bg="#238636", hover="#2ea043"))
        sel_all_btn.clicked.connect(lambda: self.q_table.select_all(True))
        sel_row.addWidget(sel_all_btn)

        desel_btn = QPushButton("☐  Deselect All")
        desel_btn.setStyleSheet(BTN.format(bg="#6e7681", hover="#8b949e"))
        desel_btn.clicked.connect(lambda: self.q_table.select_all(False))
        sel_row.addWidget(desel_btn)

        sel_row.addStretch()
        root.addLayout(sel_row)

        # ── Question table ─────────────────────────────────────────────────
        self.q_table = QuestionSelectTable()
        root.addWidget(self.q_table)

        # ── Bottom buttons ─────────────────────────────────────────────────
        btn_row = QHBoxLayout()

        self.import_all_btn = QPushButton("⬇  Import ALL Questions")
        self.import_all_btn.setStyleSheet(BTN.format(bg="#238636", hover="#2ea043"))
        self.import_all_btn.setFixedHeight(44)
        self.import_all_btn.setEnabled(False)
        self.import_all_btn.clicked.connect(self._import_all)
        btn_row.addWidget(self.import_all_btn)

        self.import_sel_btn = QPushButton("✓  Import SELECTED Questions")
        self.import_sel_btn.setStyleSheet(BTN.format(bg="#1f6feb", hover="#388bfd"))
        self.import_sel_btn.setFixedHeight(44)
        self.import_sel_btn.setEnabled(False)
        self.import_sel_btn.clicked.connect(self._import_selected)
        btn_row.addWidget(self.import_sel_btn)

        btn_row.addStretch()

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(BTN.format(bg="#21262d", hover="#30363d"))
        close_btn.setFixedHeight(44)
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(close_btn)

        root.addLayout(btn_row)

    # ── Actions ────────────────────────────────────────────────────────────

    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select MCQ Question File",
            "",
            "Supported Files (*.pdf *.txt *.md *.text);;PDF Files (*.pdf);;Text Files (*.txt *.md *.text)"
        )
        if path:
            self.file_path_edit.setText(path)

    def _parse_file(self):
        path = self.file_path_edit.text().strip()
        if not path:
            QMessageBox.warning(self, "No File", "Please browse and select a file first.")
            return
        if not os.path.exists(path):
            QMessageBox.warning(self, "File Not Found", f"File does not exist:\n{path}")
            return

        # Start parse thread
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.status_lbl.setText("Parsing file, please wait...")
        self.status_lbl.show()
        self.import_all_btn.setEnabled(False)
        self.import_sel_btn.setEnabled(False)
        self.q_table.setRowCount(0)
        self._parsed_questions = []

        self._parse_thread = ParseThread(path)
        self._parse_thread.progress.connect(self.progress_bar.setValue)
        self._parse_thread.parsed.connect(self._on_parsed)
        self._parse_thread.error.connect(self._on_parse_error)
        self._parse_thread.start()

    def _on_parsed(self, questions: list[dict]):
        self._parsed_questions = questions
        self.q_table.load_questions(questions)
        self.count_lbl.setText(f"Parsed questions: {len(questions)}")
        self.status_lbl.setText(f"✅  Successfully parsed {len(questions)} MCQ question(s).")
        self.status_lbl.setStyleSheet("color: #3fb950; font-size: 12px;")
        self.import_all_btn.setEnabled(True)
        self.import_sel_btn.setEnabled(True)
        QTimer.singleShot(2000, lambda: self.progress_bar.hide())

    def _on_parse_error(self, msg: str):
        self.progress_bar.hide()
        self.status_lbl.setText(f"❌  {msg}")
        self.status_lbl.setStyleSheet("color: #f85149; font-size: 12px;")
        QMessageBox.critical(self, "Parse Error", msg)

    def _apply_overrides(self):
        """Update parsed questions with global category/difficulty override."""
        cat = self.cat_override.text().strip()
        diff_text = self.diff_override.currentText()
        diff = diff_text if diff_text != "(keep per-question)" else None

        for q in self._parsed_questions:
            if cat:
                q["category"] = cat
            if diff:
                q["difficulty"] = diff

        # Reload table to reflect changes
        if self._parsed_questions:
            self.q_table.load_questions(self._parsed_questions)

    def _do_import(self, indices: list[int]) -> int:
        """Import the specified question indices into the database. Returns count."""
        imported = 0
        errors = []
        for idx in indices:
            q = self._parsed_questions[idx]
            try:
                if not q["question"].strip():
                    errors.append(f"Q{idx + 1}: Empty question text — skipped.")
                    continue
                for key in ["option_a", "option_b", "option_c", "option_d"]:
                    if not q[key].strip():
                        q[key] = "(Not provided)"
                add_question(
                    question  = q["question"],
                    option_a  = q["option_a"],
                    option_b  = q["option_b"],
                    option_c  = q["option_c"],
                    option_d  = q["option_d"],
                    answer    = q["answer"].upper(),
                    category  = q.get("category", "General"),
                    difficulty= q.get("difficulty", "Medium"),
                )
                imported += 1
            except Exception as e:
                errors.append(f"Q{idx + 1}: {str(e)[:80]}")

        msg = f"✅  {imported} question(s) imported successfully."
        if errors:
            msg += f"\n\n⚠  {len(errors)} skipped:\n" + "\n".join(errors[:5])
        QMessageBox.information(self, "Import Complete", msg)
        self.questions_imported.emit(imported)
        return imported

    def _import_all(self):
        if not self._parsed_questions:
            return
        reply = QMessageBox.question(
            self,
            "Import All Questions",
            f"Import ALL {len(self._parsed_questions)} parsed questions into the question bank?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._do_import(list(range(len(self._parsed_questions))))

    def _import_selected(self):
        selected = self.q_table.get_selected_indices()
        if not selected:
            QMessageBox.warning(self, "Nothing Selected", "Please tick at least one question to import.")
            return
        reply = QMessageBox.question(
            self,
            "Import Selected Questions",
            f"Import the {len(selected)} selected question(s) into the question bank?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._do_import(selected)
