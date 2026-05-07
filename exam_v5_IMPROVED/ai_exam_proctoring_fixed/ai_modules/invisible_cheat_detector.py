# ai_modules/invisible_cheat_detector.py - Invisible Cheating Detection
# Detects HIDDEN devices and OFF-SCREEN help WITHOUT directly seeing them.
# Uses behavioral inference from observable signals (gaze, audio, timing, motion).

import time
import math
from collections import deque
from typing import Dict, List, Optional, Tuple


# ─── Signal Definitions ────────────────────────────────────────────────────────
# Each invisible cheat type inferred from combinations of VISIBLE signals.

INVISIBLE_CHEAT_SIGNATURES = {

    "hidden_earpiece": {
        "label": "Hidden Earpiece Detected",
        "description": "Student may be receiving spoken answers via hidden earpiece",
        "signals": {
            # Low audio from mic (student not speaking but reacting)
            # Combined with rhythmic look-aways (listening and re-reading)
            "gaze_away_frequency": {"min": 3, "window": 30},   # ≥3 gaze-aways in 30s
            "audio_silence_with_response": True,                # mic quiet, student reacts
        },
        "required_patterns": ["gaze_rhythm", "no_audio_but_reacting"],
        "confidence_base": 60,
        "risk_score": 80,
        "color": "#f85149",
    },

    "hidden_phone_under_desk": {
        "label": "Hidden Phone Under Desk",
        "description": "Student likely consulting a hidden phone below camera frame",
        "signals": {
            "gaze_down_frequency": {"min": 2, "window": 20},    # looking DOWN repeatedly
            "no_face_brief":       {"min": 1, "window": 15},    # brief head tilt
        },
        "required_patterns": ["gaze_down_pattern", "brief_disappear"],
        "confidence_base": 65,
        "risk_score": 85,
        "color": "#f85149",
    },

    "offscreen_notes": {
        "label": "Off-Screen Notes / Cheat Sheet",
        "description": "Student is reading from materials outside camera view",
        "signals": {
            "gaze_away_directional": {"min": 2, "window": 25},  # consistent direction
            "consistent_gaze_angle": True,                       # always same direction
        },
        "required_patterns": ["directional_gaze", "no_phone_visible"],
        "confidence_base": 55,
        "risk_score": 70,
        "color": "#f0883e",
    },

    "remote_assistance": {
        "label": "Remote / Off-Screen Assistance",
        "description": "Someone outside camera range is assisting the student",
        "signals": {
            "audio_whisper_pattern": {"min": 1, "window": 30},  # low-level audio bursts
            "gaze_side_consistent": {"min": 3, "window": 40},   # looking sideways
        },
        "required_patterns": ["side_gaze", "audio_present"],
        "confidence_base": 58,
        "risk_score": 75,
        "color": "#f0883e",
    },

    "smart_glasses_or_contact_lens": {
        "label": "Wearable Tech (Smart Glasses/Lens)",
        "description": "Student appears to be reading overlaid information — minimal eye movement despite sustained gaze",
        "signals": {
            "gaze_stable_long": {"min_seconds": 15},            # staring without blinking much
            "no_device_visible": True,                           # no phone detected
            "answer_timing_fast": True,                          # suspiciously fast answers
        },
        "required_patterns": ["prolonged_fixed_gaze", "no_visible_device"],
        "confidence_base": 40,
        "risk_score": 60,
        "color": "#d29922",
    },
}


