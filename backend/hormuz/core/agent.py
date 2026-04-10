# -*- coding: utf-8 -*-
# ┌─────────────────────────────────────────────────────────────────────────┐
# │  ⚓  Agente Hormuz                                                           
# │  Criador    : Cloves Nascimento                                                  
# │  Papel      : Arquiteto de Ecossistemas Cognitivos                                                     
# │  Org        : CNGSM - Cognitive Neural & Generative Systems Management                                                      
# │  Versão     : 1.0.0                                                  
# │  Fingerprint: 8a3ee43b0c78e2b4                                              
# │  SHA-256    : 8a3ee43b0c78e2b4cb77204ffc5fb4ed6a33d8f90af59435d19533d9739c7d00                                                   
# │                                                                          
# │  © 2025 Cloves Nascimento — Todos os direitos reservados.                     
# │  Distribuição e modificação sujeitas aos termos da licença CNGSM.       
# └─────────────────────────────────────────────────────────────────────────┘

"""
CNGSM — Agente Hormuz
Core: estado persistente, fila de tarefas, execução em background
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import platform
import re
import shutil
import signal
import socket
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional, TYPE_CHECKING
if TYPE_CHECKING:
    import anthropic

# anthropic imported lazily to avoid Pydantic v1 conflict

log = logging.getLogger("hormuz.core")

# ─────────────────────────────────────────────────────────────
# Enums & constants
# ─────────────────────────────────────────────────────────────

class TaskStatus(str, Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    PAUSED    = "paused"
    DONE      = "done"
    FAILED    = "failed"
    CANCELLED = "cancelled"

class TaskPriority(int, Enum):
    LOW    = 0
    NORMAL = 1
    HIGH   = 2
    URGENT = 3

HORMUZ_HOME = Path(os.environ.get("HORMUZ_HOME", Path.home() / ".hormuz"))
STATE_FILE   = HORMUZ_HOME / "state.json"
TASK_DB      = HORMUZ_HOME / "tasks.json"
SYNC_FILE    = HORMUZ_HOME / "sync.json"
LOG_FILE     = HORMUZ_HOME / "hormuz.log"
PID_FILE     = HORMUZ_HOME / "hormuz.pid"

# ─────────────────────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────────────────────


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _device_id() -> str:
    hostname = socket.gethostname()
    return hashlib.md5(hostname.encode()).hexdigest()[:8]

def _ensure_home():
    HORMUZ_HOME.mkdir(parents=True, exist_ok=True)

def _load_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text())
    except Exception as e:
        log.warning(f'Failed to load {path}: {e}')
    return default

def _save_json(path: Path, data: Any):
    _ensure_home()
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    tmp.replace(path)   # atomic write

@dataclass
class HormuzTask:
    task_id:     str            = field(default_factory=lambda: str(uuid.uuid4())[:8])
    title:       str            = ""
    description: str            = ""
    task_type:   str            = "generic"        # file_ops | organize | tag | generic | ai
    status:      TaskStatus     = TaskStatus.PENDING
    priority:    TaskPriority   = TaskPriority.NORMAL
    created_at:  str            = field(default_factory=lambda: _now())
    updated_at:  str            = field(default_factory=lambda: _now())
    started_at:  Optional[str]  = None
    finished_at: Optional[str]  = None
    device_id:   str            = field(default_factory=_device_id)
    progress:    float          = 0.0              # 0.0 – 1.0
    result:      Optional[str]  = None
    error:       Optional[str]  = None
    params:      dict           = field(default_factory=dict)
    tags:        list[str]      = field(default_factory=list)
    parent_id:   Optional[str]  = None            # subtask support
    subtask_ids: list[str]      = field(default_factory=list)
    background:  bool           = True

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"]   = self.status.value
        d["priority"] = self.priority.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "HormuzTask":
        d = dict(d)
        d["status"]   = TaskStatus(d.get("status", "pending"))
        d["priority"] = TaskPriority(d.get("priority", 1))
        return cls(**d)


@dataclass
class DeviceState:
    device_id:    str = field(default_factory=_device_id)
    hostname:     str = field(default_factory=socket.gethostname)
    platform:     str = field(default_factory=platform.system)
    last_seen:    str = field(default_factory=_now)
    active_tasks: list[str] = field(default_factory=list)
    hormuz_version: str = "1.0"


@dataclass
class HormuzState:
    """Global persistent state — written to disk on every mutation"""
    version:       str        = "1.0"
    session_id:    str        = field(default_factory=lambda: str(uuid.uuid4())[:8])
    device:        DeviceState = field(default_factory=DeviceState)
    total_tasks:   int        = 0
    done_tasks:    int        = 0
    failed_tasks:  int        = 0
    last_sync:     Optional[str] = None
    config:        dict       = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _device_id() -> str:
    hostname = socket.gethostname()
    return hashlib.md5(hostname.encode()).hexdigest()[:8]

def _ensure_home():
    HORMUZ_HOME.mkdir(parents=True, exist_ok=True)

def _load_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text())
    except Exception as e:
        log.warning(f"Failed to load {path}: {e}")
    return default

def _save_json(path: Path, data: Any):
    _ensure_home()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    tmp.replace(path)   # atomic write

# ─────────────────────────────────────────────────────────────
# Persistent Task Store
# ─────────────────────────────────────────────────────────────

class TaskStore:
    """Thread-safe persistent task database"""

    def __init__(self):
        self._lock = threading.Lock()
        self._tasks: dict[str, HormuzTask] = {}
        self._load()

    def _load(self):
        raw = _load_json(TASK_DB, {})
        self._tasks = {k: HormuzTask.from_dict(v) for k, v in raw.items()}
        log.info(f"[TaskStore] Loaded {len(self._tasks)} tasks")

    def _save(self):
        _save_json(TASK_DB, {k: v.to_dict() for k, v in self._tasks.items()})

    def add(self, task: HormuzTask) -> HormuzTask:
        with self._lock:
            self._tasks[task.task_id] = task
            self._save()
        return task

    def get(self, task_id: str) -> Optional[HormuzTask]:
        return self._tasks.get(task_id)

    def update(self, task: HormuzTask):
        with self._lock:
            task.updated_at = _now()
            self._tasks[task.task_id] = task
            self._save()

    def all(self) -> list[HormuzTask]:
        return list(self._tasks.values())

    def pending(self) -> list[HormuzTask]:
        return sorted(
            [t for t in self._tasks.values() if t.status == TaskStatus.PENDING],
            key=lambda t: (-t.priority.value, t.created_at)
        )

    def running(self) -> list[HormuzTask]:
        return [t for t in self._tasks.values() if t.status == TaskStatus.RUNNING]

    def by_device(self, device_id: str) -> list[HormuzTask]:
        return [t for t in self._tasks.values() if t.device_id == device_id]

    def cancel(self, task_id: str) -> bool:
        with self._lock:
            t = self._tasks.get(task_id)
            if not t or t.status in (TaskStatus.DONE, TaskStatus.FAILED):
                return False
            t.status = TaskStatus.CANCELLED
            t.updated_at = _now()
            self._save()
        return True


# ─────────────────────────────────────────────────────────────
# File Operations Engine
# ─────────────────────────────────────────────────────────────

class FileOpsEngine:
    """Organize, rename, tag files — runs inside WorkspaceSandbox"""

    SAFE_EXTENSIONS = {
        ".md", ".txt", ".py", ".ts", ".js", ".json", ".yaml", ".yml",
        ".csv", ".pdf", ".docx", ".xlsx", ".pptx", ".png", ".jpg", ".jpeg"
    }

    def __init__(self, sandbox_root: Path):
        self.root = sandbox_root.resolve()

    def _safe(self, path: Path) -> Path:
        """Enforce sandbox — raise if path escapes root"""
        resolved = path.resolve()
        if not str(resolved).startswith(str(self.root)):
            raise PermissionError(f"Path escape blocked: {path}")
        return resolved

    async def organize_by_type(self, target: Path, dry_run: bool = False) -> dict:
        """Move files into type-based subdirectories"""
        target = self._safe(target)
        moved = []
        errors = []
        type_map = {
            "docs":   {".md", ".txt", ".docx", ".pdf"},
            "code":   {".py", ".ts", ".js", ".sh", ".ps1"},
            "data":   {".json", ".yaml", ".yml", ".csv", ".xlsx"},
            "media":  {".png", ".jpg", ".jpeg", ".gif", ".mp4"},
            "slides": {".pptx"},
        }
        ext_to_folder = {}
        for folder, exts in type_map.items():
            for ext in exts:
                ext_to_folder[ext] = folder

        for file in target.rglob("*"):
            if not file.is_file():
                continue
            folder_name = ext_to_folder.get(file.suffix.lower(), "other")
            dest_dir = target / folder_name
            dest = dest_dir / file.name
            if dest == file:
                continue
            try:
                if not dry_run:
                    dest_dir.mkdir(exist_ok=True)
                    shutil.move(str(file), str(dest))
                moved.append({"from": str(file.relative_to(self.root)),
                               "to": str(dest.relative_to(self.root))})
            except Exception as e:
                errors.append({"file": str(file), "error": str(e)})

        return {"moved": moved, "errors": errors, "dry_run": dry_run}

    async def smart_rename(self, target: Path, ai_client: "anthropic.Anthropic",
                            dry_run: bool = False) -> dict:
        """Use LLM to suggest better file names based on content"""
        target = self._safe(target)
        suggestions = []

        files = [f for f in target.iterdir() if f.is_file()
                 and f.suffix in self.SAFE_EXTENSIONS][:20]  # limit per call

        if not files:
            return {"suggestions": [], "applied": []}

        # Build prompt with file names + first 200 chars of content
        file_previews = []
        for f in files:
            try:
                content = f.read_text(errors="ignore")[:200]
            except Exception:
                content = "(binary)"
            file_previews.append(f"File: {f.name}\nPreview: {content}\n")

        prompt = (
            "Analise estes arquivos e sugira nomes melhores — descritivos, sem espaços, "
            "snake_case, com a extensão original preservada.\n"
            "Retorne JSON: [{\"original\": \"nome.ext\", \"suggested\": \"novo_nome.ext\", "
            "\"reason\": \"...\"}]\n\n" + "\n".join(file_previews)
        )

        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(None, lambda: ai_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        ))
        raw = resp.content[0].text.strip()
        # Strip markdown if present
        raw = re.sub(r"```json\s*|\s*```", "", raw).strip()
        try:
            suggestions = json.loads(raw)
        except Exception:
            suggestions = []

        applied = []
        for s in suggestions:
            orig = target / s["original"]
            dest = target / s["suggested"]
            if orig.exists() and orig != dest and not dest.exists():
                if not dry_run:
                    orig.rename(dest)
                applied.append(s)

        return {"suggestions": suggestions, "applied": applied, "dry_run": dry_run}

    async def tag_files(self, target: Path, ai_client: "anthropic.Anthropic") -> dict:
        """Generate a tag index for all files in target — writes tags.json"""
        target = self._safe(target)
        files = [f for f in target.rglob("*") if f.is_file()
                 and f.suffix in self.SAFE_EXTENSIONS][:30]

        tag_index = {}
        for f in files:
            try:
                content = f.read_text(errors="ignore")[:500]
            except Exception:
                continue
            prompt = (
                f"Arquivo: {f.name}\nConteúdo: {content}\n\n"
                "Retorne apenas uma lista JSON de 3-7 tags descritivas em português. "
                "Ex: [\"segurança\", \"python\", \"automação\"]"
            )
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(None, lambda: ai_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=128,
                messages=[{"role": "user", "content": prompt}]
            ))
            raw = resp.content[0].text.strip()
            raw = re.sub(r"```json\s*|\s*```", "", raw).strip()
            try:
                tags = json.loads(raw)
                tag_index[str(f.relative_to(self.root))] = tags
            except Exception:
                pass

        tags_file = target / "tags.json"
        _save_json(tags_file, tag_index)
        return {"tagged": len(tag_index), "index_file": str(tags_file)}


# ─────────────────────────────────────────────────────────────
# Cross-Device Sync Engine
# ─────────────────────────────────────────────────────────────

class SyncEngine:
    """
    Sync task state across devices via shared file (Obsidian vault,
    Google Drive mount, or any shared path).
    """

    def __init__(self, sync_path: Optional[Path] = None):
        self.sync_path = sync_path or SYNC_FILE
        self.device_id = _device_id()

    def push(self, store: TaskStore, state: HormuzState):
        """Write this device's task state to sync file"""
        payload = {
            "device_id":   self.device_id,
            "hostname":    socket.gethostname(),
            "pushed_at":   _now(),
            "tasks":       {t.task_id: t.to_dict() for t in store.all()},
            "device_state": asdict(state.device),
        }
        _save_json(self.sync_path, payload)
        log.info(f"[Sync] Pushed {len(payload['tasks'])} tasks to {self.sync_path}")

    def pull(self, store: TaskStore) -> list[str]:
        """Merge remote tasks into local store — returns list of imported task_ids"""
        remote = _load_json(self.sync_path, {})
        if not remote or remote.get("device_id") == self.device_id:
            return []    # nothing to pull from same device

        imported = []
        for task_id, t_dict in remote.get("tasks", {}).items():
            local = store.get(task_id)
            remote_task = HormuzTask.from_dict(t_dict)

            if local is None:
                store.add(remote_task)
                imported.append(task_id)
            elif remote_task.updated_at > local.updated_at:
                # Remote is newer — apply update but keep local running state
                if local.status == TaskStatus.RUNNING:
                    continue   # don't clobber running local task
                store.update(remote_task)
                imported.append(task_id)

        log.info(f"[Sync] Pulled {len(imported)} updated tasks from {remote.get('device_id')}")
        return imported

    def resume_context(self, store: TaskStore) -> list[HormuzTask]:
        """Return tasks that were in progress on another device"""
        remote = _load_json(self.sync_path, {})
        if not remote or remote.get("device_id") == self.device_id:
            return []
        paused = [
            HormuzTask.from_dict(t)
            for t in remote.get("tasks", {}).values()
            if t.get("status") in (TaskStatus.PAUSED.value, TaskStatus.RUNNING.value)
            and t.get("device_id") != self.device_id
        ]
        return paused


