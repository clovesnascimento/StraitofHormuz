# -*- coding: utf-8 -*-
# ┌─────────────────────────────────────────────────────────────────────────┐
# │  ⚓  Agente Hormuz — Managed Agents Layer                                
# │  BRIDGE: Liga os 4 pilares + CLI Rich                                   
# │  Criador    : Cloves Nascimento                                          
# │  Fingerprint: 8a3ee43b0c78e2b4                                          
# └─────────────────────────────────────────────────────────────────────────┘
"""
HORMUZ BRIDGE
─────────────
Ponto de entrada unificado do Managed Agents Layer.
Liga Agent Definition → Environment Sync → Session Manager → Event Stream.
Registra os handlers das ferramentas customizadas Hormuz.
Substitui o BackgroundWorker local para tarefas longas — o contêiner executa.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Optional

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich import box

# ── Managed layer imports ──────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from managed.agent.definition   import AgentDefinition
from managed.environment.sync   import EnvironmentSync
from managed.session.manager    import SessionManager
from managed.events.stream      import EventStream, CustomToolExecutor, stream_turn
from core.identity               import verify_identity, attribution_header, FINGERPRINT

log     = logging.getLogger("hormuz.bridge")
console = Console()

HORMUZ_HOME = Path(os.environ.get("HORMUZ_HOME", Path.home() / ".hormuz"))


# ─────────────────────────────────────────────────────────────────────────────
# Custom tool handlers — wired from local FileOpsEngine
# ─────────────────────────────────────────────────────────────────────────────

def _make_tool_executor(workspace: Path, agent: "HormuzBridge") -> CustomToolExecutor:
    executor = CustomToolExecutor()

    # Lazy import to avoid circular deps
    from core.agent import FileOpsEngine
    import anthropic
    import asyncio

    file_ops = FileOpsEngine(workspace)
    ai_client = anthropic.Anthropic()

    def _run_async(coro):
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, coro)
                    return future.result()
            return loop.run_until_complete(coro)
        except RuntimeError:
            return asyncio.run(coro)

    def handle_organize(tool_name: str, inp: dict) -> dict:
        path    = Path(inp["path"])
        dry_run = inp.get("dry_run", False)
        return _run_async(file_ops.organize_by_type(path, dry_run=dry_run))

    def handle_rename(tool_name: str, inp: dict) -> dict:
        path    = Path(inp["path"])
        dry_run = inp.get("dry_run", False)
        return _run_async(file_ops.smart_rename(path, ai_client, dry_run=dry_run))

    def handle_tag(tool_name: str, inp: dict) -> dict:
        path = Path(inp["path"])
        return _run_async(file_ops.tag_files(path, ai_client))

    def handle_sync_push(tool_name: str, inp: dict) -> dict:
        from core.agent import HormuzAgent
        sync_path = Path(inp["sync_path"])
        # Re-use existing TaskStore + SyncEngine
        from core.agent import TaskStore, SyncEngine, HormuzState
        store  = TaskStore()
        sync   = SyncEngine(sync_path)
        state  = HormuzState()
        sync.push(store, state)
        return {"pushed": len(store.all()), "sync_path": str(sync_path)}

    def handle_verify_identity(tool_name: str, inp: dict) -> dict:
        ok = verify_identity(strict=False)
        return {
            "fingerprint": FINGERPRINT,
            "sha256":      "8a3ee43b0c78e2b4cb77204ffc5fb4ed6a33d8f90af59435d19533d9739c7d00",
            "status":      "PASS" if ok else "FAIL",
            "creator":     "Cloves Nascimento",
            "org":         "CNGSM — Cognitive Neural & Generative Systems Management",
        }

    executor.register("hormuz_file_organize",  handle_organize)
    executor.register("hormuz_smart_rename",   handle_rename)
    executor.register("hormuz_tag_index",      handle_tag)
    executor.register("hormuz_sync_push",      handle_sync_push)
    executor.register("hormuz_verify_identity", handle_verify_identity)

    return executor


# ─────────────────────────────────────────────────────────────────────────────
# HormuzBridge — unified entry point
# ─────────────────────────────────────────────────────────────────────────────

class HormuzBridge:
    """
    Unified entry point for Hormuz Managed Agents.
    Handles Agent + Environment + Session lifecycle.
    All long-running tasks delegate to the managed container.
    """

    def __init__(
        self,
        workspace:  Path,
        sync_path:  Optional[Path] = None,
        api_key:    Optional[str] = None,
        enable_web: bool = True,
    ):
        verify_identity(strict=True)

        self.workspace   = workspace.resolve()
        self.sync_path   = sync_path
        self.api_key     = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self._agent_def  = AgentDefinition(enable_web=enable_web, api_key=self.api_key)
        self._env_sync   = EnvironmentSync(workspace=self.workspace, api_key=self.api_key)
        self._session_mgr = SessionManager(api_key=self.api_key)
        self._executor   = _make_tool_executor(self.workspace, self)
        self._active_session_id: Optional[str] = None
        self._stream: Optional[EventStream] = None

    # ── Bootstrap ──────────────────────────────────────────────────────────

    def bootstrap(self) -> tuple[str, str]:
        """
        Ensure agent and environment exist.
        Returns (agent_id, env_id).
        """
        with console.status("[cyan]Verificando Agent Definition...[/cyan]"):
            agent_rec = self._agent_def.get_or_create()

        with console.status("[cyan]Sincronizando Environment...[/cyan]"):
            env_rec = self._env_sync.get_or_create()

        console.print(
            f"[green]✓[/green] Agent: [yellow]{agent_rec.agent_id}[/yellow] | "
            f"Env: [yellow]{env_rec.env_id}[/yellow]"
        )
        return agent_rec.agent_id, env_rec.env_id

    # ── Session lifecycle ──────────────────────────────────────────────────

    def new_session(self, task: str) -> str:
        agent_id, env_id = self.bootstrap()
        with console.status("[cyan]Iniciando sessão...[/cyan]"):
            rec = self._session_mgr.start(agent_id, env_id, task)

        self._active_session_id = rec.session_id
        self._stream = EventStream(
            session_id    = rec.session_id,
            tool_executor = self._executor,
            api_key       = self.api_key,
        )
        console.print(f"[green]✓[/green] Sessão: [yellow]{rec.session_id}[/yellow]")
        return rec.session_id

    def resume_session(self, session_id: str) -> str:
        with console.status("[cyan]Retomando sessão...[/cyan]"):
            rec = self._session_mgr.resume(session_id)
        self._active_session_id = rec.session_id
        self._stream = EventStream(
            session_id    = rec.session_id,
            tool_executor = self._executor,
            api_key       = self.api_key,
        )
        console.print(f"[green]✓[/green] Sessão retomada: [yellow]{rec.session_id}[/yellow]")
        return rec.session_id

    def pause_session(self):
        if self._active_session_id:
            self._session_mgr.pause(self._active_session_id)
            console.print(f"[yellow]Sessão {self._active_session_id} pausada.[/yellow]")

    def stop_session(self):
        if self._active_session_id:
            self._session_mgr.stop(self._active_session_id)
            self._active_session_id = None
            self._stream = None

    # ── Communication ──────────────────────────────────────────────────────

    def send(self, message: str) -> str:
        """Send a user turn and stream response. Returns full text."""
        if not self._stream:
            raise RuntimeError("No active session. Call new_session() first.")
        return stream_turn(
            session_id    = self._active_session_id,
            message       = message,
            tool_executor = self._executor,
            api_key       = self.api_key,
            rich_console  = console,
        )

    def interrupt(self, redirect: Optional[str] = None):
        """Interrupt current execution. Optionally redirect."""
        if self._stream:
            self._stream.interrupt(redirect_message=redirect)

    def direct(self, message: str):
        """High-priority message to redirect mid-execution."""
        if self._stream:
            self._stream.direct(message)

    # ── Status helpers ─────────────────────────────────────────────────────

    def list_sessions(self) -> Table:
        sessions = self._session_mgr.list_all()
        table = Table(box=box.SIMPLE_HEAVY, header_style="bold dim", show_edge=False)
        table.add_column("ID",       width=12)
        table.add_column("Status",   width=10)
        table.add_column("Task",     min_width=30)
        table.add_column("Device",   width=8)
        table.add_column("Events",   width=8)
        table.add_column("Updated",  width=20)
        for s in sorted(sessions, key=lambda x: x.updated_at, reverse=True):
            color = {"active": "green", "paused": "yellow",
                     "done": "dim", "error": "red"}.get(s.status, "white")
            table.add_row(
                s.session_id[:10], f"[{color}]{s.status}[/{color}]",
                s.task[:45], s.device_id, str(s.event_count),
                s.updated_at[:19].replace("T", " ")
            )
        return table

    def resumable_sessions(self) -> list:
        return self._session_mgr.list_resumable()


# ─────────────────────────────────────────────────────────────────────────────
# Rich CLI — Managed Mode
# ─────────────────────────────────────────────────────────────────────────────

MANAGED_MENU = """
[bold cyan]⚓ AGENTE HORMUZ — MANAGED MODE[/bold cyan]

  [yellow]n[/yellow]  Nova sessão
  [yellow]r[/yellow]  Retomar sessão
  [yellow]s[/yellow]  Listar sessões
  [yellow]p[/yellow]  Pausar sessão ativa
  [yellow]i[/yellow]  Interromper execução
  [yellow]d[/yellow]  Direct (redirecionar)
  [yellow]e[/yellow]  Enviar mensagem
  [yellow]x[/yellow]  Exportar config do ambiente
  [yellow]q[/yellow]  Sair
