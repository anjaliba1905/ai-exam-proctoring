# ai_modules/intent_detector.py - Intent Detection Layer
# Analyzes WHY cheating might happen, not just WHAT happened.
# Uses pattern analysis over a rolling window of violation events.

import time
from collections import deque
from typing import List, Dict, Optional, Tuple


# Intent categories with their triggering patterns and descriptions
INTENT_PATTERNS = {
    "coordinated_communication": {
        "description": "Student may be communicating with someone outside",
        "required_violations": ["gaze_away", "audio_alert"],
        "window_seconds": 30,
        "min_count": 2,
        "risk_boost": 25,
        "color": "#f0883e",
    },
    "external_device_use": {
        "description": "Student likely using an external device for answers",
        "required_violations": ["phone_detected", "gaze_away"],
        "window_seconds": 20,
        "min_count": 1,
        "risk_boost": 35,
        "color": "#f85149",
    },
    "impersonation_attempt": {
        "description": "Another person may be taking the exam",
        "required_violations": ["multiple_faces", "no_face"],
        "window_seconds": 60,
        "min_count": 2,
        "risk_boost": 40,
        "color": "#f85149",
    },
    "off_screen_consultation": {
        "description": "Student is systematically looking away — possibly reading notes",
        "required_violations": ["gaze_away", "tab_switch"],
        "window_seconds": 45,
        "min_count": 3,
        "risk_boost": 20,
        "color": "#f0883e",
    },
    "environment_scanning": {
        "description": "Repetitive scanning behavior — checking surroundings before cheating",
        "required_violations": ["gaze_away"],
        "window_seconds": 20,
        "min_count": 4,
        "risk_boost": 15,
        "color": "#d29922",
    },
    "pre_cheat_positioning": {
        "description": "Student repositioning — may be preparing hidden device/notes",
        "required_violations": ["no_face", "audio_alert"],
        "window_seconds": 30,
        "min_count": 2,
        "risk_boost": 20,
        "color": "#d29922",
    },
}


class IntentDetector:
    """
    Intent Detection Layer.

    Maintains a rolling 60-second event buffer of violation signals.
    On each new violation, analyses ALL pattern windows to determine
    whether the cluster of behaviors suggests a specific cheating intent.

    Returns:
        List of active intents: [{name, description, risk_boost, color, confidence}]
    """

    def __init__(self, intent_callback=None):
        """
        Args:
            intent_callback: callable(intent_name, description, risk_boost)
                             called whenever a new intent is detected
        """
        self.intent_callback = intent_callback
        # Rolling buffer of (timestamp, violation_type) tuples
        self._event_buffer: deque = deque(maxlen=500)
        # Active intents currently flagged
        self._active_intents: Dict[str, dict] = {}
        # Cooldown per intent to avoid duplicate callbacks
        self._last_intent_fired: Dict[str, float] = {}
        self._intent_cooldown = 15  # seconds between repeated intent alerts

    def record_violation(self, vtype: str) -> List[dict]:
        """
        Called every time a violation fires.
        Adds to buffer, then analyses all patterns.

        Returns: list of currently active intents
        """
        now = time.time()
        self._event_buffer.append((now, vtype))
        self._prune_old_events(now)
        return self._analyse(now)

    def get_active_intents(self) -> List[dict]:
        """Returns currently active intents (call periodically from UI)."""
        now = time.time()
        self._prune_old_events(now)
        return list(self._active_intents.values())

    # ─── Internal ──────────────────────────────────────────────────────────

    def _prune_old_events(self, now: float):
        """Remove events older than the longest pattern window."""
        cutoff = now - 120  # keep 2 minutes max
        while self._event_buffer and self._event_buffer[0][0] < cutoff:
            self._event_buffer.popleft()

    def _analyse(self, now: float) -> List[dict]:
        """Check each pattern against the recent event buffer."""
        new_active = {}

        for intent_name, pattern in INTENT_PATTERNS.items():
            window_start = now - pattern["window_seconds"]
            required = set(pattern["required_violations"])
            min_count = pattern["min_count"]

            # Count violations within the pattern's time window
            recent_events = [
                (ts, vt) for ts, vt in self._event_buffer
                if ts >= window_start
            ]

            # Check if all required violation types are present
            seen_types = {vt for _, vt in recent_events}
            if not required.issubset(seen_types):
                # Pattern not matched — clear it if it was active
                if intent_name in self._active_intents:
                    del self._active_intents[intent_name]
                continue

            # Check count threshold (count all events of required types)
            qualifying_count = sum(
                1 for _, vt in recent_events if vt in required
            )
            if qualifying_count < min_count:
                if intent_name in self._active_intents:
                    del self._active_intents[intent_name]
                continue

            # Compute confidence (0-100) based on event density
            max_expected = min_count * 3
            confidence = min(100, int((qualifying_count / max_expected) * 100))

            intent_data = {
                "name": intent_name,
                "label": intent_name.replace("_", " ").title(),
                "description": pattern["description"],
                "risk_boost": pattern["risk_boost"],
                "color": pattern["color"],
                "confidence": confidence,
                "detected_at": now,
            }
            new_active[intent_name] = intent_data

            # Fire callback with cooldown
            last_fired = self._last_intent_fired.get(intent_name, 0)
            if now - last_fired >= self._intent_cooldown:
                self._last_intent_fired[intent_name] = now
                if self.intent_callback:
                    self.intent_callback(
                        intent_name,
                        pattern["description"],
                        pattern["risk_boost"],
                        confidence,
                    )

        self._active_intents = new_active
        return list(self._active_intents.values())

    def get_total_risk_boost(self) -> float:
        """Returns cumulative risk boost from all active intents."""
        return sum(i["risk_boost"] for i in self._active_intents.values())

    def clear(self):
        """Reset all state."""
        self._event_buffer.clear()
        self._active_intents.clear()
        self._last_intent_fired.clear()
