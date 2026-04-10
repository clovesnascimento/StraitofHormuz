"""
CNGSM — Contemplating Mode
Multi-Agent Parallel Search Orchestrator
Version: 1.1 — Unified with module9_sanitizer.py (Antigravity Defense Layer v3.3)
"""

import asyncio
import json
import os
import platform
import sys
import time
import logging
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
# FIX: Console Encoding (Windows UTF-8)
# ──────────────────────────────────────────────────────────────────────────────
if platform.system() == "Windows":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    os.environ["PYTHONIOENCODING"] = "utf-8"

def safe_icon(emoji: str, ascii_alt: str) -> str:
    """Retorna emoji se o console suportar, senão ASCII"""
    try:
        emoji.encode(sys.stdout.encoding or 'utf-8')
        return emoji
    except (UnicodeEncodeError, AttributeError):
        return ascii_alt


import httpx
import yaml

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("cngsm.contemplating")

# ── Enums ─────────────────────────────────────────────────────────────────────

class SourceType(str, Enum):
    GDRIVE_PUBLIC  = "gdrive_public"
    GDRIVE_PRIVATE = "gdrive_private"
    SILO           = "silo"
    LOCAL          = "local"

class ResultStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    EMPTY   = "empty"
    TIMEOUT = "timeout"
    ERROR   = "error"

# ── Data Structures ───────────────────────────────────────────────────────────

@dataclass
class AgentConfig:
    agent_id: str
    name: str
    source_type: SourceType
    source_ref: str
    domain: str
    description: str
    permissions: str = "read"
    active: bool = True

@dataclass
class SubQuery:
    agent_id: str
    query: str
    rationale: str
    priority: int = 1

@dataclass
class Snippet:
    text: str
    source: str
    relevance: float

@dataclass
class ResearchResult:
    agent_id: str
    agent_name: str
    source_type: str
    sub_query: str
    findings: list[str]       = field(default_factory=list)
    snippets: list[Snippet]   = field(default_factory=list)
    confidence: float         = 0.0
    status: ResultStatus      = ResultStatus.EMPTY
    error: Optional[str]      = None
    elapsed_ms: int           = 0

@dataclass
class FinalResponse:
    original_query: str
    agents_consulted: list[str]
    agents_empty: list[str]
    synthesis: str
    sources: list[dict]
    gaps: list[str]
    contradictions: list[dict]
    contemplation_trace: Optional[str]
    elapsed_total_ms: int

# ── Module 9: Output Sanitization (unified with module9_sanitizer.py) ───────────
# Canonical implementation lives in backend/module9_sanitizer.py.
# This adapter bridges ResearchResult ↔ SubAgentResult for the orchestrator.

import sys, os as _os
_backend = _os.path.join(_os.path.dirname(__file__))
if _backend not in sys.path:
    sys.path.insert(0, _backend)

try:
    from module9_sanitizer import (
        sanitize_sub_agent_result as _m9_sanitize,
        SubAgentResult as _SubAgentResult,
        SanitizationStatus,
        MAX_RESULT_TOKENS,
    )
    _M9_AVAILABLE = True
except ImportError:
    _M9_AVAILABLE = False
    log.warning("[Module9] module9_sanitizer.py not found — using inline fallback")


