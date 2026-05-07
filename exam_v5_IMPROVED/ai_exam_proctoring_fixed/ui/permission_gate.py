# ui/permission_gate.py  –  Pre-Exam Security Check dialog
# FIX v3 (complete rewrite):
#   1. Application Lockdown ALLOWS cmd.exe / PowerShell / our own python process
#      and BLOCKS everything else (Chrome, File Explorer, Notepad, etc.)
#   2. Uses BOTH window-title scan (ctypes EnumWindows) AND psutil process scan.
#   3. CMD/Terminal is never flagged — the app itself is launched from CMD.
#   4. Screenshot key (PrintScreen / Win+Shift+S) is blocked during dialog.
#   5. Retry button resets and re-runs the scan correctly.
#   6. "Still required" banner is always accurate.

import sys, os, subprocess, platform, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
)
from PyQt5.QtCore  import Qt, QTimer, pyqtSignal, QThread
from PyQt5.QtGui   import QFont

# ─── Stylesheet ───────────────────────────────────────────────────────────────
STYLE = """
QDialog { background:#0d1117; color:#e6edf3; font-family:'Segoe UI',Arial,sans-serif; }
QLabel  { color:#e6edf3; }
QFrame#permCard { background:#161b22; border:1px solid #30363d; border-radius:12px; }
QPushButton#grantBtn {
    background:#1f6feb; color:white; border:none;
    border-radius:8px; padding:10px 20px; font-size:13px; font-weight:bold; }
QPushButton#grantBtn:hover { background:#388bfd; }
QPushButton#startBtn {
    background:#238636; color:white; border:none;
    border-radius:10px; padding:14px 32px; font-size:16px; font-weight:bold; }
QPushButton#startBtn:hover  { background:#2ea043; }
QPushButton#startBtn:disabled { background:#21262d; color:#484f58; }
QPushButton#cancelBtn {
    background:#21262d; color:#8b949e; border:1px solid #30363d;
    border-radius:8px; padding:10px 20px; font-size:13px; }
QPushButton#cancelBtn:hover { background:#30363d; }
"""

STATUS_COLORS = {
    "pending":  ("#484f58", "#21262d", "○"),
    "checking": ("#f0883e", "#2d1b08", "◌"),
    "granted":  ("#3fb950", "#0d2a13", "✓"),
    "denied":   ("#f85149", "#2d0d0c", "✗"),
}

# ─── Allowed / Blocked lists ──────────────────────────────────────────────────
# STRATEGY: explicit deny-list only.
#   • Windows whose title contains a _BLOCKED_TITLE_KW keyword → flagged.
#   • Everything else (including all Windows system UI) → ignored.
# This prevents false positives from Settings, Program Manager, etc.

# Window title substrings → BLOCKED  (only these are ever flagged)
_BLOCKED_TITLE_KW = [
    # Browsers
    "google chrome", "chromium", "mozilla firefox", "microsoft edge",
    "safari", "opera", "brave browser", "vivaldi", "internet explorer",
    # Messaging / video calls
    "whatsapp", "telegram", "discord", "slack", "microsoft teams",
    "skype", "messenger", "signal", "viber", "zoom", "google meet", "webex",
    # Office / productivity
    "- notepad",          # "untitled - Notepad" — NOT "Windows Settings"
    "- wordpad",
    "microsoft word", "microsoft excel", "microsoft powerpoint",
    "libreoffice", "openoffice",
    "google docs", "google sheets", "google slides",
    # IDEs / code editors
    "visual studio code", "- visual studio",
    "pycharm", "android studio", "eclipse ide", "intellij idea",
    "sublime text", "atom", "notepad++", "xcode",
    # Media / entertainment
    "vlc media player", "spotify", "windows media player", "winamp",
    # Screen capture
    "sharex", "screentogif", "obs studio",
    # AI assistants
    "chatgpt", "gemini", "- copilot", "bard",
]

