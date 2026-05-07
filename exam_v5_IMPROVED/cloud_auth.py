"""
cloud_auth.py — Drop into exam_v5_IMPROVED/ root.

Handles cloud authentication and session lifecycle.
Designed to be completely safe: if the server is unreachable at any
point, the exam continues uninterrupted in offline mode.

Usage (in ui/login_window.py after local auth passes):

    from cloud_auth import CloudAuth
    cloud = CloudAuth()
    token_ok   = cloud.login(student_id, password)
    session_id = cloud.start_session() if token_ok else 0
    # store cloud and session_id in user_data

On exam close (in main_app.py):

    cloud.end_session(session_id, risk_score, risk_level)
"""

import os
import time
import logging
import requests
from typing import Optional

log = logging.getLogger("cloud_auth")

# ── Config ─────────────────────────────────────────────────────────────────────
API_URL = os.environ.get("PROCTORING_API_URL", "").rstrip("/")

# On Render free tier, cold start can take up to 60 s
_LOGIN_TIMEOUT  = 65
_DEFAULT_TIMEOUT = 10
_MAX_RETRIES    = 2


class CloudAuth:
    """
    Stateful cloud auth + session manager.
    One instance per exam session (store it in user_data / main_app).
    """

    def __init__(self, api_url: Optional[str] = None):
        self._api_url = (api_url or API_URL).rstrip("/")
        self._token: str = ""
        self._session_id: int = 0
        self._online: bool = False

    # ── Public API ─────────────────────────────────────────────────────────────

    def login(self, student_id: str, password: str) -> bool:
        """
        Authenticate with the cloud API.
        Returns True on success; False on any failure (offline fallback).
        """
        if not self._api_url:
            log.warning("[CloudAuth] PROCTORING_API_URL not set — offline mode.")
            return False

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                resp = requests.post(
                    f"{self._api_url}/auth/token",
                    json={"student_id": student_id, "password": password},
                    timeout=_LOGIN_TIMEOUT,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    self._token = data["access_token"]
                    # Also export to env so camera_monitor.py picks it up
                    os.environ["PROCTORING_AUTH_TOKEN"] = self._token
                    self._online = True
                    log.info("[CloudAuth] Logged in: %s", student_id)
                    return True
                elif resp.status_code == 401:
                    log.warning("[CloudAuth] Invalid credentials for %s", student_id)
                    return False
                else:
                    log.warning("[CloudAuth] Login HTTP %d: %s",
                                resp.status_code, resp.text[:120])
                    if attempt < _MAX_RETRIES:
                        time.sleep(2)
            except requests.exceptions.Timeout:
                log.warning("[CloudAuth] Timeout on attempt %d — server cold-starting?", attempt)
                if attempt < _MAX_RETRIES:
                    time.sleep(5)
            except requests.exceptions.RequestException as e:
                log.warning("[CloudAuth] Network error: %s — offline mode.", e)
                return False

        log.warning("[CloudAuth] All login attempts failed — offline mode.")
        return False

    def start_session(self, exam_id: str = "default") -> int:
        """
        Open an exam session on the server.
        Returns session_id (>0) on success, 0 on failure.
        """
        if not self._token:
            return 0
        try:
            resp = requests.post(
                f"{self._api_url}/sessions/start",
                json={"exam_id": exam_id},
                headers=self._auth_headers(),
                timeout=_DEFAULT_TIMEOUT,
            )
            if resp.status_code == 200:
                self._session_id = resp.json()["session_id"]
                log.info("[CloudAuth] Session started: id=%d", self._session_id)
                return self._session_id
            log.warning("[CloudAuth] start_session HTTP %d", resp.status_code)
        except Exception as e:
            log.warning("[CloudAuth] start_session error: %s", e)
        return 0

    def end_session(self, session_id: int, risk_score: float, risk_level: str):
        """
        Close the exam session.  Best-effort — never raises.
        """
        if not self._token or not session_id:
            return
        try:
            requests.post(
                f"{self._api_url}/sessions/end",
                json={
                    "session_id":       session_id,
                    "final_risk_score": float(risk_score),
                    "risk_level":       str(risk_level),
                },
                headers=self._auth_headers(),
                timeout=_DEFAULT_TIMEOUT,
            )
            log.info("[CloudAuth] Session %d ended. Risk=%.1f %s",
                     session_id, risk_score, risk_level)
        except Exception as e:
            log.warning("[CloudAuth] end_session error: %s", e)

    @property
    def token(self) -> str:
        return self._token

    @property
    def is_online(self) -> bool:
        return self._online

    # ── Private ────────────────────────────────────────────────────────────────

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token}"}


# ── Module-level convenience shims (backwards-compat with DEPLOYMENT.md) ──────
_default_auth = CloudAuth()

def cloud_login(student_id: str, password: str) -> bool:
    return _default_auth.login(student_id, password)

def cloud_start_session(exam_id: str = "default") -> int:
    return _default_auth.start_session(exam_id)

def cloud_end_session(session_id: int, risk_score: float, risk_level: str):
    _default_auth.end_session(session_id, risk_score, risk_level)
