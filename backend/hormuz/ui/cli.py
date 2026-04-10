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
CLI: interface Rich com dashboard, submit de tarefas e monitoramento
"""

import asyncio
import json
import os
import platform
import signal
import sys
import time
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

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich.text import Text
from rich import box
from rich.columns import Columns

# Local imports — add both hormuz parent and backend/ (for anthropic_stub, module9, etc.)
_hormuz_parent = str(Path(__file__).parent.parent)          # backend/hormuz
_backend_dir   = str(Path(__file__).parent.parent.parent)   # backend/
for _p in (_hormuz_parent, _backend_dir):
    if _p not in sys.path:
        sys.path.insert(0, _p)
from core.agent import HormuzAgent, HormuzTask, TaskStatus, TaskPriority, _device_id

console = Console()

# ─────────────────────────────────────────────────────────────
# UI Components
# ─────────────────────────────────────────────────────────────

STATUS_COLORS = {
    TaskStatus.PENDING:   "yellow",
    TaskStatus.RUNNING:   "cyan",
    TaskStatus.PAUSED:    "magenta",
    TaskStatus.DONE:      "green",
    TaskStatus.FAILED:    "red",
    TaskStatus.CANCELLED: "dim",
}

STATUS_ICONS = {
    TaskStatus.PENDING:   safe_icon("⏳", "..."),
    TaskStatus.RUNNING:   safe_icon("⚡", "RUN"),
    TaskStatus.PAUSED:    safe_icon("⏸", "||"),
    TaskStatus.DONE:      safe_icon("✓", "DONE"),
    TaskStatus.FAILED:    safe_icon("✗", "FAIL"),
    TaskStatus.CANCELLED: safe_icon("−", "CAN"),
}

def render_header(agent: HormuzAgent) -> Panel:
    st = agent.status()
    grid = Table.grid(expand=True)
    grid.add_column(justify="left")
    grid.add_column(justify="right")
    header_title = safe_icon("⚓", "[ANCHOR]") + " AGENTE HORMUZ"
    grid.add_row(
        Text(header_title, style="bold cyan"),
        Text(f"device:{st['device']} | {st['hostname']}", style="dim")
    )
    summary = (
        f"[yellow]{safe_icon('⏳', '...')} {st['pending']}[/yellow]  "
        f"[cyan]{safe_icon('⚡', 'RUN')} {st['running']}[/cyan]  "
        f"[green]{safe_icon('✓', 'OK')} {st['done']}[/green]  "
        f"[red]{safe_icon('✗', 'ERR')} {st['failed']}[/red]"
    )
    grid.add_row(Text(summary), Text(""))
    return Panel(grid, border_style="cyan", padding=(0, 1))


def render_task_table(agent: HormuzAgent, limit: int = 20) -> Table:
    table = Table(
        box=box.SIMPLE_HEAVY,
        header_style="bold dim",
        show_edge=False,
        pad_edge=False,
    )
    table.add_column("ID",       width=8,  style="dim")
    table.add_column("Status",   width=10)
    table.add_column("Title",    min_width=24)
    table.add_column("Type",     width=10)
    table.add_column("Device",   width=8,  style="dim")
    table.add_column("Progress", width=12)
    table.add_column("Updated",  width=20, style="dim")

    tasks = sorted(agent.store.all(), key=lambda t: t.updated_at, reverse=True)[:limit]
    for t in tasks:
        color = STATUS_COLORS.get(t.status, "white")
        icon  = STATUS_ICONS.get(t.status, "?")
        bar   = _progress_bar(t.progress)
        table.add_row(
            t.task_id,
            f"[{color}]{icon} {t.status.value}[/{color}]",
            t.title or "(sem título)",
            t.task_type,
            t.device_id,
            bar,
            t.updated_at[:19].replace("T", " "),
        )
    return table


def _progress_bar(progress: float, width: int = 10) -> str:
    filled = int(progress * width)
    bar = "█" * filled + "░" * (width - filled)
    pct = int(progress * 100)
    return f"[cyan]{bar}[/cyan] {pct}%"


def render_resume_panel(tasks) -> Panel:
    if not tasks:
        return Panel("[dim]Nenhuma tarefa de outro dispositivo pendente.[/dim]",
                     title="Retomar de outro dispositivo", border_style="magenta")
    lines = []
    for t in tasks:
        lines.append(f"  [yellow]{t.task_id}[/yellow] {t.title} [{t.status.value}] device:{t.device_id}")
    return Panel("\n".join(lines), title="⚡ Retomar de outro dispositivo", border_style="magenta")


# ─────────────────────────────────────────────────────────────
# Interactive Dashboard
# ─────────────────────────────────────────────────────────────

def dashboard(agent: HormuzAgent, refresh_sec: float = 2.0):
    console.print(render_header(agent))
    resume = agent.resume_from_other_device()
    if resume:
        console.print(render_resume_panel(resume))
    with Live(console=console, refresh_per_second=1 / refresh_sec, screen=False) as live:
        try:
            while True:
                live.update(render_task_table(agent))
                time.sleep(refresh_sec)
        except KeyboardInterrupt:
            pass


# ─────────────────────────────────────────────────────────────
# Command Handlers
# ─────────────────────────────────────────────────────────────

def cmd_submit(agent: HormuzAgent):
    console.print("\n[bold cyan]Nova Tarefa[/bold cyan]")
    title = Prompt.ask("Título")
    task_type = Prompt.ask(
        "Tipo",
        choices=["organize", "rename", "tag", "ai", "generic"],
        default="generic"
    )
    priority_name = Prompt.ask(
        "Prioridade",
        choices=["low", "normal", "high", "urgent"],
        default="normal"
    )
    priority = TaskPriority[priority_name.upper()]
    background = Confirm.ask("Executar em background?", default=True)

    params = {}
    if task_type in ("organize", "rename", "tag"):
        path = Prompt.ask("Caminho do diretório", default=str(Path.cwd()))
        dry_run = Confirm.ask("Dry run (simular sem mover)?", default=False)
        params = {"path": path, "dry_run": dry_run}
    elif task_type == "ai":
        prompt = Prompt.ask("Prompt para o agente")
        params = {"prompt": prompt}

    task = HormuzTask(
        title=title,
        task_type=task_type,
        priority=priority,
        background=background,
        params=params,
    )
    agent.submit_task(task)
    console.print(f"\n[green]✓[/green] Tarefa [yellow]{task.task_id}[/yellow] adicionada à fila.")


def cmd_status(agent: HormuzAgent):
    console.print(render_header(agent))
    console.print(render_task_table(agent))


def cmd_sync(agent: HormuzAgent):
    with console.status("[cyan]Sincronizando...[/cyan]"):
        agent.sync_now()
    console.print("[green]✓[/green] Sincronização concluída.")


def cmd_cancel(agent: HormuzAgent):
    task_id = Prompt.ask("ID da tarefa para cancelar")
    if agent.store.cancel(task_id):
        console.print(f"[yellow]Tarefa {task_id} cancelada.[/yellow]")
    else:
        console.print(f"[red]Não foi possível cancelar {task_id}.[/red]")


def cmd_result(agent: HormuzAgent):
    task_id = Prompt.ask("ID da tarefa")
    task = agent.store.get(task_id)
    if not task:
        console.print(f"[red]Tarefa {task_id} não encontrada.[/red]")
        return
    console.print(Panel(
        f"[bold]Status:[/bold] {task.status.value}\n"
        f"[bold]Progresso:[/bold] {_progress_bar(task.progress)}\n"
        f"[bold]Resultado:[/bold]\n{task.result or '(sem resultado ainda)'}\n"
        f"[bold]Erro:[/bold] {task.error or 'nenhum'}",
        title=f"Tarefa {task_id}: {task.title}",
        border_style="green" if task.status == TaskStatus.DONE else "yellow"
    ))


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────

MENU = f"""
[bold cyan]{safe_icon("⚓", "[ANCHOR]")} AGENTE HORMUZ[/bold cyan]

  [yellow]1[/yellow] Dashboard (ao vivo)
  [yellow]2[/yellow] Status rápido
  [yellow]3[/yellow] Submeter tarefa
  [yellow]4[/yellow] Ver resultado
  [yellow]5[/yellow] Cancelar tarefa
  [yellow]6[/yellow] Sincronizar agora
  [yellow]q[/yellow] Sair