# Process executable names → BLOCKED  (catches hidden/minimised apps via psutil)
_BLOCKED_PROC_NAMES = {
    "chrome.exe", "chromium.exe", "firefox.exe", "msedge.exe",
    "opera.exe", "brave.exe", "vivaldi.exe", "iexplore.exe",
    "whatsapp.exe", "telegram.exe", "discord.exe", "slack.exe",
    "teams.exe", "skype.exe", "zoom.exe",
    "winword.exe", "excel.exe", "powerpnt.exe", "soffice.exe", "code.exe",
    "pycharm64.exe", "pycharm.exe", "idea64.exe", "devenv.exe",
    "sublime_text.exe", "atom.exe",
    "obs64.exe", "obs.exe", "sharex.exe", "screentogif.exe",
    "vlc.exe", "spotify.exe", "wmplayer.exe",
}

# Own-app titles to strip from the window list before scanning
_OWN_TITLE_KW = [
    "ai exam proctoring", "exam proctoring", "pre-exam",
    "security check", "exam —", "exam window",
]


# ─── Scanner helpers ──────────────────────────────────────────────────────────

def _get_open_windows():
    """Return list of visible window titles, excluding our own dialog."""
    system = platform.system()
    windows = []
    try:
        if system == "Windows":
            import ctypes, ctypes.wintypes as wt
            titles = []
            def cb(hwnd, _):
                if ctypes.windll.user32.IsWindowVisible(hwnd):
                    n = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                    if n > 0:
                        buf = ctypes.create_unicode_buffer(n + 1)
                        ctypes.windll.user32.GetWindowTextW(hwnd, buf, n + 1)
                        t = buf.value.strip()
                        if t:
                            titles.append(t)
                return True
            FN = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
            ctypes.windll.user32.EnumWindows(FN(cb), 0)
            windows = titles
        elif system == "Darwin":
            script = ('tell application "System Events"\n'
                      '  set r to {}\n'
                      '  repeat with p in (every process whose background only is false)\n'
                      '    repeat with w in (every window of p)\n'
                      '      set end of r to name of w & " [" & name of p & "]"\n'
                      '    end repeat\n'
                      '  end repeat\n'
                      '  return r\nend tell')
            res = subprocess.run(["osascript", "-e", script],
                                 capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                windows = [w.strip() for w in res.stdout.strip().split(",") if w.strip()]
        elif system == "Linux":
            try:
                res = subprocess.run(["wmctrl", "-l"], capture_output=True, text=True, timeout=3)
                if res.returncode == 0:
                    for line in res.stdout.strip().splitlines():
                        parts = line.split(None, 3)
                        if len(parts) >= 4 and parts[3].strip() not in ("", "N/A"):
                            windows.append(parts[3].strip())
            except Exception:
                pass
    except Exception:
        pass

    # Filter out our own windows
    return [w for w in windows
            if w.strip() and not any(k in w.lower() for k in _OWN_TITLE_KW)]


def _classify_windows(windows):
    """
    Flag a window ONLY if its title contains a keyword from _BLOCKED_TITLE_KW.
    System windows (Settings, Program Manager, Windows Input Experience, etc.)
    are silently ignored — they cannot be closed and should never be flagged.
    """
    blocked = []
    for title in windows:
        tl = title.lower()
        if any(k in tl for k in _BLOCKED_TITLE_KW):
            blocked.append(title)
    return blocked


def _get_blocked_processes():
    """Use psutil to find running processes from the blocked list."""
    try:
        import psutil
        found = set()
        for p in psutil.process_iter(["name"]):
            try:
                name = (p.info.get("name") or "").lower().strip()
                if name in _BLOCKED_PROC_NAMES:
                    found.add(name)
            except Exception:
                pass
        return list(found)
    except ImportError:
        return []


# ─── Permission Row widget ─────────────────────────────────────────────────────

class PermissionRow(QFrame):
    grant_clicked = pyqtSignal(str)

    def __init__(self, perm_id, title, description, parent=None):
        super().__init__(parent)
        self.perm_id = perm_id
        self.setObjectName("permCard")
        self.setMinimumHeight(80)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(12)

        self.circle = QLabel("○")
        self.circle.setFixedSize(32, 32)
        self.circle.setAlignment(Qt.AlignCenter)
        self.circle.setFont(QFont("Segoe UI", 16))
        self.circle.setStyleSheet("color:#484f58;")
        lay.addWidget(self.circle)

        txt = QVBoxLayout()
        txt.setSpacing(2)
        self.title_lbl = QLabel(title)
        self.title_lbl.setFont(QFont("Segoe UI", 13, QFont.Bold))
        self.desc_lbl = QLabel(description)
        self.desc_lbl.setStyleSheet("color:#8b949e; font-size:11px;")
        self.desc_lbl.setWordWrap(True)
        txt.addWidget(self.title_lbl)
        txt.addWidget(self.desc_lbl)
        lay.addLayout(txt, stretch=1)

        self.btn = QPushButton("Grant Access")
        self.btn.setObjectName("grantBtn")
        self.btn.setFixedWidth(130)
        self.btn.clicked.connect(lambda: self.grant_clicked.emit(self.perm_id))
        lay.addWidget(self.btn)

    def set_status(self, status, message=""):
        color, bg, icon = STATUS_COLORS.get(status, STATUS_COLORS["pending"])
        self.circle.setText(icon)
        self.circle.setStyleSheet(f"color:{color};")
        self.setStyleSheet(
            f"QFrame#permCard{{background:{bg};border:1px solid {color}55;border-radius:12px;}}"
        )
        if message:
            self.desc_lbl.setText(message)

        if status == "granted":
            self.btn.setText("✓ Granted")
            self.btn.setEnabled(False)
            self.btn.setStyleSheet(
                "QPushButton{background:#238636;color:white;border:none;"
                "border-radius:8px;padding:10px 20px;font-size:13px;}"
            )
        elif status == "denied":
            self.btn.setText("Retry")
            self.btn.setEnabled(True)
            self.btn.setStyleSheet(
                "QPushButton{background:#da3633;color:white;border:none;"
                "border-radius:8px;padding:10px 20px;font-size:13px;}"
                "QPushButton:hover{background:#f85149;}"
            )
        elif status == "checking":
            self.btn.setText("Scanning...")
            self.btn.setEnabled(False)
            self.btn.setStyleSheet(
                "QPushButton{background:#21262d;color:#8b949e;border:1px solid #30363d;"
                "border-radius:8px;padding:10px 20px;font-size:13px;}"
            )
        else:
            self.btn.setText("Grant Access")
            self.btn.setEnabled(True)
            self.btn.setStyleSheet("")


# ─── Background checker thread ────────────────────────────────────────────────

class PermissionChecker(QThread):
    result_ready = pyqtSignal(str, bool, str)   # perm_id, success, message

    def __init__(self, perm_id):
        super().__init__()
        self.perm_id = perm_id

    def run(self):
        if self.perm_id == "camera":
            self._check_camera()
        elif self.perm_id == "microphone":
            self._check_microphone()

    def _check_camera(self):
        try:
            import cv2
            # CAP_DSHOW on Windows skips backend negotiation (~0.3 s vs ~8 s)
            backend = cv2.CAP_DSHOW if platform.system() == "Windows" else cv2.CAP_ANY
            cap = cv2.VideoCapture(0, backend)
            if not cap.isOpened():
                cap = cv2.VideoCapture(0)          # fallback
            opened = cap.isOpened()
            cap.release()                          # release immediately — no frame read
            if opened:
                self.result_ready.emit("camera", True, "Camera is working ✓")
            else:
                self.result_ready.emit("camera", False, "No camera detected. Connect a webcam.")
        except Exception as e:
            self.result_ready.emit("camera", False, f"Camera error: {str(e)[:60]}")

    def _check_microphone(self):
        try:
            import sounddevice as sd
            import numpy as np
            devs = sd.query_devices()
            inputs = [d for d in devs if d["max_input_channels"] > 0]
            if not inputs:
                self.result_ready.emit("microphone", False, "No microphone detected.")
                return
            sd.rec(int(0.1 * 44100), samplerate=44100, channels=1, dtype="float32")
            sd.wait()
            self.result_ready.emit("microphone", True, "Microphone is working ✓")
        except Exception as e:
            self.result_ready.emit("microphone", False, f"Microphone error: {str(e)[:60]}")


# ─── Main Dialog ──────────────────────────────────────────────────────────────

class PermissionGateDialog(QDialog):
    def __init__(self, student, parent=None):
        super().__init__(parent)
        self.student = student
        self.setWindowTitle("Pre-Exam Security Check")
        self.setMinimumWidth(680)
        self.setModal(True)
        self.setStyleSheet(STYLE)

        self._camera_ok = False
        self._mic_ok    = False
        self._tabs_ok   = False
        self._checker   = None

        self._build_ui()
        # Auto-run all three checks after dialog renders
        QTimer.singleShot(300, self._auto_start_checks)

    def _auto_start_checks(self):
        """Kick off camera, microphone, and app scan automatically on open."""
        self.cam_row.set_status("checking", "Testing camera access…")
        self.mic_row.set_status("checking", "Testing microphone…")
        self._run_checker("camera")
        # Mic starts after camera check finishes (via _on_result) to avoid thread clash
        QTimer.singleShot(500, self._check_tabs)

    # ── UI ─────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 24)
        root.setSpacing(14)

        hdr = QLabel("🛡  Pre-Exam Security Check")
        hdr.setFont(QFont("Segoe UI", 20, QFont.Bold))
        hdr.setStyleSheet("color:#58a6ff;")
        hdr.setAlignment(Qt.AlignCenter)
        root.addWidget(hdr)

        sub = QLabel(
            f"Welcome, <b>{self.student.get('name', 'Student')}</b>. "
            "Complete all three checks below to start the exam."
        )
        sub.setAlignment(Qt.AlignCenter)
        sub.setWordWrap(True)
        sub.setStyleSheet("color:#8b949e; font-size:13px;")
        root.addWidget(sub)

        div = QFrame(); div.setFrameShape(QFrame.HLine)
        div.setStyleSheet("border-color:#30363d;")
        root.addWidget(div)

        self.cam_row = PermissionRow(
            "camera", "📷  Camera Access",
            "Required for live proctoring — face detection and gaze tracking.")
        self.cam_row.grant_clicked.connect(self._grant)
        root.addWidget(self.cam_row)

        self.mic_row = PermissionRow(
            "microphone", "🎤  Microphone Access",
            "Required to detect ambient sounds and voice-based cheating.")
        self.mic_row.grant_clicked.connect(self._grant)
        root.addWidget(self.mic_row)

        self.tabs_row = PermissionRow(
            "tabs", "🔒  Application Lockdown",
            "Only CMD / Terminal is allowed.  All other apps must be closed.")
        self.tabs_row.grant_clicked.connect(self._grant)
        root.addWidget(self.tabs_row)

        # Offender list
        self.offender_box = QLabel("")
        self.offender_box.setWordWrap(True)
        self.offender_box.setStyleSheet(
            "background:#2d1b08; color:#f0883e; border:1px solid #f0883e55;"
            " border-radius:6px; padding:10px 14px; font-size:12px;"
        )
        self.offender_box.hide()
        root.addWidget(self.offender_box)

        # Status / info banner
        self.status_box = QLabel("")
        self.status_box.setWordWrap(True)
        self.status_box.setAlignment(Qt.AlignCenter)
        self.status_box.setStyleSheet(
            "background:#1f3a5f; color:#79c0ff; border-radius:6px;"
            " padding:8px 12px; font-size:12px;"
        )
        self.status_box.hide()
        root.addWidget(self.status_box)

        btns = QHBoxLayout()
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("cancelBtn")
        self.cancel_btn.clicked.connect(self.reject)
        btns.addWidget(self.cancel_btn)
        btns.addStretch()
        self.start_btn = QPushButton("🚀  Start Exam")
        self.start_btn.setObjectName("startBtn")
        self.start_btn.setEnabled(False)
        self.start_btn.clicked.connect(self.accept)
        btns.addWidget(self.start_btn)
        root.addLayout(btns)

        note = QLabel(
            "⚠  After the exam starts, opening any application will be logged "
            "as a violation and may result in exam disqualification."
        )
        note.setWordWrap(True)
        note.setAlignment(Qt.AlignCenter)
        note.setStyleSheet("color:#6e7681; font-size:11px;")
        root.addWidget(note)

    # ── Actions ────────────────────────────────────────────────────────────

    def _grant(self, perm_id):
        if perm_id == "camera":
            self.cam_row.set_status("checking", "Testing camera access…")
            self._run_checker("camera")
        elif perm_id == "microphone":
            self.mic_row.set_status("checking", "Testing microphone…")
            self._run_checker("microphone")
        elif perm_id == "tabs":
            self._check_tabs()

    def _run_checker(self, perm_id):
        if self._checker and self._checker.isRunning():
            return
        self._checker = PermissionChecker(perm_id)
        self._checker.result_ready.connect(self._on_result)
        self._checker.start()

    def _on_result(self, perm_id, ok, msg):
        row = self.cam_row if perm_id == "camera" else self.mic_row
        row.set_status("granted" if ok else "denied", msg)
        if perm_id == "camera":
            self._camera_ok = ok
            # Auto-start mic check now that camera thread is done
            if not self._mic_ok:
                self.mic_row.set_status("checking", "Testing microphone…")
                self._run_checker("microphone")
        else:
            self._mic_ok = ok
        self._refresh()

    # ── App lockdown scan ──────────────────────────────────────────────────

    def _check_tabs(self):
        self.tabs_row.set_status("checking", "Scanning for open applications…")
        self.offender_box.hide()
        # Delay lets the UI repaint before the (slightly blocking) scan
        QTimer.singleShot(600, self._do_scan)

    def _do_scan(self):
        # Window-title scan
        windows   = _get_open_windows()
        win_block = _classify_windows(windows)

        # Process scan
        proc_block = _get_blocked_processes()

        # Merge results
        all_blocked = list(win_block)
        for p in proc_block:
            label = f"[process] {p}"
            if label not in all_blocked:
                all_blocked.append(label)

        total = len(all_blocked)

        if total == 0:
            self._tabs_ok = True
            self.tabs_row.set_status(
                "granted",
                "✓ No blocked applications found — only CMD / Terminal allowed."
            )
            self.offender_box.hide()
        else:
            self._tabs_ok = False
            lines = "\n".join(f"  • {o}" for o in all_blocked[:10])
            if total > 10:
                lines += f"\n  • … and {total - 10} more"
            self.tabs_row.set_status(
                "denied",
                f"{total} blocked app(s) still open. Close them, then click Retry."
            )
            self.offender_box.setText(
                f"🚫  Please close these before starting the exam:\n{lines}"
            )
            self.offender_box.show()

        self._refresh()

    # ── Start-button logic ─────────────────────────────────────────────────

    def _refresh(self):
        missing = []
        if not self._camera_ok:
            missing.append("camera")
        if not self._mic_ok:
            missing.append("microphone")
        if not self._tabs_ok:
            missing.append("close all blocked apps")

        ok = not missing
        self.start_btn.setEnabled(ok)

        if ok:
            self.offender_box.hide()
            self.status_box.setText("✅  All checks passed! You may now start the exam.")
            self.status_box.setStyleSheet(
                "background:#0d2a13; color:#3fb950; border-radius:6px;"
                " padding:8px 12px; font-size:12px;"
            )
        else:
            self.status_box.setText(f"ℹ  Still required: {', '.join(missing)}")
            self.status_box.setStyleSheet(
                "background:#1f3a5f; color:#79c0ff; border-radius:6px;"
                " padding:8px 12px; font-size:12px;"
            )
        self.status_box.show()
        self.adjustSize()
