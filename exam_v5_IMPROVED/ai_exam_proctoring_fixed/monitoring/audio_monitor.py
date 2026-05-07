# monitoring/audio_monitor.py - Microphone audio analysis thread

import numpy as np
import time
from PyQt5.QtCore import QThread, pyqtSignal

from config import (AUDIO_SAMPLE_RATE, AUDIO_CHUNK_DURATION,
                    AUDIO_ENERGY_THRESHOLD, AUDIO_SPEECH_DURATION,
                    VIOLATION_LOG_COOLDOWN)


class AudioMonitor(QThread):
    """
    Captures microphone input using sounddevice and analyses RMS energy.
    Emits violations when sustained speech/noise is detected.
    """

    audio_status     = pyqtSignal(str, float)   # (status_text, rms_energy)
    violation_signal = pyqtSignal(str, str)      # (type, details)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False
        self._speech_since = None
        self._last_violation_log = 0

    def run(self):
        self._running = True
        try:
            import sounddevice as sd
            # librosa import removed — it was imported but never used
        except ImportError:
            self.audio_status.emit("sounddevice not installed", 0.0)
            return

        chunk_size = int(AUDIO_SAMPLE_RATE * AUDIO_CHUNK_DURATION)

        while self._running:
            try:
                audio = sd.rec(chunk_size, samplerate=AUDIO_SAMPLE_RATE,
                               channels=1, dtype='float32')
                sd.wait()
                if not self._running:
                    break
                samples = audio.flatten()
                rms = float(np.sqrt(np.mean(samples ** 2)))
                self._analyse(rms)
            except Exception as e:
                self.audio_status.emit(f"Audio error: {e}", 0.0)
                self.msleep(3000)

    def _analyse(self, rms: float):
        now = time.time()
        if rms > AUDIO_ENERGY_THRESHOLD:
            if self._speech_since is None:
                self._speech_since = now
            elapsed = now - self._speech_since
            status = f"AUDIO ALERT! Speech detected ({elapsed:.1f}s)"
            self.audio_status.emit(status, rms)

            if elapsed >= AUDIO_SPEECH_DURATION:
                if now - self._last_violation_log >= VIOLATION_LOG_COOLDOWN:
                    self._last_violation_log = now
                    self.violation_signal.emit(
                        "audio_alert",
                        f"Continuous speech/noise for {elapsed:.1f}s (RMS={rms:.4f})"
                    )
        else:
            self._speech_since = None
            self.audio_status.emit("Audio: Quiet", rms)

    def stop(self):
        self._running = False
        self.wait(5000)  # Max 5s wait — prevents hang if sounddevice blocks
