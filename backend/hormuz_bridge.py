"""
CNGSM — Hormuz Managed Bridge
Integração do Agente Hormuz Managed Agents Layer ao Starlette e orquestrador principal S.O.H.-X.
"""

import os
import sys
import logging
from pathlib import Path

# ── garante que backend/ está no path ─────────────────────────────────────────
_backend = os.path.dirname(os.path.abspath(__file__))
if _backend not in sys.path:
    sys.path.insert(0, _backend)

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

# Importa a bridge V2 (Managed Agents)
from hormuz.managed.bridge.hormuz_bridge import HormuzBridge
from hormuz.core.identity import attribution_header

log = logging.getLogger("cngsm.hormuz_bridge")

_WORKSPACE = Path(os.path.abspath(os.path.join(_backend, "..", "workspace")))
_bridge: HormuzBridge | None = None

def get_bridge() -> HormuzBridge:
    global _bridge
    if _bridge is None:
        log.info(f"[HormuzBridge] Initializing Managed Bridge | workspace={_WORKSPACE}")
        _bridge = HormuzBridge(workspace=_WORKSPACE)
    return _bridge

# ── Route handlers ────────────────────────────────────────────────────────────

async def route_status(request: Request) -> JSONResponse:
    """GET /hormuz/status — agent and environment status"""
    try:
        b = get_bridge()
        agent_id, env_id = b.bootstrap()
        return JSONResponse({
            "status": "MANAGED_ONLINE",
            "agent_id": agent_id,
            "environment_id": env_id,
            "workspace": str(_WORKSPACE),
            "identity": attribution_header()
        })
    except Exception as e:
        log.error(f"[route_status] Error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


async def route_session_start(request: Request) -> JSONResponse:
    """POST /hormuz/managed/session"""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON body"}, status_code=400)

    task = body.get("task", "")
    if not task:
        return JSONResponse({"error": "task is required"}, status_code=400)

    try:
        b = get_bridge()
        session_id = b.new_session(task)
        return JSONResponse({"session_id": session_id, "status": "active"})
    except Exception as e:
        log.error(f"[route_session_start] Error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


async def route_session_resume(request: Request) -> JSONResponse:
    """POST /hormuz/managed/resume"""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON body"}, status_code=400)

    session_id = body.get("session_id", "")
    if not session_id:
        return JSONResponse({"error": "session_id is required"}, status_code=400)

    try:
        b = get_bridge()
        sid = b.resume_session(session_id)
        return JSONResponse({"session_id": sid, "status": "resumed"})
    except Exception as e:
         return JSONResponse({"error": str(e)}, status_code=500)


async def route_send(request: Request) -> JSONResponse:
    """POST /hormuz/managed/send"""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON body"}, status_code=400)

    message = body.get("message", "")
    session_id = body.get("session_id", None)

    try:
        b = get_bridge()
        
        # Opcionalmente, pode forçar o resumo
        if session_id and b._active_session_id != session_id:
            b.resume_session(session_id)
            
        if not b._active_session_id:
            return JSONResponse({"error": "no active session"}, status_code=400)
            
        result_text = b.send(message)
        return JSONResponse({"response": result_text})
    except Exception as e:
        log.error(f"[route_send] Error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


async def route_interrupt(request: Request) -> JSONResponse:
    """POST /hormuz/managed/interrupt"""
    try:
        body = await request.json()
        redirect = body.get("redirect", None)
    except Exception:
        redirect = None

    try:
        b = get_bridge()
        b.interrupt(redirect)
        return JSONResponse({"status": "interrupted", "redirect": redirect})
    except Exception as e:
         return JSONResponse({"error": str(e)}, status_code=500)


import asyncio
from starlette.responses import StreamingResponse

async def route_events(request: Request) -> StreamingResponse:
    """GET /hormuz/managed/events"""
    async def event_generator():
        b = get_bridge()
        if not b._stream:
            yield "data: {\"error\": \"no active session\"}\n\n"
            return
            
        q = asyncio.Queue()
        
        original_on_event = b._stream.on_event
        def queue_event(ev):
            try:
                loop = asyncio.get_event_loop()
                loop.call_soon_threadsafe(q.put_nowait, ev)
            except Exception:
                pass
            if original_on_event:
                original_on_event(ev)
                
        b._stream.on_event = queue_event
        
        try:
            while True:
                if await request.is_disconnected():
                    break
                ev = await q.get()
                import dataclasses
                import json
                yield f"data: {json.dumps(dataclasses.asdict(ev))}\n\n"
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error(f"[route_events] Error: {e}")
            yield f"data: {{\"error\": \"{str(e)}\"}}\n\n"
        finally:
            if b._stream:
                b._stream.on_event = original_on_event

    return StreamingResponse(event_generator(), media_type="text/event-stream")

# ── Route table (mounted in main.py) ──────────────────────────────────────────

hormuz_routes = [
    Route("/hormuz/status",            route_status,            methods=["GET"]),
    Route("/hormuz/managed/session",   route_session_start,     methods=["POST"]),
    Route("/hormuz/managed/resume",    route_session_resume,    methods=["POST"]),
    Route("/hormuz/managed/send",      route_send,              methods=["POST"]),
    Route("/hormuz/managed/interrupt", route_interrupt,         methods=["POST"]),
    Route("/hormuz/managed/events",    route_events,            methods=["GET"]),
]