"""

def main():
    import logging
    logging.basicConfig(
        filename=str(Path.home() / ".hormuz" / "hormuz.log"),
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    sandbox = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    sync_path = Path(sys.argv[2]) if len(sys.argv) > 2 else None

    agent = HormuzAgent(sandbox_root=sandbox, sync_path=sync_path)
    agent.start()

    def _shutdown(sig, frame):
        console.print("\n[dim]Encerrando Agente Hormuz...[/dim]")
        agent.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    console.print(Panel(
        f"[bold cyan]{safe_icon('⚓', '[ANCHOR]')} Agente Hormuz iniciado[/bold cyan]\n"
        f"[dim]Sandbox: {sandbox} | Device: {_device_id()}[/dim]",
        border_style="cyan"
    ))

    # Show tasks from other devices on startup
    resume = agent.resume_from_other_device()
    if resume:
        console.print(render_resume_panel(resume))

    while True:
        console.print(MENU)
        choice = Prompt.ask("Opção", default="1")

        if choice == "1":
            dashboard(agent)
        elif choice == "2":
            cmd_status(agent)
        elif choice == "3":
            cmd_submit(agent)
        elif choice == "4":
            cmd_result(agent)
        elif choice == "5":
            cmd_cancel(agent)
        elif choice == "6":
            cmd_sync(agent)
        elif choice in ("q", "sair", "exit"):
            _shutdown(None, None)
        else:
            console.print("[red]Opção inválida.[/red]")


if __name__ == "__main__":
    main()