# ─────────────────────────────────────────────────────────────
# Background Worker
# ─────────────────────────────────────────────────────────────

TaskHandler = Callable[[HormuzTask, Any], Any]

class BackgroundWorker:
    """
    Runs pending tasks in background using idle CPU.
    Respects max_concurrent and cpu_threshold.
    """

    def __init__(self, store: TaskStore, ai_client: "anthropic.Anthropic",
                 max_concurrent: int = 2):
        self.store = store
        self.client = ai_client
        self.max_concurrent = max_concurrent
        self._running = False
        self._handlers: dict[str, TaskHandler] = {}
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def register_handler(self, task_type: str, handler: TaskHandler):
        self._handlers[task_type] = handler

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._worker_loop, daemon=True, name="hormuz-bg")
        self._thread.start()
        log.info("[Worker] Background worker started")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        log.info("[Worker] Background worker stopped")

    def _worker_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._async_loop())

    async def _async_loop(self):
        while self._running:
            running_count = len(self.store.running())
            if running_count < self.max_concurrent:
                pending = self.store.pending()
                for task in pending[:self.max_concurrent - running_count]:
                    asyncio.create_task(self._execute(task))
            await asyncio.sleep(2)   # poll every 2s

    async def _execute(self, task: HormuzTask):
        task.status    = TaskStatus.RUNNING
        task.started_at = _now()
        task.device_id  = _device_id()
        self.store.update(task)
        log.info(f"[Worker] Starting task {task.task_id}: {task.title}")

        handler = self._handlers.get(task.task_type)
        if not handler:
            task.status = TaskStatus.FAILED
            task.error  = f"No handler for task_type '{task.task_type}'"
            task.finished_at = _now()
            self.store.update(task)
            return

        try:
            result = await handler(task, self.client)
            task.status      = TaskStatus.DONE
            task.progress    = 1.0
            task.result      = json.dumps(result) if not isinstance(result, str) else result
            task.finished_at = _now()
            log.info(f"[Worker] Task {task.task_id} done")
        except Exception as e:
            task.status      = TaskStatus.FAILED
            task.error       = str(e)
            task.finished_at = _now()
            log.error(f"[Worker] Task {task.task_id} failed: {e}")
        finally:
            self.store.update(task)


