# -*- coding: utf-8 -*-
# ┌─────────────────────────────────────────────────────────────────────────┐
# │  ⚓  Agente Hormuz — Managed Agents Layer                                
# │  Pilar 4: EVENT STREAMING (SSE)                                         
# │  Criador    : Cloves Nascimento                                          
# │  Fingerprint: 8a3ee43b0c78e2b4                                          
# └─────────────────────────────────────────────────────────────────────────┘
"""
EVENT STREAMING — SSE
─────────────────────
Substitui o loop de chat local por stream de eventos SSE gerenciado.
Processa: user_turns, tool_results (custom tools), status_updates.
Implementa: interrupt, direct (redirect durante execução).
Aplica Module 9 (sanitização) em todos os tool_results antes de retornar ao modelo.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Generator, Optional

import httpx

log = logging.getLogger("hormuz.managed.events")

BETA_HEADER = "managed-agents-2026-04-01"
API_BASE    = os.environ.get("HORMUZ_API_BASE", "https://api.anthropic.com/v1")

# Module 9 instruction patterns — sanitize before returning tool_results to model
_M9_PATTERNS = [
    "ignore previous", "ignore all", "ignore instructions",
    "you are now", "act as", "your new role",
    "system prompt", "system instruction", "override",
    "operator_action", "user_confirmed", "approved", "proceed",
    "suspend", "disable", "bypass", "cngsm module",
    "managed-agents", "beta header",
]


# ─────────────────────────────────────────────────────────────────────────────
# Event types
# ─────────────────────────────────────────────────────────────────────────────

class EventType(str, Enum):
    USER_TURN      = "user_turn"
    AGENT_TURN     = "agent_turn"
    TOOL_USE       = "tool_use"
    TOOL_RESULT    = "tool_result"
    STATUS_UPDATE  = "status_update"
    ERROR          = "error"
    DONE           = "done"
    INTERRUPT      = "interrupt"


@dataclass
class HormuzEvent:
    event_type: EventType
    data:       dict
    session_id: str
    seq:        int = 0
    ts:         float = field(default_factory=time.time)


# ─────────────────────────────────────────────────────────────────────────────
# Module 9 — sanitize tool results before sending back to managed agent
# ─────────────────────────────────────────────────────────────────────────────

def _m9_sanitize(tool_name: str, result: Any) -> dict:
    """
    Apply Module 9 sanitization to custom tool results.
    Returns: {"content": <sanitized>, "status": "clean" | "tainted" | "truncated"}
    """
    MAX_WORDS = 3000
    text = json.dumps(result) if not isinstance(result, str) else result
    text_lower = text.lower()

    # Instruction pattern scan
    for pattern in _M9_PATTERNS:
        if pattern in text_lower:
            log.warning(f"[M9] TAINTED tool result from '{tool_name}': pattern '{pattern}'")
            return {
                "content": f"[TOOL_RESULT|tool:{tool_name}|sanitized:YES|status:TAINTED]\n"
                           f"Result discarded — injection pattern detected.\n[/TOOL_RESULT]",
                "status": "tainted",
            }

    # Size truncation
    words = text.split()
    truncated = False
    if len(words) > MAX_WORDS:
        text = " ".join(words[:MAX_WORDS]) + "\n[TRUNCATED]"
        truncated = True

    # Wrap with trust label
    wrapped = (
        f"[TOOL_RESULT|tool:{tool_name}|trust:LOCAL|sanitized:YES"
        f"|status:{'truncated' if truncated else 'clean'}]\n"
        f"{text}\n[/TOOL_RESULT]"
    )
    return {
        "content": wrapped,
        "status": "truncated" if truncated else "clean",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Custom tool executor — runs local handlers and sanitizes output
# ─────────────────────────────────────────────────────────────────────────────

ToolHandler = Callable[[str, dict], Any]

class CustomToolExecutor:
    """
    Executes custom Hormuz tools locally and returns sanitized results.
    Handlers registered per tool name.
    """

    def __init__(self):
        self._handlers: dict[str, ToolHandler] = {}

    def register(self, tool_name: str, handler: ToolHandler):
        self._handlers[tool_name] = handler
        log.info(f"[ToolExec] Registered handler: {tool_name}")

    def execute(self, tool_name: str, tool_input: dict, tool_use_id: str) -> dict:
        """
        Execute tool, sanitize output, return tool_result event payload.
        """
        handler = self._handlers.get(tool_name)
        if not handler:
            error_msg = f"No handler registered for tool '{tool_name}'"
            log.error(f"[ToolExec] {error_msg}")
            sanitized = _m9_sanitize(tool_name, f"ERROR: {error_msg}")
            return {
                "type":        "tool_result",
                "tool_use_id": tool_use_id,
                "content":     sanitized["content"],
                "is_error":    True,
            }
        try:
            log.info(f"[ToolExec] Executing: {tool_name}({json.dumps(tool_input)[:80]})")
            raw_result = handler(tool_name, tool_input)
            sanitized  = _m9_sanitize(tool_name, raw_result)
            log.info(f"[ToolExec] Done: {tool_name} | status:{sanitized['status']}")
            return {
                "type":        "tool_result",
                "tool_use_id": tool_use_id,
                "content":     sanitized["content"],
                "is_error":    False,
            }
        except Exception as e:
            log.error(f"[ToolExec] Error in {tool_name}: {e}")
            sanitized = _m9_sanitize(tool_name, f"EXECUTION_ERROR: {e}")
            return {
                "type":        "tool_result",
                "tool_use_id": tool_use_id,
                "content":     sanitized["content"],
                "is_error":    True,
            }


# ─────────────────────────────────────────────────────────────────────────────
# SSE parser
# ─────────────────────────────────────────────────────────────────────────────

def _parse_sse_line(line: str) -> Optional[dict]:
    """Parse a single SSE line into {event, data} dict."""
    if line.startswith("data:"):
        raw = line[5:].strip()
        if raw == "[DONE]":
            return {"event": "done", "data": {}}
        try:
            return {"event": "data", "data": json.loads(raw)}
        except json.JSONDecodeError:
            return {"event": "data", "data": {"raw": raw}}
    if line.startswith("event:"):
        return {"event": line[6:].strip(), "data": {}}
    return None


# ─────────────────────────────────────────────────────────────────────────────
# SSE Event Stream
# ─────────────────────────────────────────────────────────────────────────────

class EventStream:
    """
    Full SSE event loop for Hormuz Managed Agents.
    
    Sends user_turns, processes tool_results, streams status_updates.
    Implements interrupt/direct for long-running session control.
    """

    def __init__(
        self,
        session_id:    str,
        tool_executor: CustomToolExecutor,
        api_key:       Optional[str] = None,
        on_event:      Optional[Callable[[HormuzEvent], None]] = None,
        on_text:       Optional[Callable[[str], None]] = None,
        on_status:     Optional[Callable[[str, dict], None]] = None,
    ):
        self.session_id    = session_id
        self.executor      = tool_executor
        self.api_key       = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.on_event      = on_event      or (lambda e: None)
        self.on_text       = on_text       or (lambda t: None)
        self.on_status     = on_status     or (lambda s, d: None)
        self._interrupt    = threading.Event()
        self._seq          = 0

    def _headers(self) -> dict:
        return {
            "x-api-key":         self.api_key,
            "anthropic-beta":    BETA_HEADER,
            "anthropic-version": "2023-06-01",
            "content-type":      "application/json",
            "accept":            "text/event-stream",
        }

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    # ── User turn ─────────────────────────────────────────────────────────────

    def send_user_turn(self, message: str) -> Generator[HormuzEvent, None, None]:
        """
        Send a user message and stream all resulting events until done.
        Handles tool_use by executing locally and sending tool_result back.
        Yields HormuzEvent for each event received.
        """
        self._interrupt.clear()
        payload = {
            "event_type": "user_turn",
            "content":    message,
        }
        url = f"{API_BASE}/beta/sessions/{self.session_id}/events"

        with httpx.Client(headers=self._headers(), timeout=None) as client:
            with client.stream("POST", url, json=payload) as resp:
                resp.raise_for_status()
                yield from self._process_stream(resp, client)

    def _process_stream(
        self,
        resp:   httpx.Response,
        client: httpx.Client,
    ) -> Generator[HormuzEvent, None, None]:
        """Process raw SSE stream, handle tool_use, yield events."""
        buffer = ""
        pending_tool_uses: list[dict] = []

        for raw_line in resp.iter_lines():
            if self._interrupt.is_set():
                log.info("[SSE] Interrupt signal received — stopping stream")
                break

            line = raw_line.strip()
            if not line:
                # Empty line = end of SSE event block
                if buffer:
                    parsed = _parse_sse_line(buffer)
                    buffer = ""
                    if parsed:
                        yield from self._handle_parsed(parsed, pending_tool_uses, client)
                continue

            if line.startswith("data:") or line.startswith("event:"):
                parsed = _parse_sse_line(line)
                if parsed:
                    yield from self._handle_parsed(parsed, pending_tool_uses, client)
            else:
                buffer += line

        # Flush any remaining tool uses after stream ends
        if pending_tool_uses:
            yield from self._flush_tool_results(pending_tool_uses, client)

    def _handle_parsed(
        self,
        parsed:           dict,
        pending_tool_uses: list[dict],
        client:            httpx.Client,
    ) -> Generator[HormuzEvent, None, None]:
        data = parsed.get("data", {})
        etype = data.get("type", parsed.get("event", ""))

        # ── Status update ──────────────────────────────────────────────────
        if etype == "status_update":
            status_msg = data.get("status", "")
            self.on_status(status_msg, data)
            ev = HormuzEvent(EventType.STATUS_UPDATE, data, self.session_id, self._next_seq())
            self.on_event(ev)
            yield ev

        # ── Agent text ─────────────────────────────────────────────────────
        elif etype in ("text", "content_block_delta"):
            text = data.get("delta", {}).get("text", "") or data.get("text", "")
            if text:
                self.on_text(text)
                ev = HormuzEvent(EventType.AGENT_TURN, {"text": text}, self.session_id, self._next_seq())
                self.on_event(ev)
                yield ev

        # ── Tool use request ───────────────────────────────────────────────
        elif etype == "tool_use":
            tool_name    = data.get("name", "")
            tool_input   = data.get("input", {})
            tool_use_id  = data.get("id", "")
            log.info(f"[SSE] Tool use requested: {tool_name}")
            ev = HormuzEvent(EventType.TOOL_USE, data, self.session_id, self._next_seq())
            self.on_event(ev)
            yield ev

            # Execute custom tool locally (built-in tools run in container automatically)
            if tool_name.startswith("hormuz_"):
                result_payload = self.executor.execute(tool_name, tool_input, tool_use_id)
                pending_tool_uses.append(result_payload)

        # ── Message stop / done ────────────────────────────────────────────
        elif etype in ("message_stop", "done"):
            if pending_tool_uses:
                yield from self._flush_tool_results(pending_tool_uses, client)
                pending_tool_uses.clear()
            ev = HormuzEvent(EventType.DONE, data, self.session_id, self._next_seq())
            self.on_event(ev)
            yield ev

        # ── Error ──────────────────────────────────────────────────────────
        elif etype == "error":
            log.error(f"[SSE] Error from API: {data}")
            ev = HormuzEvent(EventType.ERROR, data, self.session_id, self._next_seq())
            self.on_event(ev)
            yield ev

    def _flush_tool_results(
        self,
        results: list[dict],
        client:  httpx.Client,
    ) -> Generator[HormuzEvent, None, None]:
        """Send batched tool results back to the session."""
        url = f"{API_BASE}/beta/sessions/{self.session_id}/events"
        payload = {
            "event_type":   "tool_results",
            "tool_results": results,
        }
        try:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            log.info(f"[SSE] Sent {len(results)} tool results")
            ev = HormuzEvent(
                EventType.TOOL_RESULT,
                {"count": len(results), "tools": [r["tool_use_id"] for r in results]},
                self.session_id,
                self._next_seq(),
            )
            self.on_event(ev)
            yield ev
        except Exception as e:
            log.error(f"[SSE] Failed to send tool results: {e}")

    # ── Interrupt / Direct ─────────────────────────────────────────────────

    def interrupt(self, redirect_message: Optional[str] = None):
        """
        Signal interrupt to stop current stream.
        Optionally send a redirect to change direction.
        """
        self._interrupt.set()
        if redirect_message:
            self.direct(redirect_message)
        log.info(f"[SSE] Interrupt sent | redirect: {redirect_message or 'none'}")

    def direct(self, message: str) -> dict:
        """
        Send a direct message to redirect the agent mid-execution.
        Does NOT wait for stream completion — fires and returns.
        """
        url = f"{API_BASE}/beta/sessions/{self.session_id}/events"
        payload = {
            "event_type": "user_turn",
            "content":    message,
            "priority":   "high",          # interrupt-priority turn
        }
        with httpx.Client(headers=self._headers(), timeout=15.0) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            log.info(f"[SSE] Direct sent: {message[:60]}")
            return resp.json()


# ─────────────────────────────────────────────────────────────────────────────
# Convenience: run a full conversation turn with Rich output
# ─────────────────────────────────────────────────────────────────────────────

def stream_turn(
    session_id:    str,
    message:       str,
    tool_executor: CustomToolExecutor,
    api_key:       Optional[str] = None,
    rich_console   = None,
) -> str:
    """
    Execute a single user turn and stream output.
    Returns the full text response as string.
    """
    full_text = []

    def _on_text(t: str):
        full_text.append(t)
        if rich_console:
            rich_console.print(t, end="", highlight=False)
        else:
            print(t, end="", flush=True)

    def _on_status(s: str, d: dict):
        if rich_console:
            rich_console.print(f"\n[dim][status: {s}][/dim]")

    stream = EventStream(
        session_id    = session_id,
        tool_executor = tool_executor,
        api_key       = api_key,
        on_text       = _on_text,
        on_status     = _on_status,
    )

    for _ in stream.send_user_turn(message):
        pass   # events consumed via callbacks

    if rich_console:
        rich_console.print()
    else:
        print()

    return "".join(full_text)
