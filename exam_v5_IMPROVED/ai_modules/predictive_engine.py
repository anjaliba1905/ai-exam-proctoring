# ai_modules/predictive_engine.py - Behavioral Prediction Engine
# Uses the past 30–60 seconds of behavior to forecast the NEXT likely action.
# This is like AI forecasting cheating BEFORE it fully occurs.

import time
import math
from collections import deque
from typing import List, Dict, Tuple, Optional


# Transition probabilities based on behavioral studies.
# Structure: {current_state: [(next_state, probability, window_seconds)]}
# These represent what behavior typically follows a given violation pattern.
BEHAVIORAL_TRANSITIONS = {
    "gaze_away": [
        ("phone_use_imminent", 0.60, 15),       # Looking away → phone likely next
        ("note_consultation",  0.35, 20),        # Looking away → notes next
        ("return_normal",      0.25, 10),        # May just be normal distraction
    ],
    "audio_alert": [
        ("coordinated_cheat",  0.55, 20),        # Speech → coordinating with someone
        ("stress_response",    0.30, 15),        # Talking to self under stress
    ],
    "tab_switch": [
        ("external_resource",  0.70, 10),        # Tab switch → looking something up
        ("communication_app",  0.45, 15),        # Could be messaging
    ],
    "phone_detected": [
        ("answer_lookup",      0.80, 10),        # Phone → directly looking up answers
        ("communication_app",  0.50, 15),        # Could be messaging partner
    ],
    "multiple_faces": [
        ("impersonation",      0.65, 30),        # Extra person → identity fraud
        ("coaching_session",   0.70, 20),        # Being coached live
    ],
    "no_face": [
        ("repositioning",      0.40, 10),        # Short absence — repositioning
        ("device_retrieval",   0.55, 20),        # Longer absence — getting device
    ],
}

# Risk level of each predicted action
PREDICTION_RISK = {
    "phone_use_imminent": ("HIGH",    "#f85149", 85),
    "coordinated_cheat":  ("HIGH",    "#f85149", 90),
    "answer_lookup":      ("HIGH",    "#f85149", 88),
    "impersonation":      ("CRITICAL","#ff0000", 95),
    "coaching_session":   ("CRITICAL","#ff0000", 92),
    "external_resource":  ("HIGH",    "#f85149", 75),
    "communication_app":  ("HIGH",    "#f85149", 78),
    "note_consultation":  ("MEDIUM",  "#f0883e", 60),
    "device_retrieval":   ("MEDIUM",  "#f0883e", 65),
    "repositioning":      ("LOW",     "#d29922", 30),
    "stress_response":    ("LOW",     "#d29922", 20),
    "return_normal":      ("NONE",    "#3fb950",  5),
}


