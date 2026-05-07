# monitoring/screen_monitor.py  –  Window-focus / tab-switch detection
# FIX v3:
#   • Runs on main thread via QTimer (Qt forbids isActiveWindow from QThread).
#   • Also uses Win32 GetForegroundWindow to detect switch even when our window
#     is minimised, so no false "focus OK" readings.
#   • Screenshot key (PrintScreen, Win+Shift+S) is intercepted and blocked
#     during the exam using a low-level keyboard hook on Windows.

import time, platform
from PyQt5.QtCore import QObject, QTimer, pyqtSignal
from config import SCREEN_CHECK_INTERVAL, VIOLATION_LOG_COOLDOWN


class ScreenMonitor(QObject):
    """
    Detects when the student switches away from the exam window.
    Uses a QTimer on the main thread — never a QThread.
    Also installs a screenshot-blocking keyboard hook on Windows.
    """

    focus_status     = pyqtSignal(bool)      # True = has focus
    violation_signal = pyqtSignal(str, str)  # (type, details)

    def __init__(self, target_window=None, parent=None):
        super().__init__(parent)
        self.target_window    = target_window
        self._last_viol_log   = 0
        self._focus_lost_since = None
        self._timer           = None
        self._hook_thread     = None   # screenshot-blocker thread handle

    # ── Public API ─────────────────────────────────────────────────────────

    def start(self):
        """Call from main thread after ExamWindow is shown."""
        self._install_screenshot_blocker()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._check_focus)
        self._timer.start(SCREEN_CHECK_INTERVAL)

    def stop(self):
        if self._timer:
            self._timer.stop()
            self._timer = None
        self._remove_screenshot_blocker()

    # ── Focus check ────────────────────────────────────────────────────────

    def _check_focus(self):
        if self.target_window is None:
            return

        has_focus = self._window_has_focus()
        self.focus_status.emit(has_focus)

        now = time.time()
        if not has_focus:
            if self._focus_lost_since is None:
                self._focus_lost_since = now
            elapsed = now - self._focus_lost_since
            if now - self._last_viol_log >= VIOLATION_LOG_COOLDOWN:
                self._last_viol_log = now
                self.violation_signal.emit(
                    "tab_switch",
                    f"Exam window lost focus for {elapsed:.1f}s"
                )
        else:
            self._focus_lost_since = None

    def _window_has_focus(self):
        """
        More reliable than isActiveWindow() alone:
        On Windows, also check GetForegroundWindow so we catch minimised-window
        switches that Qt misses.
        """
        if not self.target_window.isActiveWindow():
            return False
        if platform.system() == "Windows":
            try:
                import ctypes
                fg_hwnd = ctypes.windll.user32.GetForegroundWindow()
                our_hwnd = int(self.target_window.winId())
                return fg_hwnd == our_hwnd
            except Exception:
                pass
        return True

    # ── Screenshot blocker (Windows only) ──────────────────────────────────

    def _install_screenshot_blocker(self):
        """
        Install a low-level WH_KEYBOARD_LL hook that swallows
        VK_SNAPSHOT (PrintScreen) and Win+Shift+S.
        Runs in a daemon thread so it doesn't block the main thread.
        """
        if platform.system() != "Windows":
            return
        try:
            import threading
            self._hook_thread = threading.Thread(
                target=self._run_hook, daemon=True
            )
            self._hook_thread.start()
        except Exception as e:
            print(f"[ScreenMonitor] Screenshot blocker start error: {e}")

    def _remove_screenshot_blocker(self):
        # The daemon thread exits automatically; just clear the reference
        self._hook_thread = None

    def _run_hook(self):
        """Low-level keyboard hook — blocks PrintScreen & Win+Shift+S."""
        try:
            import ctypes, ctypes.wintypes as wt
            import threading

            VK_SNAPSHOT = 0x2C   # PrintScreen
            VK_S        = 0x53
            VK_SHIFT    = 0x10
            VK_LWIN     = 0x5B
            VK_RWIN     = 0x5C

            WH_KEYBOARD_LL = 13
            WM_KEYDOWN     = 0x0100
            WM_SYSKEYDOWN  = 0x0104

            class KBDLLHOOKSTRUCT(ctypes.Structure):
                _fields_ = [
                    ("vkCode",      wt.DWORD),
                    ("scanCode",    wt.DWORD),
                    ("flags",       wt.DWORD),
                    ("time",        wt.DWORD),
                    ("dwExtraInfo", ctypes.POINTER(wt.ULONG)),
                ]

            HOOKPROC = ctypes.WINFUNCTYPE(
                ctypes.c_long, ctypes.c_int, wt.WPARAM, ctypes.POINTER(KBDLLHOOKSTRUCT)
            )

            def low_level_handler(n_code, w_param, l_param):
                if n_code >= 0 and w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
                    vk = l_param.contents.vkCode
                    # Block PrintScreen
                    if vk == VK_SNAPSHOT:
                        return 1   # swallow
                    # Block Win+Shift+S  (Snipping Tool)
                    state = ctypes.windll.user32.GetAsyncKeyState
                    win_down   = (state(VK_LWIN) | state(VK_RWIN)) & 0x8000
                    shift_down = state(VK_SHIFT) & 0x8000
                    if vk == VK_S and win_down and shift_down:
                        return 1   # swallow
                return ctypes.windll.user32.CallNextHookEx(None, n_code, w_param, l_param)

            self._hook_cb = HOOKPROC(low_level_handler)   # keep reference alive
            hook = ctypes.windll.user32.SetWindowsHookExW(
                WH_KEYBOARD_LL, self._hook_cb, None, 0
            )
            if not hook:
                print("[ScreenMonitor] SetWindowsHookEx failed — screenshots not blocked.")
                return

            # Message loop so the hook stays active
            msg = wt.MSG()
            while ctypes.windll.user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
                ctypes.windll.user32.TranslateMessage(ctypes.byref(msg))
                ctypes.windll.user32.DispatchMessageW(ctypes.byref(msg))

            ctypes.windll.user32.UnhookWindowsHookEx(hook)

        except Exception as e:
            print(f"[ScreenMonitor] Hook thread error: {e}")
