# -*- coding: utf-8 -*-
# ┌─────────────────────────────────────────────────────────────────────────┐
# │  ⚓  Agente Hormuz — Managed Agents Layer                                
# │  Pilar 3: SESSION MANAGEMENT                                            
# │  Criador    : Cloves Nascimento                                          
# │  Fingerprint: 8a3ee43b0c78e2b4                                          
# └─────────────────────────────────────────────────────────────────────────┘
"""
SESSION MANAGEMENT
──────────────────
Inicia sessões referenciando Agent ID e Environment ID.
Estado persistente via filesystem do contêiner gerenciado.
Suporte a resume de sessões interrompidas cross-device.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import httpx

log = logging.getLogger("hormuz.managed.session")

HORMUZ_HOME   = Path(os.environ.get("HORMUZ_HOME", Path.home() / ".hormuz"))
SESSIONS_FILE = HORMUZ_HOME / "sessions.json"
BETA_HEADER   = "managed-agents-2026-04-01"
API_BASE      = os.environ.get("HORMUZ_API_BASE", "https://api.anthropic.com/v1")


# ─────────────────────────────────────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SessionRecord:
    session_id:  str
    agent_id:    str
    env_id:      str
    task:        str
    status:      str = "active"          # active | paused | done | error
    device_id:   str = ""
    created_at:  str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at:  str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    event_count: int = 0
    last_event:  Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "SessionRecord":
        return cls(**d)


# ─────────────────────────────────────────────────────────────────────────────
# Persistent session store
# ─────────────────────────────────────────────────────────────────────────────

class SessionStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._sessions: dict[str, SessionRecord] = {}
        self._load()

    def _load(self):
        try:
            if SESSIONS_FILE.exists():
                raw = json.loads(SESSIONS_FILE.read_text())
                self._sessions = {k: SessionRecord.from_dict(v) for k, v in raw.items()}
        except Exception as e:
            log.warning(f"[SessionStore] Load failed: {e}")

    def _save(self):
        HORMUZ_HOME.mkdir(parents=True, exist_ok=True)
        tmp = SESSIONS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(
            {k: v.to_dict() for k, v in self._sessions.items()}, indent=2
        ))
        tmp.replace(SESSIONS_FILE)

    def add(self, rec: SessionRecord):
        with self._lock:
            self._sessions[rec.session_id] = rec
            self._save()

    def get(self, session_id: str) -> Optional[SessionRecord]:
        return self._sessions.get(session_id)

    def update(self, rec: SessionRecord):
        with self._lock:
            rec.updated_at = datetime.now(timezone.utc).isoformat()
            self._sessions[rec.session_id] = rec
            self._save()

    def active(self) -> list[SessionRecord]:
        return [s for s in self._sessions.values() if s.status == "active"]

    def resumable(self, exclude_device: str = "") -> list[SessionRecord]:
        return [
            s for s in self._sessions.values()
            if s.status in ("active", "paused") and s.device_id != exclude_device
        ]

    def all(self) -> list[SessionRecord]:
        return list(self._sessions.values())


# Global store
_store = SessionStore()


# ─────────────────────────────────────────────────────────────────────────────
# HTTP client
# ─────────────────────────────────────────────────────────────────────────────

def _client(api_key: Optional[str] = None) -> httpx.Client:
    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    return httpx.Client(
        base_url=API_BASE,
        headers={
            "x-api-key":         key,
            "anthropic-beta":    BETA_HEADER,
            "anthropic-version": "2023-06-01",
            "content-type":      "application/json",
        },
        timeout=30.0,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Session Manager
# ─────────────────────────────────────────────────────────────────────────────

class SessionManager:
    """
    Manages lifecycle of Hormuz managed agent sessions.
    Each session references an Agent ID and an Environment ID.
    State is persisted locally and in the container filesystem.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key  = api_key
        self._device  = _device_id()

    def start(
        self,
        agent_id:   str,
        env_id:     str,
        task:       str,
        metadata:   dict = None,
    ) -> SessionRecord:
        """
        Start a new session. Returns SessionRecord with session_id.
        """
        payload = {
            "agent_id":       agent_id,
            "environment_id": env_id,
            "metadata":       metadata or {"task": task, "device": self._device},
        }
        with _client(self.api_key) as client:
            resp = client.post("/beta/sessions", json=payload)
            resp.raise_for_status()
            data = resp.json()

        rec = SessionRecord(
            session_id  = data["id"],
            agent_id    = agent_id,
            env_id      = env_id,
            task        = task,
            status      = "active",
            device_id   = self._device,
        )
        _store.add(rec)
        log.info(f"[Session] Started: {rec.session_id} | task: {task[:60]}")
        return rec

    def resume(self, session_id: str) -> SessionRecord:
        """
        Resume a paused or interrupted session (e.g. from another device).
        Updates device ownership locally.
        """
        rec = _store.get(session_id)
        if not rec:
            raise ValueError(f"Session {session_id} not found locally")

        with _client(self.api_key) as client:
            resp = client.get(f"/beta/sessions/{session_id}")
            resp.raise_for_status()
            data = resp.json()

        rec.status     = data.get("status", rec.status)
        rec.device_id  = self._device
        rec.event_count = data.get("event_count", rec.event_count)
        _store.update(rec)
        log.info(f"[Session] Resumed: {session_id} (was on device {rec.device_id})")
        return rec

    def pause(self, session_id: str) -> bool:
        """Mark session as paused — allows resume on another device."""
        rec = _store.get(session_id)
        if not rec:
            return False
        with _client(self.api_key) as client:
            resp = client.post(f"/beta/sessions/{session_id}/pause")
            if resp.status_code not in (200, 204):
                return False
        rec.status = "paused"
        _store.update(rec)
        log.info(f"[Session] Paused: {session_id}")
        return True

    def stop(self, session_id: str) -> bool:
        """Terminate a session."""
        with _client(self.api_key) as client:
            resp = client.post(f"/beta/sessions/{session_id}/stop")
            ok = resp.status_code in (200, 204)
        rec = _store.get(session_id)
        if rec:
            rec.status = "done"
            _store.update(rec)
        log.info(f"[Session] Stopped: {session_id}")
        return ok

    def interrupt(self, session_id: str, redirect_message: Optional[str] = None) -> bool:
        """
        Interrupt a running session mid-execution.
        Optionally send a redirect message to change direction.
        """
        payload = {}
        if redirect_message:
            payload["redirect"] = redirect_message
        with _client(self.api_key) as client:
            resp = client.post(f"/beta/sessions/{session_id}/interrupt", json=payload)
            ok = resp.status_code in (200, 204)
        log.info(f"[Session] Interrupted: {session_id} | redirect: {redirect_message or 'none'}")
        return ok

    def get_history(self, session_id: str) -> list[dict]:
        """Retrieve full event history from server."""
        with _client(self.api_key) as client:
            resp = client.get(f"/beta/sessions/{session_id}/events")
            resp.raise_for_status()
            return resp.json().get("events", [])

    def list_active(self) -> list[SessionRecord]:
        return _store.active()

    def list_resumable(self) -> list[SessionRecord]:
        """Sessions from other devices that can be continued here."""
        return _store.resumable(exclude_device=self._device)

    def list_all(self) -> list[SessionRecord]:
        return _store.all()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _device_id() -> str:
    import hashlib, socket
    return hashlib.md5(socket.gethostname().encode()).hexdigest()[:8]