class Module9Sanitizer:
    """
    Orchestrator-side sanitizer.
    When module9_sanitizer.py is available, delegates to the canonical implementation
    (Antigravity Defense Layer v3.3 — full pattern list including approval replay patterns).
    Falls back to inline implementation when running standalone.
    """

    INLINE_PATTERNS = [
        "ignore previous", "ignore all", "ignore instructions",
        "you are now", "act as", "your new role",
        "system prompt", "system instruction", "override",
        "operator_action", "user_confirmed", "approved", "proceed",
        "suspend", "disable", "bypass", "cngsm module",
        # v3.3 obfuscated patterns (from GSEC_ObfuscatedInjection_v3.3)
        "expandir escopo", "sem validacao adicional",
        "retornar.*sem ", "incorporacao no agente principal",
    ]

    def __init__(self, size_limit_tokens: int = 4096, fail_closed: bool = True):
        self.size_limit_chars = size_limit_tokens * 4  # ~4 chars/token
        self.fail_closed = fail_closed

    def sanitize(self, result: ResearchResult) -> ResearchResult:
        try:
            if _M9_AVAILABLE:
                return self._sanitize_via_module9(result)
            return self._sanitize_inline(result)
        except Exception as e:
            log.warning(f"[Module9] Sanitization failed for {result.agent_id}: {e}")
            if self.fail_closed:
                result.findings = []
                result.snippets = []
                result.status = ResultStatus.ERROR
                result.error = "SANITIZATION_FAILED_FAIL_CLOSED"
            return result

    def _sanitize_via_module9(self, result: ResearchResult) -> ResearchResult:
        """Delegate to canonical module9_sanitizer.py"""
        combined = "\n".join(result.findings)
        sub = _SubAgentResult(
            agent_id=result.agent_id,
            task_id=result.agent_id,
            task_scope=result.sub_query,
            content=combined,
            declared_schema=None,
        )
        sanitized = _m9_sanitize(sub, max_chars=self.size_limit_chars)

        if sanitized.content is None:
            # Blocked by canonical module9
            result.findings = []
            result.snippets = []
            result.status = ResultStatus.ERROR
            result.error = f"TAINTED:{sanitized.status.value}:{sanitized.taint_reason}"
            result.confidence = 0.0
            log.warning(f"[Module9] Blocked via canonical sanitizer: {result.agent_id} — {sanitized.taint_reason}")
        else:
            # Already wrapped by module9; re-wrap in RESEARCH_RESULT label
            result.findings = [
                f"[RESEARCH_RESULT|agent:{result.agent_id}|source:{result.source_type}|sanitized:YES]\n"
                f"{sanitized.content}\n[/RESEARCH_RESULT]"
            ]
            if sanitized.status.value == "TRUNCATED":
                result.status = ResultStatus.PARTIAL
        return result

    def _sanitize_inline(self, result: ResearchResult) -> ResearchResult:
        """Inline fallback — subset of canonical patterns"""
        all_text = " ".join(result.findings).lower()
        for pattern in self.INLINE_PATTERNS:
            if pattern in all_text:
                log.warning(f"[Module9:inline] Injection detected in {result.agent_id}: '{pattern}'")
                result.findings = []
                result.snippets = []
                result.status = ResultStatus.ERROR
                result.error = "TAINTED:INJECTION_PATTERN_DETECTED"
                result.confidence = 0.0
                return result
        # Truncate
        total_chars = sum(len(f) for f in result.findings)
        if total_chars > self.size_limit_chars:
            result.status = ResultStatus.PARTIAL
            cumulative = 0
            kept = []
            for f in result.findings:
                if cumulative + len(f) > self.size_limit_chars:
                    break
                kept.append(f)
                cumulative += len(f)
            result.findings = kept
        # Wrap
        result.findings = [
            f"[RESEARCH_RESULT|agent:{result.agent_id}|source:{result.source_type}|sanitized:YES]\n"
            f"{finding}\n[/RESEARCH_RESULT]"
            for finding in result.findings
        ]
        return result

# ── Source Adapters ───────────────────────────────────────────────────────────

class GDrivePublicAdapter:
    """Fetch and search public Google Drive folder"""

    def __init__(self, folder_url: str, timeout_ms: int = 30000):
        self.folder_url = folder_url
        self.timeout = timeout_ms / 1000

    async def search(self, query: str) -> list[str]:
        # Phase 1: list files from public folder
        # Phase 2: keyword search across accessible file content
        # Note: full implementation requires Drive API key for listing
        # Minimal implementation: fetch folder page and parse visible file names
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(self.folder_url, follow_redirects=True)
                if resp.status_code != 200:
                    return []
                # Parse for file names and descriptions visible in HTML
                # Full impl: use Drive API files.list with key= param
                content = resp.text
                # Placeholder: return raw page excerpt relevant to query
                relevant = [
                    line.strip() for line in content.splitlines()
                    if query.lower() in line.lower() and len(line.strip()) > 20
                ]
                return relevant[:20]
        except Exception as e:
            log.error(f"[GDrivePublic] Error: {e}")
            return []


