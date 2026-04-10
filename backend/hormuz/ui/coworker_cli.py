"""
CNGSM — Coworker CLI
Interface interativa Estilo Claude Code / Cowork
"""

import os
import sys
import platform
import asyncio
import logging
# ──────────────────────────────────────────────────────────────────────────────
# Imports
# ──────────────────────────────────────────────────────────────────────────────
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.live import Live
from rich.table import Table
from rich.status import Status
from rich.prompt import Prompt

# Injeção de Path para monorepo
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "hormuz")))

try:
    from backend.hormuz.core.coworker import coworker_engine
except ImportError:
    try:
        from core.coworker import coworker_engine
    except ImportError:
        # Fallback para execução direta
        import sys
        sys.path.append(os.path.dirname(__file__))
        import coworker
        coworker_engine = coworker.coworker_engine

console = Console(force_terminal=True)



def safe_icon(emoji: str, ascii_alt: str) -> str:
    try:
        emoji.encode(sys.stdout.encoding or 'utf-8')
        return emoji
    except (UnicodeEncodeError, AttributeError):
        return ascii_alt

# ──────────────────────────────────────────────────────────────────────────────
# UI Header
# ──────────────────────────────────────────────────────────────────────────────

def print_header():
    header_text = (
        f"[bold cyan]{safe_icon('⚓', '---')} CNGSM COWORKER — OPERATIONAL MODE — Ω-9[/bold cyan]\n"
        f"[dim]Assistente de Programação & Automação Agentica[/dim]"
    )
    console.print(Panel(header_text, border_style="cyan", padding=(1, 2)))

# ──────────────────────────────────────────────────────────────────────────────
# Main Chat Loop
# ──────────────────────────────────────────────────────────────────────────────

async def main_loop():
    print_header()
    console.print(f"[dim]Digite seu pedido de código ou tarefa. (/exit para sair, /clear para limpar history)[/dim]\n")
    
    while True:
        try:
            user_input = Prompt.ask(f"[bold yellow]{safe_icon('COWORK>', 'COWORK>')}[/bold yellow]").strip()
            
            if not user_input:
                continue
                
            if user_input.lower() in ("/exit", "exit", "quit", "sair"):
                console.print("[dim]Desconectando Coworker...[/dim]")
                break
                
            if user_input.lower() == "/clear":
                coworker_engine.history = []
                console.clear()
                print_header()
                continue

            with Status(f"[cyan]Pensando...[/cyan]", spinner="dots", console=console) as status:
                # 1. Envio para Raciocínio
                result = await coworker_engine.chat(user_input)
                
                if "error" in result:
                    console.print(Panel(f"[red]Erro na Engine:[/red] {result['error']}", border_style="red"))
                    continue

                # 2. Mostra Resposta Inicial (Thought + Sugestão)
                console.print(Markdown(result["response"]))
                
                # 3. Processamento de Ferramentas (Recursive Observation)
                current_result = result
                iteration = 0
                max_iterations = 5 # Prevenção de loop infinito
                
                while current_result.get("tool_result") and iteration < max_iterations:
                    tool = current_result["tool_result"]
                    iteration += 1
                    
                    # Log da execução da ferramenta
                    console.print(Panel(
                        f"[bold blue]AÇÃO:[/bold blue] {tool['type']} ({tool.get('command') or tool.get('path')})",
                        border_style="blue",
                        title=f"{safe_icon('⚡', 'EXE')}"
                    ))
                    
                    # Exibe output da ferramenta (se não for gigante)
                    output_snippet = tool["output"]
                    if len(output_snippet) > 1000:
                        output_snippet = output_snippet[:1000] + "\n\n[... Omitido por tamanho ...]"
                    
                    console.print(Panel(output_snippet, title="Observação", border_style="dim"))
                    
                    # 4. Envia observação de volta para o LLM para continuar o raciocínio
                    status.update(f"[cyan]Analisando observação ({iteration})...[/cyan]")
                    observation_prompt = f"OBSERVAÇÃO DA FERRAMENTA:\n{tool['output']}\n\nAnalise o resultado acima e prossiga com a tarefa ou finalize se concluído."
                    current_result = await coworker_engine.chat(observation_prompt)
                    
                    # Mostra a nova resposta do LLM
                    console.print(Markdown(current_result["response"]))

            console.print("") # Linha em branco para clareza

        except KeyboardInterrupt:
            break
        except Exception as e:
            console.print(f"[bold red]CRITICAL ERROR:[/bold red] {e}")
            break

if __name__ == "__main__":
    asyncio.run(main_loop())
