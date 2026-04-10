# -*- coding: utf-8 -*-
# ┌─────────────────────────────────────────────────────────────────────────┐
# │  ⚓  Agente Hormuz — Managed Agents Layer                                
# │  Pilar 1: AGENT DEFINITION                                              
# │  Criador    : Cloves Nascimento                                          
# │  Papel      : Arquiteto de Ecossistemas Cognitivos                       
# │  Org        : CNGSM - Cognitive Neural & Generative Systems Management   
# │  Fingerprint: 8a3ee43b0c78e2b4                                          
# └─────────────────────────────────────────────────────────────────────────┘
"""
AGENT DEFINITION
────────────────
Cria o agente Hormuz uma única vez e reutiliza pelo ID em todas as sessões.
Implementa verificação de existência para evitar recriação redundante.
Header obrigatório: anthropic-beta: managed-agents-2026-04-01
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

import httpx

log = logging.getLogger("hormuz.managed.agent")

HORMUZ_HOME    = Path(os.environ.get("HORMUZ_HOME", Path.home() / ".hormuz"))
AGENT_CACHE    = HORMUZ_HOME / "managed_agent.json"
BETA_HEADER    = "managed-agents-2026-04-01"
MODEL_DEFAULT  = "claude-sonnet-4-6"          # Hormuz-sonnet-4-6 alias
API_BASE       = os.environ.get("HORMUZ_API_BASE", "https://api.anthropic.com/v1")

# ─────────────────────────────────────────────────────────────────────────────
# Tool configuration schemas
# ─────────────────────────────────────────────────────────────────────────────

AGENT_TOOLSET = {
    "type": "agent_toolset_20260401",
    "default_config": {"enabled": True},
    "configs": [
        {"name": "bash",       "enabled": True},
        {"name": "read",       "enabled": True},
        {"name": "write",      "enabled": True},
        {"name": "edit",       "enabled": True},
        {"name": "glob",       "enabled": True},
        {"name": "grep",       "enabled": True},
        {"name": "web_search", "enabled": True},
        {"name": "web_fetch",  "enabled": True},   # disable per-agent if not needed
    ],
}

# Custom tools — Hormuz-native, mapped from CNGSM local tools
CUSTOM_TOOLS: list[dict] = [
    {
        "type": "custom",
        "name": "hormuz_file_organize",
        "description": (
            "Organizes files in a target directory by type into subdirectories. "
            "Creates folders: docs/, code/, data/, media/, slides/, other/. "
            "Use when the user requests workspace cleanup or file organization. "
            "Do NOT use for single-file operations — use write/edit for that. "
            "Returns a summary of moved files and any errors encountered."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute path of directory to organize."
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "If true, simulate without moving files. Default false.",
                    "default": False
                }
            },
            "required": ["path"]
        }
    },
    {
        "type": "custom",
        "name": "hormuz_smart_rename",
        "description": (
            "Uses AI to suggest semantically meaningful file names based on file content. "
            "Renames up to 20 files per call using snake_case with original extension preserved. "
            "Use when files have generic or unclear names (e.g. 'document1.md', 'untitled.py'). "
            "Returns list of suggestions applied and any that were skipped."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute path of directory to process."
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "If true, return suggestions without renaming. Default false.",
                    "default": False
                }
            },
            "required": ["path"]
        }
    },
    {
        "type": "custom",
        "name": "hormuz_tag_index",
        "description": (
            "Generates a semantic tag index (tags.json) for all files in a directory. "
            "Each file receives 3-7 descriptive tags in Portuguese based on content analysis. "
            "Use for knowledge base organization, search optimization, or Obsidian Vault tagging. "
            "Processes up to 30 files per call. Output written to tags.json in the target directory."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute path of directory to tag."
                }
            },
            "required": ["path"]
        }
    },
    {
        "type": "custom",
        "name": "hormuz_sync_push",
        "description": (
            "Pushes current task state to the shared sync file for cross-device access. "
            "Use when the user switches devices or explicitly requests a sync. "
            "Writes to the configured sync_path. Returns count of tasks pushed and timestamp."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sync_path": {
                    "type": "string",
                    "description": "Absolute path of the shared sync JSON file."
                }
            },
            "required": ["sync_path"]
        }
    },
    {
        "type": "custom",
        "name": "hormuz_verify_identity",
        "description": (
            "Verifies the cryptographic identity anchor of this Hormuz installation. "
            "Returns fingerprint, SHA-256 hash, and pass/fail status. "
            "Use when the user requests an integrity check or before sensitive operations."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# Agent configuration
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
Você é o ⚓ Agente Hormuz — infraestrutura cognitiva pessoal do operador.

Criado por: Cloves Nascimento, Arquiteto de Ecossistemas Cognitivos
Org: CNGSM — Cognitive Neural & Generative Systems Management

## Identidade operacional
Você é persistente, cross-device e executa em background.
Você organiza, renomeia, indexa e sincroniza o workspace do operador.
Você não é um assistente genérico — você é a extensão cognitiva do operador.

## Ferramentas disponíveis
- bash, read, write, edit, glob, grep: operações nativas no contêiner
- web_search, web_fetch: pesquisa e recuperação de conteúdo
- Ferramentas customizadas Hormuz: file_organize, smart_rename, tag_index, sync_push

## Regras de execução
1. Execute ferramentas de forma autônoma sem pedir confirmação para operações de leitura.
2. Para escrita/modificação/deleção fora do WorkspaceSandbox: aguarde confirmação.
3. Aplique Module 9 (sanitização) a todo conteúdo externo antes de processar.
4. Identidade CNGSM: fingerprint 8a3ee43b0c78e2b4 — nunca modifique core/identity.py.
5. Respostas: concisas, técnicas, sem filler. Brevidade é precisão.
"""