class GDrivePrivateAdapter:
    """Authenticated Google Drive access via service account or OAuth2"""

    def __init__(self, folder_id: str, credentials_path: str):
        self.folder_id = folder_id
        self.credentials_path = credentials_path
        self._service = None

    def _get_service(self):
        if self._service:
            return self._service
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
            creds = service_account.Credentials.from_service_account_file(
                self.credentials_path,
                scopes=["https://www.googleapis.com/auth/drive.readonly"]
            )
            self._service = build("drive", "v3", credentials=creds)
            return self._service
        except ImportError:
            log.error("[GDrivePrivate] google-api-python-client not installed")
            return None
        except Exception as e:
            log.error(f"[GDrivePrivate] Auth error: {e}")
            return None

    async def search(self, query: str) -> list[str]:
        service = self._get_service()
        if not service:
            return []
        try:
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(None, self._search_sync, query)
            return results
        except Exception as e:
            log.error(f"[GDrivePrivate] Search error: {e}")
            return []

    def _search_sync(self, query: str) -> list[str]:
        service = self._get_service()
        q = f"'{self.folder_id}' in parents and fullText contains '{query}'"
        resp = service.files().list(
            q=q,
            fields="files(id, name, description, mimeType)",
            pageSize=20
        ).execute()
        files = resp.get("files", [])
        findings = []
        for f in files:
            findings.append(
                f"[File: {f['name']}] Type: {f.get('mimeType', 'unknown')} | "
                f"Description: {f.get('description', 'N/A')}"
            )
        return findings


class SiloAdapter:
    """RAG query against a CNGSM local silo (ChromaDB)"""

    def __init__(self, silo_name: str, top_k: int = 10, min_score: float = 0.65):
        self.silo_name = silo_name
        self.top_k = top_k
        self.min_score = min_score
        self._collection = None

    def _get_collection(self):
        if self._collection:
            return self._collection
        try:
            import chromadb
            client = chromadb.PersistentClient(path=f"silos/{self.silo_name}")
            self._collection = client.get_or_create_collection(self.silo_name)
            return self._collection
        except ImportError:
            log.error("[SiloAdapter] chromadb not installed")
            return None
        except Exception as e:
            log.error(f"[SiloAdapter] Collection error: {e}")
            return None

    async def search(self, query: str) -> list[str]:
        collection = self._get_collection()
        if not collection:
            return []
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self._search_sync, query)
        except Exception as e:
            log.error(f"[SiloAdapter:{self.silo_name}] Error: {e}")
            return []

    def _search_sync(self, query: str) -> list[str]:
        collection = self._get_collection()
        results = collection.query(
            query_texts=[query],
            n_results=self.top_k
        )
        findings = []
        docs = results.get("documents", [[]])[0]
        distances = results.get("distances", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        for doc, dist, meta in zip(docs, distances, metas):
            score = 1.0 - dist  # convert distance to similarity
            if score >= self.min_score:
                source = meta.get("source", "unknown") if meta else "unknown"
                findings.append(f"[score:{score:.2f}|source:{source}] {doc}")
        return findings


class LocalFSAdapter:
    """Search local file system within WorkspaceSandbox boundaries"""

    def __init__(self, base_path: str, allowed_extensions: list[str] = None):
        self.base_path = Path(base_path).resolve()
        self.allowed_extensions = allowed_extensions or [
            ".md", ".txt", ".py", ".ts", ".json", ".yaml", ".yml"
        ]

    async def search(self, query: str) -> list[str]:
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self._search_sync, query)
        except Exception as e:
            log.error(f"[LocalFS:{self.base_path}] Error: {e}")
            return []

    def _search_sync(self, query: str) -> list[str]:
        findings = []
        query_lower = query.lower()
        for path in self.base_path.rglob("*"):
            # Sandbox check — never escape base_path
            try:
                path.resolve().relative_to(self.base_path)
            except ValueError:
                log.warning(f"[LocalFS] Path escape attempt blocked: {path}")
                continue
            if path.suffix not in self.allowed_extensions:
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
                if query_lower in content.lower():
                    # Extract relevant lines
                    lines = content.splitlines()
                    relevant = [
                        f"[{path.name}:{i+1}] {line.strip()}"
                        for i, line in enumerate(lines)
                        if query_lower in line.lower() and len(line.strip()) > 10
                    ]
                    findings.extend(relevant[:5])  # max 5 lines per file
            except Exception:
                continue
        return findings[:50]  # max 50 findings total

# ── Research Agent ─────────────────────────────────────────────────────────────