class PredictiveEngine:
    """
    Behavioral Prediction Engine.

    Maintains a 60-second sliding window of violation events.
    After each event, computes the probability that SPECIFIC cheating
    actions will occur within the next 10–30 seconds.

    Output: ranked list of predictions with confidence scores.
    """

    WINDOW_SECONDS = 60    # Historical window to consider
    MAX_PREDICTIONS = 4    # Top N predictions to surface

    def __init__(self, prediction_callback=None):
        """
        Args:
            prediction_callback: callable(prediction_label, confidence, risk_level)
        """
        self.prediction_callback = prediction_callback
        # Rolling buffer: (timestamp, violation_type)
        self._history: deque = deque(maxlen=300)
        # Currently active predictions: {label: {confidence, risk, expires_at}}
        self._active_predictions: Dict[str, dict] = {}
        # Decay rate per second (predictions fade if no new supporting events)
        self._decay_rate = 0.015
        self._last_callback_fire: Dict[str, float] = {}
        self._callback_cooldown = 20  # seconds

    def record_event(self, vtype: str) -> List[dict]:
        """
        Record a new violation event and recompute predictions.

        Returns: list of active predictions sorted by confidence.
        """
        now = time.time()
        self._history.append((now, vtype))
        self._prune(now)
        self._decay_predictions(now)
        self._generate_predictions(vtype, now)
        return self.get_predictions()

    def get_predictions(self) -> List[dict]:
        """Return active predictions sorted by confidence descending."""
        now = time.time()
        # Remove expired predictions
        self._active_predictions = {
            k: v for k, v in self._active_predictions.items()
            if v["expires_at"] > now
        }
        return sorted(
            self._active_predictions.values(),
            key=lambda x: x["confidence"],
            reverse=True
        )[:self.MAX_PREDICTIONS]

    def get_prediction_score(self) -> float:
        """Composite prediction risk score (0–100)."""
        preds = self.get_predictions()
        if not preds:
            return 0.0
        # Weighted sum — highest confidence prediction dominates
        total = sum(p["confidence"] * p["base_risk"] / 100 for p in preds)
        return min(100.0, round(total, 1))

    # ─── Internal ──────────────────────────────────────────────────────────

    def _prune(self, now: float):
        cutoff = now - self.WINDOW_SECONDS
        while self._history and self._history[0][0] < cutoff:
            self._history.popleft()

    def _decay_predictions(self, now: float):
        """Apply exponential decay to existing predictions."""
        for pred in self._active_predictions.values():
            age = now - pred["last_updated"]
            # Exponential decay: confidence halves every ~46 seconds
            pred["confidence"] = max(0.0, pred["confidence"] * math.exp(-self._decay_rate * age))
            pred["last_updated"] = now

    def _generate_predictions(self, trigger_vtype: str, now: float):
        """
        For the triggering violation, look up transition table and
        compute or strengthen predictions.
        """
        transitions = BEHAVIORAL_TRANSITIONS.get(trigger_vtype, [])

        # Compute velocity — how many of this type in last 30s?
        recent_count = sum(
            1 for ts, vt in self._history
            if vt == trigger_vtype and ts >= now - 30
        )
        velocity_boost = min(0.3, (recent_count - 1) * 0.08)  # caps at +30%

        for next_state, base_prob, window in transitions:
            # Boost probability based on recent frequency
            adjusted_prob = min(0.95, base_prob + velocity_boost)
            confidence = round(adjusted_prob * 100, 1)

            risk_info = PREDICTION_RISK.get(next_state, ("MEDIUM", "#f0883e", 50))
            risk_label, risk_color, base_risk = risk_info

            if next_state in self._active_predictions:
                # Strengthen existing prediction
                existing = self._active_predictions[next_state]
                existing["confidence"] = min(98.0, max(existing["confidence"], confidence))
                existing["expires_at"] = now + window
                existing["last_updated"] = now
                existing["trigger_count"] = existing.get("trigger_count", 1) + 1
            else:
                # New prediction
                self._active_predictions[next_state] = {
                    "label": next_state.replace("_", " ").title(),
                    "confidence": confidence,
                    "risk_level": risk_label,
                    "risk_color": risk_color,
                    "base_risk": base_risk,
                    "expires_at": now + window,
                    "created_at": now,
                    "last_updated": now,
                    "trigger_count": 1,
                    "triggered_by": trigger_vtype,
                }

            # Fire callback
            last_fired = self._last_callback_fire.get(next_state, 0)
            if (now - last_fired >= self._callback_cooldown and
                    confidence >= 50 and self.prediction_callback):
                self._last_callback_fire[next_state] = now
                self.prediction_callback(
                    next_state.replace("_", " ").title(),
                    confidence,
                    risk_label,
                )

    def get_history_summary(self) -> Dict[str, int]:
        """Returns counts of each violation type in current window."""
        summary: Dict[str, int] = {}
        for _, vt in self._history:
            summary[vt] = summary.get(vt, 0) + 1
        return summary

    def clear(self):
        self._history.clear()
        self._active_predictions.clear()
        self._last_callback_fire.clear()
