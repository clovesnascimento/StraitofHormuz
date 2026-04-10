from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from pydantic import BaseModel, Field, ValidationError
from typing import Annotated, Dict, Any, Optional
import uvicorn
import os
import sys

# Injeção de PYTHONPATH para resolução de monorepo
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))



# Hormuz bridge (importação lazy — falha silenciosa se anthropic não instalado)
try:
    from backend.hormuz_bridge import hormuz_routes
    _hormuz_ok = True
except Exception as _e:
    hormuz_routes = []
    _hormuz_ok = False
    print(f"[main] Hormuz bridge not loaded: {_e}")

# Modelo S.O.H.-X compatível com Pydantic v2
class ToolCall(BaseModel):
    tool_name: str
    arguments: Dict[str, Any]

async def get_status(request):
    return JSONResponse({
        "status": "S.O.H.-X ONLINE",
        "protocol": "Ω-9",
        "integrity": "PRESERVED",
        "bootstrap": "RESOLVED"
    })



routes = [
    Route("/status", get_status, methods=["GET"]),
] + hormuz_routes

from starlette.middleware.cors import CORSMiddleware
app = Starlette(debug=False, routes=routes)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

if __name__ == "__main__":
    print("S.O.H.-X KERNEL BOOTING (STARLETTE_ASGI_STABLE)...")
    print(f"[main] Hormuz bridge: {'LOADED' if _hormuz_ok else 'NOT LOADED'}")
    uvicorn.run(app, host="0.0.0.0", port=8000)