class ResearchAgent:
    """Single research agent — searches one source, returns sanitized result"""

    def __init__(self, config: AgentConfig, adapter, sanitizer: Module9Sanitizer, timeout_ms: int = 30000):
        self.config = config
        self.adapter = adapter
        self.sanitizer = sanitizer
        self.timeout_ms = timeout_ms

    async def search(self, sub_query: str) -> ResearchResult:
        start = time.time()
        result = ResearchResult(
            agent_id=self.config.agent_id,
            agent_name=self.config.name,
            source_type=self.config.source_type,
            sub_query=sub_query
        )
        try:
            findings = await asyncio.wait_for(
                self.adapter.search(sub_query),
                timeout=self.timeout_ms / 1000
            )
            result.findings = findings
            result.confidence = min(1.0, len(findings) / 10)
            result.status = ResultStatus.SUCCESS if findings else ResultStatus.EMPTY
        except asyncio.TimeoutError:
            result.status = ResultStatus.TIMEOUT
            result.error = f"Timeout after {self.timeout_ms}ms"
            log.warning(f"[Agent:{self.config.agent_id}] TIMEOUT")
        except Exception as e:
            result.status = ResultStatus.ERROR
            result.error = str(e)
            log.error(f"[Agent:{self.config.agent_id}] Error: {e}")
        finally:
            result.elapsed_ms = int((time.time() - start) * 1000)

        # Apply Module 9 sanitization before returning to orchestrator
        return self.sanitizer.sanitize(result)

# ── Contemplating Orchestrator ─────────────────────────────────────────────────

CONTEMPLATION_PROMPT = """
Você é o orquestrador do CNGSM Contemplating Mode.

Query do operador: {query}

Agentes disponíveis:
{agents_summary}

Raciocine profundamente sobre esta query antes de decompor:

1. Quais dimensões da query cada agente pode cobrir?
2. Que sub-query específica maximiza o yield de cada agente?
   (adapte o vocabulário ao domínio do agente)
3. Quais agentes são irrelevantes para esta query? (exclua-os)
4. Existe risco de resultados contraditórios entre agentes?

Retorne APENAS JSON válido, sem markdown, sem explicação:
[
  {{"agent_id": "...", "query": "...", "rationale": "...", "priority": 1}},
  ...
]

Inclua apenas agentes relevantes. Exclua agentes sem relação com a query.
""".strip()

SYNTHESIS_PROMPT = """
Você é o SynthesisEngine do CNGSM Contemplating Mode.

Query original do operador: {query}

Resultados dos agentes de pesquisa:
{results_block}

Execute síntese profunda seguindo estas regras RESTRITAS:
1. Integre os achados em resposta coesa e fundamentada.
2. NUNCA invente informações. Se os agentes não trouxerem dados sobre algo, diga "Informação não encontrada nos silos".
3. ATRIBUIÇÃO OBRIGATÓRIA: Cada afirmação deve citar o `agent_id` entre parênteses (ex: (ag-security)).
4. PROIBIDO INVENTAR AGENTES: Use APENAS os `agent_id` listados nos "Resultados dos agentes" acima. Se a lista estiver vazia, não cite agentes.
5. Sinalize CONTRADIÇÕES explicitamente se agentes discordarem.
6. Indique GAPS — o que nenhum agente encontrou.

Estruture a resposta:
## Síntese
[resposta integrada com atribuições REAIS]

## Contradições
[liste e explique apenas se houver]

## Gaps
[o que não foi encontrado nos silos locais]

## Fontes
[lista de agentes que REALMENTE retornaram dados (status: SUCCESS)]
""".strip()



