# ui/login_window.py - Login screen for students and teacher

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QMessageBox, QTabWidget, QFormLayout, QComboBox
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QPixmap, QColor, QPalette

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import authenticate_student
from config import TEACHER_USERNAME, TEACHER_PASSWORD, COLOR_PRIMARY, COLOR_HIGHLIGHT

STYLE = """
QWidget {
    background-color: #0d1117;
    color: #e6edf3;
    font-family: 'Segoe UI', Arial, sans-serif;
}
QFrame#card {
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 12px;
    padding: 20px;
}
QLabel#title {
    font-size: 26px;
    font-weight: bold;
    color: #58a6ff;
}
QLabel#subtitle {
    font-size: 13px;
    color: #8b949e;
}
QLabel {
    font-size: 13px;
    color: #c9d1d9;
}
QLineEdit {
    background-color: #0d1117;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 10px 14px;
    font-size: 14px;
    color: #e6edf3;
    min-height: 20px;
}
QLineEdit:focus {
    border: 1px solid #58a6ff;
}
QPushButton#primary {
    background-color: #238636;
    color: white;
    border: none;
    border-radius: 8px;
    padding: 12px;
    font-size: 15px;
    font-weight: bold;
    min-height: 44px;
}
QPushButton#primary:hover {
    background-color: #2ea043;
}
QPushButton#secondary {
    background-color: #21262d;
    color: #c9d1d9;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 10px;
    font-size: 13px;
}
QPushButton#secondary:hover {
    background-color: #30363d;
    color: #58a6ff;
}
QTabWidget::pane {
    border: 1px solid #30363d;
    border-radius: 8px;
    background: #161b22;
}
QTabBar::tab {
    background: #21262d;
    color: #8b949e;
    padding: 8px 20px;
    border-radius: 6px 6px 0 0;
    margin-right: 2px;
    font-size: 13px;
}
QTabBar::tab:selected {
    background: #161b22;
    color: #58a6ff;
    border-bottom: 2px solid #58a6ff;
}
"""


class LoginWindow(QWidget):
    login_success = pyqtSignal(dict, str)   # (user_data, role: 'student'|'teacher')

    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI Exam Proctoring System — Login")
        self.setMinimumSize(460, 560)
        self.setStyleSheet(STYLE)
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignCenter)
        outer.setContentsMargins(40, 40, 40, 40)

        # ── Header ─────────────────────────────────────────────────────────
        hdr = QVBoxLayout()
        hdr.setAlignment(Qt.AlignCenter)
        icon_lbl = QLabel("🎓")
        icon_lbl.setFont(QFont("Segoe UI Emoji", 48))
        icon_lbl.setAlignment(Qt.AlignCenter)

        title = QLabel("AI Exam Proctoring")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignCenter)

        subtitle = QLabel("Secure · Intelligent · Reliable")
        subtitle.setObjectName("subtitle")
        subtitle.setAlignment(Qt.AlignCenter)

        hdr.addWidget(icon_lbl)
        hdr.addWidget(title)
        hdr.addWidget(subtitle)
        outer.addLayout(hdr)
        outer.addSpacing(24)

        # ── Card frame ─────────────────────────────────────────────────────
        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 24, 24, 24)
        card_layout.setSpacing(12)

        # Tabs: Student | Teacher
        tabs = QTabWidget()
        tabs.addTab(self._student_tab(), "  Student  ")
        tabs.addTab(self._teacher_tab(), "  Teacher  ")
        card_layout.addWidget(tabs)

        outer.addWidget(card)

    # ── Student tab ────────────────────────────────────────────────────────
    def _student_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(12)
        layout.setContentsMargins(8, 16, 8, 8)

        layout.addWidget(QLabel("Student ID"))
        self.stu_id = QLineEdit()
        self.stu_id.setPlaceholderText("e.g. STU001")
        layout.addWidget(self.stu_id)

        layout.addWidget(QLabel("Password"))
        self.stu_pwd = QLineEdit()
        self.stu_pwd.setEchoMode(QLineEdit.Password)
        self.stu_pwd.setPlaceholderText("Enter password")
        self.stu_pwd.returnPressed.connect(self._student_login)
        layout.addWidget(self.stu_pwd)

        layout.addSpacing(8)
        btn = QPushButton("Login & Start Exam")
        btn.setObjectName("primary")
        btn.clicked.connect(self._student_login)
        layout.addWidget(btn)

        hint = QLabel("Demo credentials: STU001 / pass123")
        hint.setStyleSheet("color: #6e7681; font-size: 11px;")
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint)

        return w

    # ── Teacher tab ────────────────────────────────────────────────────────
    def _teacher_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(12)
        layout.setContentsMargins(8, 16, 8, 8)

        layout.addWidget(QLabel("Username"))
        self.tea_user = QLineEdit()
        self.tea_user.setPlaceholderText("admin")
        layout.addWidget(self.tea_user)

        layout.addWidget(QLabel("Password"))
        self.tea_pwd = QLineEdit()
        self.tea_pwd.setEchoMode(QLineEdit.Password)
        self.tea_pwd.setPlaceholderText("Enter admin password")
        self.tea_pwd.returnPressed.connect(self._teacher_login)
        layout.addWidget(self.tea_pwd)

        layout.addSpacing(8)
        btn = QPushButton("Open Teacher Dashboard")
        btn.setObjectName("primary")
        btn.setStyleSheet("""
            QPushButton { background-color: #1f6feb; border: none; border-radius: 8px;
                          padding: 12px; font-size: 15px; font-weight: bold; color: white; }
            QPushButton:hover { background-color: #388bfd; }
        """)
        btn.clicked.connect(self._teacher_login)
        layout.addWidget(btn)

        hint = QLabel("Default: admin / admin123")
        hint.setStyleSheet("color: #6e7681; font-size: 11px;")
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint)

        return w

    def _student_login(self):
        sid = self.stu_id.text().strip()
        pwd = self.stu_pwd.text().strip()
        if not sid or not pwd:
            QMessageBox.warning(self, "Missing Fields", "Please enter Student ID and Password.")
            return
        user = authenticate_student(sid, pwd)
        if user:
            self.login_success.emit(user, "student")
        else:
            QMessageBox.critical(self, "Login Failed", "Invalid Student ID or Password.")

    def _teacher_login(self):
        u = self.tea_user.text().strip()
        p = self.tea_pwd.text().strip()
        if u == TEACHER_USERNAME and p == TEACHER_PASSWORD:
            self.login_success.emit({"name": "Teacher", "role": "teacher"}, "teacher")
        else:
            QMessageBox.critical(self, "Login Failed", "Invalid teacher credentials.")