class InvisibleCheatDetector:
    """
    Invisible Cheating Detection Engine.

    Infers hidden cheating behaviors from OBSERVABLE signals:
    - Gaze patterns (direction, frequency, duration)
    - Audio patterns (presence/absence, timing)
    - Motion indicators (brief no-face, head tilt)
    - Temporal patterns (when violations cluster)

    Does NOT require direct camera evidence of the cheating device.
    """

    HISTORY_WINDOW = 120  # seconds of history to maintain

    def __init__(self, alert_callback=None):
        """
        Args:
            alert_callback: callable(cheat_type, description, confidence, risk_score)
        """
        self.alert_callback = alert_callback

        # Event buffers
        self._gaze_events: deque = deque(maxlen=200)    # (ts, direction)
        self._audio_events: deque = deque(maxlen=200)   # (ts, rms, is_speech)
        self._face_events:  deque = deque(maxlen=200)   # (ts, face_count)
        self._phone_events: deque = deque(maxlen=50)    # (ts, detected)

        # Active detections: {cheat_type: {confidence, last_seen, ...}}
        self._active: Dict[str, dict] = {}
        self._last_alert: Dict[str, float] = {}
        self._alert_cooldown = 30  # seconds

        # Internal pattern state
        self._gaze_direction_history: deque = deque(maxlen=50)  # last 50 gaze directions
        self._stable_gaze_start: Optional[float] = None

    # ─── Public Feed Methods ───────────────────────────────────────────────

    def feed_gaze(self, direction: str, looking_away: bool):
        """Feed current gaze data."""
        now = time.time()
        self._gaze_events.append((now, direction, looking_away))
        self._gaze_direction_history.append(direction)
        if looking_away:
            self._stable_gaze_start = None
        else:
            if self._stable_gaze_start is None:
                self._stable_gaze_start = now

    def feed_audio(self, rms: float, is_speech: bool):
        """Feed current audio data."""
        now = time.time()
        self._audio_events.append((now, rms, is_speech))

    def feed_face(self, face_count: int):
        """Feed current face count."""
        now = time.time()
        self._face_events.append((now, face_count))

    def feed_phone(self, detected: bool):
        """Feed phone detection state."""
        now = time.time()
        self._phone_events.append((now, detected))

    def analyse(self) -> List[dict]:
        """
        Run full invisible cheat analysis.
        Call every 2-5 seconds from monitoring loop.

        Returns: list of active invisible cheat detections.
        """
        now = time.time()
        self._prune(now)

        detections = []

        # Run each inference rule
        result = self._detect_hidden_earpiece(now)
        if result: detections.append(result)

        result = self._detect_hidden_phone(now)
        if result: detections.append(result)

        result = self._detect_offscreen_notes(now)
        if result: detections.append(result)

        result = self._detect_remote_assistance(now)
        if result: detections.append(result)

        result = self._detect_wearable_tech(now)
        if result: detections.append(result)

        # Update active detections and fire callbacks
        self._active = {d["type"]: d for d in detections}
        for det in detections:
            last = self._last_alert.get(det["type"], 0)
            if now - last >= self._alert_cooldown:
                self._last_alert[det["type"]] = now
                if self.alert_callback:
                    self.alert_callback(
                        det["type"],
                        det["description"],
                        det["confidence"],
                        det["risk_score"],
                    )

        return detections

    def get_active_detections(self) -> List[dict]:
        return list(self._active.values())

    def get_max_risk(self) -> float:
        if not self._active:
            return 0.0
        return max(d["risk_score"] for d in self._active.values())

    # ─── Inference Rules ───────────────────────────────────────────────────

    def _detect_hidden_earpiece(self, now: float) -> Optional[dict]:
        """
        Hidden earpiece: student is quiet on mic but shows rhythmic
        gaze-away patterns consistent with listening and responding.
        """
        window = 30
        gaze_aways = self._count_gaze_away(now, window)
        audio_silent = self._is_mostly_silent(now, window, threshold=0.015)
        has_face = self._has_stable_face(now, window, min_ratio=0.7)

        if gaze_aways >= 3 and audio_silent and has_face:
            # Check rhythmic pattern (gaze-aways spaced 5-15s apart)
            rhythmic = self._is_rhythmic_gaze(now, window, min_interval=4, max_interval=18)
            confidence = 55 + (15 if rhythmic else 0) + min(15, gaze_aways * 3)
            if confidence >= 60:
                return self._make_detection(
                    "hidden_earpiece",
                    INVISIBLE_CHEAT_SIGNATURES["hidden_earpiece"],
                    confidence,
                )
        return None

    def _detect_hidden_phone(self, now: float) -> Optional[dict]:
        """
        Hidden phone under desk: brief head-dips (no_face) + downward gaze.
        The phone isn't in camera frame but behavior reveals it.
        """
        window = 25
        # Count brief no-face events (< 3 seconds each)
        brief_dips = self._count_brief_no_face(now, window, max_duration=4)
        phone_visible = self._phone_recently_detected(now, window)

        if phone_visible:
            return None  # Phone IS visible — not hidden

        gaze_aways = self._count_gaze_away(now, window)
        downward_gaze = self._count_directional_gaze(now, window, "DOWN")

        if (brief_dips >= 1 and gaze_aways >= 2) or downward_gaze >= 2:
            confidence = 45 + (brief_dips * 12) + (downward_gaze * 10)
            confidence = min(90, confidence)
            if confidence >= 55:
                return self._make_detection(
                    "hidden_phone_under_desk",
                    INVISIBLE_CHEAT_SIGNATURES["hidden_phone_under_desk"],
                    confidence,
                )
        return None

    def _detect_offscreen_notes(self, now: float) -> Optional[dict]:
        """
        Off-screen notes: student consistently gazes in ONE direction
        (left or right) suggesting a cheat sheet beside them.
        """
        window = 35
        left_count  = self._count_directional_gaze(now, window, "LEFT")
        right_count = self._count_directional_gaze(now, window, "RIGHT")
        dominant = max(left_count, right_count)
        other    = min(left_count, right_count)

        phone_visible = self._phone_recently_detected(now, window)
        if phone_visible:
            return None  # More likely phone — handled elsewhere

        # Strong directional preference (not balanced looking)
        if dominant >= 3 and dominant >= other * 2:
            confidence = 40 + min(35, dominant * 8) - (other * 5)
            confidence = max(0, min(85, confidence))
            if confidence >= 50:
                return self._make_detection(
                    "offscreen_notes",
                    INVISIBLE_CHEAT_SIGNATURES["offscreen_notes"],
                    confidence,
                )
        return None

    def _detect_remote_assistance(self, now: float) -> Optional[dict]:
        """
        Remote assistance: someone out of frame is helping.
        Signal: side-gaze + audio (listening/responding to someone off-camera).
        """
        window = 40
        side_gaze = (self._count_directional_gaze(now, window, "LEFT") +
                     self._count_directional_gaze(now, window, "RIGHT"))
        has_audio  = self._has_audio_presence(now, window, min_ratio=0.15)
        multiple_faces = self._had_multiple_faces(now, window)

        if side_gaze >= 3 and (has_audio or multiple_faces):
            confidence = 40 + (side_gaze * 6) + (15 if has_audio else 0) + (20 if multiple_faces else 0)
            confidence = min(85, confidence)
            if confidence >= 55:
                return self._make_detection(
                    "remote_assistance",
                    INVISIBLE_CHEAT_SIGNATURES["remote_assistance"],
                    confidence,
                )
        return None

    def _detect_wearable_tech(self, now: float) -> Optional[dict]:
        """
        Smart glasses / AR lens: student stares at screen for very long without
        normal reading eye movement, no device visible.
        """
        # Check for prolonged stable gaze (≥ 15 seconds)
        if self._stable_gaze_start is None:
            return None
        stable_duration = now - self._stable_gaze_start

        if stable_duration < 15:
            return None

        phone_visible = self._phone_recently_detected(now, 20)
        if phone_visible:
            return None

        # No gaze-away at all during stable period — unnatural
        gaze_aways_recent = self._count_gaze_away(now, min(stable_duration, 60))
        if gaze_aways_recent > 0:
            return None  # Normal reading — has occasional gaze shifts

        confidence = min(70, 35 + int(stable_duration / 3))
        if confidence >= 45:
            sig = INVISIBLE_CHEAT_SIGNATURES["smart_glasses_or_contact_lens"]
            return self._make_detection("smart_glasses_or_contact_lens", sig, confidence)
        return None

    # ─── Helper Utilities ──────────────────────────────────────────────────

    def _make_detection(self, type_key: str, sig: dict, confidence: float) -> dict:
        return {
            "type": type_key,
            "label": sig["label"],
            "description": sig["description"],
            "confidence": round(confidence, 1),
            "risk_score": sig["risk_score"],
            "color": sig["color"],
            "detected_at": time.time(),
        }

    def _prune(self, now: float):
        cutoff = now - self.HISTORY_WINDOW
        for buf in [self._gaze_events, self._audio_events,
                    self._face_events, self._phone_events]:
            while buf and buf[0][0] < cutoff:
                buf.popleft()

    def _count_gaze_away(self, now: float, window: float) -> int:
        cutoff = now - window
        # Count transition TO looking_away (rising edges)
        events = [(ts, d, la) for ts, d, la in self._gaze_events if ts >= cutoff]
        count = 0
        prev_away = False
        for _, _, la in events:
            if la and not prev_away:
                count += 1
            prev_away = la
        return count

    def _count_directional_gaze(self, now: float, window: float, direction: str) -> int:
        cutoff = now - window
        return sum(
            1 for ts, d, la in self._gaze_events
            if ts >= cutoff and direction in d.upper() and la
        )

    def _is_mostly_silent(self, now: float, window: float, threshold: float = 0.015) -> bool:
        cutoff = now - window
        recent = [(rms, sp) for ts, rms, sp in self._audio_events if ts >= cutoff]
        if not recent:
            return True
        silent = sum(1 for rms, _ in recent if rms < threshold)
        return silent / len(recent) >= 0.75

    def _has_audio_presence(self, now: float, window: float, min_ratio: float) -> bool:
        cutoff = now - window
        recent = [rms for ts, rms, _ in self._audio_events if ts >= cutoff]
        if not recent:
            return False
        active = sum(1 for r in recent if r > 0.015)
        return active / len(recent) >= min_ratio

    def _has_stable_face(self, now: float, window: float, min_ratio: float = 0.7) -> bool:
        cutoff = now - window
        recent = [fc for ts, fc in self._face_events if ts >= cutoff]
        if not recent:
            return False
        has_face = sum(1 for fc in recent if fc == 1)
        return has_face / len(recent) >= min_ratio

    def _count_brief_no_face(self, now: float, window: float, max_duration: float = 4) -> int:
        """Count brief gaps (no_face events < max_duration seconds)."""
        cutoff = now - window
        events = [(ts, fc) for ts, fc in self._face_events if ts >= cutoff]
        count = 0
        gap_start = None
        for ts, fc in events:
            if fc == 0 and gap_start is None:
                gap_start = ts
            elif fc > 0 and gap_start is not None:
                duration = ts - gap_start
                if duration < max_duration:
                    count += 1
                gap_start = None
        return count

    def _phone_recently_detected(self, now: float, window: float) -> bool:
        cutoff = now - window
        return any(det for ts, det in self._phone_events if ts >= cutoff and det)

    def _had_multiple_faces(self, now: float, window: float) -> bool:
        cutoff = now - window
        return any(fc > 1 for ts, fc in self._face_events if ts >= cutoff)

    def _is_rhythmic_gaze(self, now: float, window: float,
                           min_interval: float, max_interval: float) -> bool:
        """Check if gaze-away events are spaced rhythmically (consistent intervals)."""
        cutoff = now - window
        away_times = [
            ts for ts, _, la in self._gaze_events
            if ts >= cutoff and la
        ]
        if len(away_times) < 3:
            return False
        intervals = [away_times[i+1] - away_times[i]
                     for i in range(len(away_times) - 1)]
        within_range = [min_interval <= iv <= max_interval for iv in intervals]
        return sum(within_range) >= len(intervals) * 0.6

    def clear(self):
        self._gaze_events.clear()
        self._audio_events.clear()
        self._face_events.clear()
        self._phone_events.clear()
        self._active.clear()
        self._last_alert.clear()
        self._stable_gaze_start = None