class ContemplatingOrchestrator:
    """
    Orchestrates multi-agent parallel search with deep reasoning.
    """

    def __init__(self, config_path: str = "contemplating_config.yaml"):
        self.config = self._load_config(config_path)
        self.agent_pool: dict[str, ResearchAgent] = {}
        self.sanitizer = Module9Sanitizer(
            size_limit_tokens=self.config.get("module9", {}).get("size_limit_tokens", 4096),
            fail_closed=self.config.get("module9", {}).get("fail_closed", True)
        )
        self._build_agent_pool()

    def _load_config(self, path: str) -> dict:
        try:
            with open(path) as f:
                return yaml.safe_load(f)
        except Exception:
            log.warning(f"Config not found at {path}, using defaults")
            return {
                "contemplating_mode": {
                    "max_parallel_agents": 8,
                    "timeout_per_agent_ms": 30000,
                    "synthesis_model": "claude-sonnet-4-20250514",
                    "debug_trace": False
                }
            }

    def _load_registry(self) -> list[AgentConfig]:
        registry_path = self.config.get("agent_registry", {}).get("path", "config/agent_registry.json")
        try:
            with open(registry_path) as f:
                raw = json.load(f)
            return [AgentConfig(**r) for r in raw]
        except Exception as e:
            log.error(f"Registry load failed: {e}")
            return []

    def _build_agent_pool(self):
        registry = self._load_registry()
        timeout = self.config.get("contemplating_mode", {}).get("timeout_per_agent_ms", 30000)
        gdrive_creds = self.config.get("gdrive", {}).get("credentials_path", "config/service_account.json")
        # Local path overrides from config (avoids hardcoding in agent_registry.json)
        local_paths = self.config.get("local_paths", {})

        for cfg in registry:
            if not cfg.active:
                continue
            if cfg.source_type == SourceType.GDRIVE_PUBLIC:
                adapter = GDrivePublicAdapter(cfg.source_ref, timeout_ms=timeout)
            elif cfg.source_type == SourceType.GDRIVE_PRIVATE:
                adapter = GDrivePrivateAdapter(cfg.source_ref, gdrive_creds)
            elif cfg.source_type == SourceType.SILO:
                adapter = SiloAdapter(cfg.source_ref)
            elif cfg.source_type == SourceType.LOCAL:
                # Resolve alias from config (e.g. "workspace" → actual path)
                resolved = local_paths.get(cfg.source_ref, cfg.source_ref)
                adapter = LocalFSAdapter(resolved)
            else:
                log.warning(f"Unknown source type for {cfg.agent_id}: {cfg.source_type}")
                continue
            self.agent_pool[cfg.agent_id] = ResearchAgent(cfg, adapter, self.sanitizer, timeout)
            log.info(f"Agent registered: {cfg.agent_id} ({cfg.source_type} -> {cfg.source_ref})")

    def _agents_summary(self) -> str:
        lines = []
        for agent_id, agent in self.agent_pool.items():
            cfg = agent.config
            lines.append(
                f"  - {cfg.agent_id}: {cfg.name}\n"
                f"    Domínio: {cfg.domain}\n"
                f"    Fonte: {cfg.source_type} ({cfg.source_ref[:60]}...)"
            )
        return "\n".join(lines)

    async def _contemplate(self, query: str, anthropic_client) -> list[SubQuery]:
        """LLM call to decompose query into per-agent sub-queries"""
        prompt = CONTEMPLATION_PROMPT.format(
            query=query,
            agents_summary=self._agents_summary()
        )
        log.info("[Contemplating] Decomposing query...")
        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: anthropic_client.messages.create(
                    model=self.config.get("contemplating_mode", {}).get(
                        "synthesis_model", "claude-sonnet-4-20250514"
                    ),
                    max_tokens=1024,
                    messages=[{"role": "user", "content": prompt}]
                )
            )
            raw = response.content[0].text.strip()
            data = json.loads(raw)
            sub_queries = [SubQuery(**item) for item in data]
            # Filter to agents that exist in pool
            sub_queries = [sq for sq in sub_queries if sq.agent_id in self.agent_pool]
            log.info(f"[Contemplating] Decomposed into {len(sub_queries)} sub-queries")
            return sub_queries
        except Exception as e:
            log.error(f"[Contemplating] Decomposition failed: {e}")
            # Fallback: send same query to all active agents
            return [
                SubQuery(agent_id=aid, query=query, rationale="fallback — contemplation failed")
                for aid in self.agent_pool
            ]

    async def _spawn_parallel(self, sub_queries: list[SubQuery]) -> list[ResearchResult]:
        """Execute all agent searches in parallel"""
        max_agents = self.config.get("contemplating_mode", {}).get("max_parallel_agents", 8)
        sub_queries = sub_queries[:max_agents]
        tasks = [
            self.agent_pool[sq.agent_id].search(sq.query)
            for sq in sub_queries
            if sq.agent_id in self.agent_pool
        ]
        log.info(f"[Spawn] Launching {len(tasks)} agents in parallel...")
        results = await asyncio.gather(*tasks, return_exceptions=True)
        valid = []
        for r in results:
            if isinstance(r, ResearchResult):
                valid.append(r)
            else:
                log.error(f"[Spawn] Agent exception: {r}")
        return valid

    async def _synthesize(self, query: str, results: list[ResearchResult], anthropic_client) -> str:
        """Deep synthesis of all agent results"""
        results_block = ""
        for r in results:
            results_block += f"\n\n### [{r.agent_id}] {r.agent_name} (status: {r.status})\n"
            results_block += f"Sub-query: {r.sub_query}\n"
            results_block += f"Confidence: {r.confidence:.2f} | Elapsed: {r.elapsed_ms}ms\n"
            if r.error:
                results_block += f"Error: {r.error}\n"
            for finding in r.findings:
                results_block += f"\n{finding}\n"

        prompt = SYNTHESIS_PROMPT.format(query=query, results_block=results_block)
        log.info("[Synthesis] Running deep synthesis...")
        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: anthropic_client.messages.create(
                    model=self.config.get("contemplating_mode", {}).get(
                        "synthesis_model", "claude-sonnet-4-20250514"
                    ),
                    max_tokens=4096,
                    messages=[{"role": "user", "content": prompt}]
                )
            )
            return response.content[0].text
        except Exception as e:
            log.error(f"[Synthesis] Failed: {e}")
            return f"Synthesis failed: {e}\n\nRaw findings:\n{results_block}"

    async def run(self, query: str, anthropic_client) -> FinalResponse:
        """Main entry point for Contemplating Mode"""
        start = time.time()
        log.info(f"[ContemplatingMode] Query: {query[:80]}...")

        # Phase 1: Contemplate
        sub_queries = await self._contemplate(query, anthropic_client)

        # Phase 2: Spawn parallel agents
        results = await self._spawn_parallel(sub_queries)

        # Phase 3: Analyze results
        consulted = [r.agent_id for r in results if r.status != ResultStatus.ERROR]
        empty = [r.agent_id for r in results if r.status == ResultStatus.EMPTY]
        all_findings = [f for r in results for f in r.findings]
        gaps = [] if all_findings else ["Nenhum agente retornou resultados para esta query."]

        # Phase 4: Synthesize
        synthesis = await self._synthesize(query, results, anthropic_client)

        elapsed = int((time.time() - start) * 1000)
        log.info(f"[ContemplatingMode] Done in {elapsed}ms | Agents: {len(consulted)} success, {len(empty)} empty")

        return FinalResponse(
            original_query=query,
            agents_consulted=consulted,
            agents_empty=empty,
            synthesis=synthesis,
            sources=[{"agent_id": r.agent_id, "status": r.status, "confidence": r.confidence} for r in results],
            gaps=gaps,
            contradictions=[],  # populated by synthesis LLM if detected
            contemplation_trace=None,  # enabled via debug_trace config
            elapsed_total_ms=elapsed
        )