"""

def run_cli(workspace: Path, sync_path: Optional[Path] = None):
    bridge = HormuzBridge(workspace=workspace, sync_path=sync_path)

    console.print(Panel(
        f"[bold cyan]⚓ Agente Hormuz — Managed Agents[/bold cyan]\n"
        f"[dim]{attribution_header()}[/dim]",
        border_style="cyan"
    ))

    # Show resumable sessions from other devices
    resumable = bridge.resumable_sessions()
    if resumable:
        console.print(f"\n[magenta]⚡ {len(resumable)} sessão(ões) retomável(is) de outro dispositivo:[/magenta]")
        for s in resumable:
            console.print(f"  [yellow]{s.session_id}[/yellow] — {s.task[:50]} [{s.device_id}]")

    while True:
        console.print(MANAGED_MENU)
        choice = Prompt.ask("Opção", default="e")

        try:
            if choice == "n":
                task = Prompt.ask("Descreva a tarefa")
                bridge.new_session(task)

            elif choice == "r":
                sid = Prompt.ask("Session ID para retomar")
                bridge.resume_session(sid)

            elif choice == "s":
                console.print(bridge.list_sessions())

            elif choice == "p":
                bridge.pause_session()

            elif choice == "i":
                redirect = Prompt.ask("Mensagem de redirecionamento (Enter para apenas interromper)", default="")
                bridge.interrupt(redirect or None)

            elif choice == "d":
                msg = Prompt.ask("Mensagem direta")
                bridge.direct(msg)

            elif choice == "e":
                if not bridge._active_session_id:
                    task = Prompt.ask("Nenhuma sessão ativa. Descreva a tarefa")
                    bridge.new_session(task)
                msg = Prompt.ask("\n[bold yellow]HORMUZ>[/bold yellow]")
                console.print(Panel("", title="Resposta", border_style="green"), end="")
                bridge.send(msg)

            elif choice == "x":
                out = workspace / "hormuz_env_config.json"
                bridge._env_sync.export_config(output_path=out)
                console.print(f"[green]✓[/green] Config exportada: {out}")

            elif choice in ("q", "sair"):
                bridge.pause_session()
                console.print("[dim]Sessão pausada. Agente continua no container.[/dim]")
                break

        except KeyboardInterrupt:
            console.print("\n[yellow]Ctrl+C — pausando sessão...[/yellow]")
            bridge.pause_session()
            break
        except Exception as e:
            console.print(f"[red]Erro: {e}[/red]")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Agente Hormuz — Managed Mode")
    parser.add_argument("workspace", nargs="?", default=".", help="Workspace path")
    parser.add_argument("--sync",    default=None,           help="Sync file path")
    args = parser.parse_args()

    run_cli(
        workspace = Path(args.workspace),
        sync_path = Path(args.sync) if args.sync else None,
    )