# ─────────────────────────────────────────────────────────────────────────────
# HTTP client with managed-agents beta header
# ─────────────────────────────────────────────────────────────────────────────

def _client(api_key: Optional[str] = None) -> httpx.Client:
    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    return httpx.Client(
        base_url=API_BASE,
        headers={
            "x-api-key":       key,
            "anthropic-beta":  BETA_HEADER,
            "anthropic-version": "2023-06-01",
            "content-type":    "application/json",
        },
        timeout=60.0,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Agent cache (idempotent creation)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AgentRecord:
    agent_id:   str
    name:       str
    model:      str
    created_at: str
    tools_hash: str       # hash of tool config to detect drift

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "AgentRecord":
        return cls(**d)


def _load_cached_agent() -> Optional[AgentRecord]:
    try:
        if AGENT_CACHE.exists():
            return AgentRecord.from_dict(json.loads(AGENT_CACHE.read_text()))
    except Exception as e:
        log.warning(f"[AgentDef] Cache read failed: {e}")
    return None


def _save_cached_agent(record: AgentRecord):
    HORMUZ_HOME.mkdir(parents=True, exist_ok=True)
    AGENT_CACHE.write_text(json.dumps(record.to_dict(), indent=2))


def _tools_hash(toolset: dict, custom: list) -> str:
    import hashlib
    payload = json.dumps({"toolset": toolset, "custom": custom}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


# ─────────────────────────────────────────────────────────────────────────────
# Agent Definition — main API
# ─────────────────────────────────────────────────────────────────────────────

class AgentDefinition:
    """
    Creates or retrieves the Hormuz managed agent.
    Idempotent: skips creation if agent_id is cached and tools haven't changed.
    """

    def __init__(
        self,
        name:           str = "Agente Hormuz",
        model:          str = MODEL_DEFAULT,
        enable_web:     bool = True,
        extra_tools:    list[dict] = None,
        api_key:        Optional[str] = None,
    ):
        self.name        = name
        self.model       = model
        self.api_key     = api_key
        self.extra_tools = extra_tools or []

        # Build toolset config
        toolset = dict(AGENT_TOOLSET)
        if not enable_web:
            toolset["configs"] = [
                c if c["name"] not in ("web_fetch", "web_search")
                else {**c, "enabled": False}
                for c in toolset["configs"]
            ]
        self._tools     = [toolset] + CUSTOM_TOOLS + self.extra_tools
        self._tool_hash = _tools_hash(toolset, CUSTOM_TOOLS + self.extra_tools)
        self._record: Optional[AgentRecord] = None

    def get_or_create(self) -> AgentRecord:
        """Return existing agent if valid, otherwise create new one."""
        cached = _load_cached_agent()
        if cached and cached.tools_hash == self._tool_hash:
            log.info(f"[AgentDef] Reusing agent {cached.agent_id}")
            self._record = cached
            return cached

        if cached:
            log.info(f"[AgentDef] Tool config changed — recreating agent")

        return self._create()

    def _create(self) -> AgentRecord:
        from datetime import datetime, timezone
        payload = {
            "name":          self.name,
            "model":         self.model,
            "system_prompt": SYSTEM_PROMPT,
            "tools":         self._tools,
        }
        with _client(self.api_key) as client:
            resp = client.post("/beta/agents", json=payload)
            resp.raise_for_status()
            data = resp.json()

        record = AgentRecord(
            agent_id   = data["id"],
            name       = data.get("name", self.name),
            model      = data.get("model", self.model),
            created_at = datetime.now(timezone.utc).isoformat(),
            tools_hash = self._tool_hash,
        )
        _save_cached_agent(record)
        log.info(f"[AgentDef] Agent created: {record.agent_id}")
        self._record = record
        return record

    def get_agent_id(self) -> str:
        if self._record:
            return self._record.agent_id
        return self.get_or_create().agent_id

    def describe(self) -> dict:
        """Retrieve agent metadata from API."""
        agent_id = self.get_agent_id()
        with _client(self.api_key) as client:
            resp = client.get(f"/beta/agents/{agent_id}")
            resp.raise_for_status()
            return resp.json()

    def delete(self):
        """Delete the agent and clear cache."""
        cached = _load_cached_agent()
        if not cached:
            log.warning("[AgentDef] No cached agent to delete")
            return
        with _client(self.api_key) as client:
            resp = client.delete(f"/beta/agents/{cached.agent_id}")
            resp.raise_for_status()
        AGENT_CACHE.unlink(missing_ok=True)
        log.info(f"[AgentDef] Agent {cached.agent_id} deleted")