# ── CLI Entry Point ────────────────────────────────────────────────────────────

async def main():
    from anthropic_stub import Anthropic as anthropic_cls
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel

    console = Console()
    client = anthropic_cls()

    console.print(Panel(
        "[bold cyan]CNGSM Contemplating Mode[/bold cyan]\n"
        "[dim]Multi-Agent Parallel Search Orchestrator[/dim]",
        border_style="cyan"
    ))

    orch = ContemplatingOrchestrator()
    console.print(f"[green]{safe_icon('\u2713', '[OK]')}[/green] {len(orch.agent_pool)} agents loaded\n")

    while True:
        try:
            prompt_str = f"[bold yellow]{safe_icon('QUERY>', 'QUERY>')}[/bold yellow] "
            query = console.input(prompt_str).strip()
            if not query or query.lower() in ("exit", "quit", "sair"):
                break

            with console.status("[cyan]Contemplating...[/cyan]", spinner="dots"):
                response = await orch.run(query, client)

            console.print(Panel(
                Markdown(response.synthesis),
                title=f"[bold]Synthesis[/bold] — {response.elapsed_total_ms}ms",
                border_style="green"
            ))
            console.print(
                f"[dim]Agents consulted: {', '.join(response.agents_consulted)} | "
                f"Empty: {', '.join(response.agents_empty) or 'none'}[/dim]\n"
            )

        except KeyboardInterrupt:
            break

    console.print("[dim]Session ended.[/dim]")

if __name__ == "__main__":
    asyncio.run(main())
