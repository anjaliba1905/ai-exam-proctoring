#!/usr/bin/env python3
# main_app.py - Application entry point (FIXED v6)

import sys, os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

# ── High DPI must be set BEFORE QApplication is created ──────────────────────
import PyQt5.QtCore
PyQt5.QtCore.QCoreApplication.setAttribute(PyQt5.QtCore.Qt.AA_EnableHighDpiScaling, True)
PyQt5.QtCore.QCoreApplication.setAttribute(PyQt5.QtCore.Qt.AA_UseHighDpiPixmaps, True)

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from database import init_db, init_exam_config
from ui.login_window import LoginWindow
from ui.exam_window import ExamWindow
from ui.permission_gate import PermissionGateDialog
from dashboard.teacher_dashboard import TeacherDashboard


class Application:

    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setApplicationName("AI Exam Proctoring System")
        self.app.setFont(QFont("Segoe UI", 11))

        # Initialise DB schema + seed data + exam config defaults
        init_db()
        init_exam_config()

        self.login_window = None
        self.exam_window  = None
        self.dashboard    = None

    def run(self):
        self._show_login()
        sys.exit(self.app.exec_())

    def _show_login(self):
        self.login_window = LoginWindow()
        self.login_window.login_success.connect(self._on_login)
        self.login_window.show()

    def _on_login(self, user_data: dict, role: str):
        if role == "student":
            self.login_window.hide()

            # ── Permission Gate ── must pass all 3 checks before exam opens
            gate = PermissionGateDialog(user_data, parent=None)
            result = gate.exec_()

            if result != PermissionGateDialog.Accepted:
                # Student cancelled or closed the gate — go back to login
                self.login_window.show()
                return

            # All permissions granted — open the exam
            # FIX: ExamWindow doesn't have _ready; check questions list instead
            try:
                self.exam_window = ExamWindow(user_data)
                if not getattr(self.exam_window, 'questions', None):
                    # No questions loaded — error already shown inside ExamWindow
                    self.login_window.show()
                    return
                self.exam_window.show()
                self.exam_window.destroyed.connect(self.login_window.show)
            except Exception as e:
                from PyQt5.QtWidgets import QMessageBox
                QMessageBox.critical(None, "Exam Error", f"Could not start exam:\n{e}")
                self.login_window.show()

        elif role == "teacher":
            self.login_window.hide()
            self.dashboard = TeacherDashboard()
            self.dashboard.show()
            self.dashboard.destroyed.connect(self.login_window.show)


if __name__ == "__main__":
    Application().run()