# ─────────────────────────────────────────────────────────────
# Hormuz Agent — main entry point
# ─────────────────────────────────────────────────────────────

class HormuzAgent:
    """
    Agente Hormuz — persistent, cross-device, background-capable.

    Usage:
        agent = HormuzAgent()
        agent.start()
        agent.submit_task(HormuzTask(title="Organize workspace", task_type="organize",
                                     params={"path": "/path/to/dir"}))
    """

    def __init__(self, sandbox_root: Optional[Path] = None,
                 sync_path: Optional[Path] = None):
        _ensure_home()
        self.store   = TaskStore()
        self.state   = self._load_state()
        self.sync    = SyncEngine(sync_path)
        from anthropic_stub import Anthropic as _Anthropic
        self.client  = _Anthropic()
        self.files   = FileOpsEngine(sandbox_root or Path.cwd())
        self.worker  = BackgroundWorker(self.store, self.client)
        self._register_handlers()

    def _load_state(self) -> HormuzState:
        raw = _load_json(STATE_FILE, {})
        if not raw:
            return HormuzState()
        try:
            raw["device"] = DeviceState(**raw.get("device", {}))
            return HormuzState(**raw)
        except Exception:
            return HormuzState()

    def _save_state(self):
        d = asdict(self.state)
        _save_json(STATE_FILE, d)

    def _register_handlers(self):
        self.worker.register_handler("organize", self._handle_organize)
        self.worker.register_handler("rename",   self._handle_rename)
        self.worker.register_handler("tag",      self._handle_tag)
        self.worker.register_handler("ai",       self._handle_ai)
        self.worker.register_handler("generic",  self._handle_generic)

    # ── Task Handlers ─────────────────────────────────────────

    async def _handle_organize(self, task: HormuzTask, client: "anthropic.Anthropic") -> dict:
        path = Path(task.params.get("path", "."))
        dry_run = task.params.get("dry_run", False)
        task.progress = 0.1; self.store.update(task)
        result = await self.files.organize_by_type(path, dry_run=dry_run)
        task.progress = 1.0; self.store.update(task)
        return result

    async def _handle_rename(self, task: HormuzTask, client: "anthropic.Anthropic") -> dict:
        path = Path(task.params.get("path", "."))
        dry_run = task.params.get("dry_run", False)
        task.progress = 0.2; self.store.update(task)
        result = await self.files.smart_rename(path, client, dry_run=dry_run)
        task.progress = 1.0; self.store.update(task)
        return result

    async def _handle_tag(self, task: HormuzTask, client: "anthropic.Anthropic") -> dict:
        path = Path(task.params.get("path", "."))
        task.progress = 0.1; self.store.update(task)
        result = await self.files.tag_files(path, client)
        task.progress = 1.0; self.store.update(task)
        return result

    async def _handle_ai(self, task: HormuzTask, client: "anthropic.Anthropic") -> str:
        prompt = task.params.get("prompt", task.description)
        task.progress = 0.3; self.store.update(task)
        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(None, lambda: client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}]
        ))
        task.progress = 1.0; self.store.update(task)
        return resp.content[0].text

    async def _handle_generic(self, task: HormuzTask, client: "anthropic.Anthropic") -> str:
        await asyncio.sleep(0.5)   # placeholder
        return f"Task '{task.title}' executed (generic handler)"

    # ── Public API ────────────────────────────────────────────

    def start(self):
        """Start background worker and pull sync"""
        self.worker.start()
        pulled = self.sync.pull(self.store)
        if pulled:
            log.info(f"[Hormuz] Pulled {len(pulled)} tasks from sync")
        # Write PID for daemon management
        PID_FILE.write_text(str(os.getpid()))
        log.info(f"[Hormuz] Agent started | device:{_device_id()} | pid:{os.getpid()}")

    def stop(self):
        self.worker.stop()
        self.sync.push(self.store, self.state)
        self._save_state()
        if PID_FILE.exists():
            PID_FILE.unlink()
        log.info("[Hormuz] Agent stopped")

    def submit_task(self, task: HormuzTask) -> HormuzTask:
        """Add task to queue — background worker picks it up automatically"""
        self.store.add(task)
        self.state.total_tasks += 1
        self._save_state()
        log.info(f"[Hormuz] Task submitted: {task.task_id} '{task.title}'")
        return task

    def status(self) -> dict:
        all_tasks = self.store.all()
        return {
            "device":   _device_id(),
            "hostname": socket.gethostname(),
            "pending":  len([t for t in all_tasks if t.status == TaskStatus.PENDING]),
            "running":  len([t for t in all_tasks if t.status == TaskStatus.RUNNING]),
            "done":     len([t for t in all_tasks if t.status == TaskStatus.DONE]),
            "failed":   len([t for t in all_tasks if t.status == TaskStatus.FAILED]),
            "total":    len(all_tasks),
        }

    def resume_from_other_device(self) -> list[HormuzTask]:
        """Return tasks paused/running on another device that can continue here"""
        return self.sync.resume_context(self.store)

    def sync_now(self):
        self.sync.push(self.store, self.state)
        self.sync.pull(self.store)
