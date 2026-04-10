"""
CNGSM — Anthropic Stub v1.1
Cliente mínimo via httpx — sem dependência de Pydantic.

Compatível com:
  - Anthropic API nativa  (ANTHROPIC_BASE_URL=https://api.anthropic.com)
  - DeepSeek via /anthropic (ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic)

Variáveis de ambiente (lidas automaticamente do .env via load_env()):
  ANTHROPIC_API_KEY      — chave da API (Anthropic ou DeepSeek)
  ANTHROPIC_BASE_URL     — endpoint base (default: https://api.anthropic.com)
  ANTHROPIC_MODEL        — modelo padrão (default: deepseek-chat)
  API_TIMEOUT_MS         — timeout em ms (default: 600000 = 10min)
"""

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import httpx

log = logging.getLogger("cngsm.anthropic_stub")

# ── .env loader (sem dependência de dotenv) ───────────────────────────────────

def load_env(env_path: Optional[str] = None) -> None:
    """Carrega variáveis do .env para os.environ (não sobrescreve existentes)."""
    candidates = [
        env_path,
        Path(__file__).parent.parent / ".env",   # raiz do projeto
        Path.cwd() / ".env",
    ]
    for path in candidates:
        if path and Path(path).exists():
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key and key not in os.environ:
                        os.environ[key] = value
            log.debug("[AnthropicStub] Loaded .env from %s", path)
            return


# Carrega .env ao importar o módulo
load_env()

# ── Defaults lidos do ambiente ────────────────────────────────────────────────

def _base_url() -> str:
    raw = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/")
    # Garantir que o path /v1/messages está presente apenas para endpoint nativo
    if "deepseek.com" in raw:
        return raw  # DeepSeek: /anthropic/v1/messages já está no base
    return raw      # Anthropic: adicionamos /v1/messages na chamada

def _messages_url() -> str:
    base = _base_url()
    if base.endswith("/anthropic"):
        return base + "/v1/messages"
    if base.endswith("/v1"):
        return base + "/messages"
    if not base.endswith("/messages"):
        return base + "/v1/messages"
    return base

def _default_model() -> str:
    return os.environ.get("ANTHROPIC_MODEL", "deepseek-chat")

def _timeout() -> float:
    ms = int(os.environ.get("API_TIMEOUT_MS", "600000"))
    return ms / 1000


# ── Response types ────────────────────────────────────────────────────────────

@dataclass
class ContentBlock:
    text: str
    type: str = "text"


@dataclass
class MessageResponse:
    id: str
    model: str
    content: list
    role: str = "assistant"
    stop_reason: Optional[str] = None
    usage: dict = field(default_factory=dict)

    def __post_init__(self):
        normalized = []
        for item in self.content:
            if isinstance(item, dict):
                normalized.append(ContentBlock(
                    text=item.get("text", ""),
                    type=item.get("type", "text"),
                ))
            else:
                normalized.append(item)
        self.content = normalized


# ── Messages resource ─────────────────────────────────────────────────────────

class _MessagesResource:
    def __init__(self, api_key: str):
        self._api_key = api_key

    def create(
        self,
        model: Optional[str] = None,
        max_tokens: int = 1024,
        messages: Optional[list] = None,
        system: Optional[str] = None,
        temperature: float = 1.0,
        **kwargs,
    ) -> MessageResponse:
        """
        Synchronous API call.
        Mirrors: anthropic.Anthropic().messages.create(...)
        """
        url     = _messages_url()
        timeout = _timeout()
        model   = model or _default_model()

        payload: dict[str, Any] = {
            "model":      model,
            "max_tokens": max_tokens,
            "messages":   messages or [],
        }
        if system:
            payload["system"] = system
        if temperature != 1.0:
            payload["temperature"] = temperature

        # DeepSeek ignora anthropic-version mas aceita x-api-key
        headers = {
            "x-api-key":          self._api_key,
            "anthropic-version":  "2023-06-01",
            "content-type":       "application/json",
        }

        log.info("[AnthropicStub] POST %s model=%s max_tokens=%d timeout=%.0fs",
                 url, model, max_tokens, timeout)

        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as e:
            log.error("[AnthropicStub] HTTP %s: %s", e.response.status_code, e.response.text[:300])
            raise RuntimeError(
                f"API error {e.response.status_code}: {e.response.text[:200]}"
            ) from e
        except httpx.TimeoutException as e:
            log.error("[AnthropicStub] Timeout after %.0fs", timeout)
            raise RuntimeError(f"API timeout after {timeout}s") from e
        except Exception as e:
            log.error("[AnthropicStub] Request failed: %s", e)
            raise

        return MessageResponse(
            id=data.get("id", ""),
            model=data.get("model", model),
            content=data.get("content", []),
            role=data.get("role", "assistant"),
            stop_reason=data.get("stop_reason"),
            usage=data.get("usage", {}),
        )


# ── Public client ─────────────────────────────────────────────────────────────

class Anthropic:
    """
    Drop-in para anthropic.Anthropic() — usa httpx puro, sem Pydantic.

    Compatível com Anthropic nativo e DeepSeek via /anthropic.
    Lê ANTHROPIC_API_KEY, ANTHROPIC_BASE_URL, ANTHROPIC_MODEL do ambiente.

    Exemplo:
        client = Anthropic()
        resp = client.messages.create(
            model="deepseek-chat",
            max_tokens=1024,
            messages=[{"role": "user", "content": "Olá!"}]
        )
        print(resp.content[0].text)
    """

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not self._api_key:
            log.warning("[AnthropicStub] ANTHROPIC_API_KEY nao definida")
        self.messages = _MessagesResource(self._api_key)
        log.info("[AnthropicStub] endpoint=%s model=%s", _messages_url(), _default_model())

    def __repr__(self) -> str:
        key_hint = (self._api_key[:8] + "...") if self._api_key else "NAO DEFINIDA"
        return f"<AnthropicStub endpoint={_messages_url()} key={key_hint}>"
