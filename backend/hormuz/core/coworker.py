"""
CNGSM — S.O.H.-X Coworker Engine
Lógica de assistência de programação baseada em terminal (estilo Claude Code/Aider)
"""

import os
import re
import json
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

# Fix para encodagem de console (Windows)
import sys
import platform
if platform.system() == "Windows":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from anthropic_stub import Anthropic as _Anthropic
from sandbox import sandbox

log = logging.getLogger("hormuz.coworker")

COWORKER_SYSTEM_PROMPT = """
Você é o CNGSM Coworker (S.O.H.-X Assistant).
Sua missão é atuar como um engenheiro de software de elite diretamente no terminal.

VOCÊ TEM PODERES REAIS:
Você pode ler arquivos, criar código, rodar testes e executar comandos shell na Sandbox Ω-9.

DIRETRIZES DE OPERAÇÃO:
1. Seja direto, técnico e profissional. Evite conversas triviais.
2. Sempre analise o contexto antes de sugerir mudanças.
3. Se precisar de dados externos, sugira usar o Modo Contemplating.
4. Você opera em uma sandbox protegida. Se um comando for bloqueado, explique o motivo e sugira uma alternativa segura.

COMO USAR FERRAMENTAS:
Você executa ações usando tags especiais. O sistema processará apenas UMA ação por vez e retornará o output.

<bash> comando </bash> -> Executa comandos shell (ex: python, pytest, ls).
<read_file> arquivo </read_file> -> Lê o conteúdo de um arquivo.
<write_file path="caminho"> conteúdo </write_file> -> Escreve/Sobrescreve um arquivo.
<research> query </research> -> Aciona o Contemplating Mode para busca profunda.

REGRAS DE OURO:
- SEMPRE mostre o raciocínio (Thought) antes de agir.
- Responda em Português, mas mantenha termos técnicos e código em Inglês onde apropriado.
""".strip()

class CoworkerEngine:
    def __init__(self, history_limit: int = 15):
        self.client = _Anthropic()
        self.history = []
        self.history_limit = history_limit

    async def chat(self, user_input: str) -> Dict[str, Any]:
        self.history.append({"role": "user", "content": user_input})
        
        # Limita histórico para economizar tokens
        if len(self.history) > self.history_limit:
            self.history = self.history[-self.history_limit:]

        try:
            # Chama o LLM via Stub
            response = self.client.messages.create(
                model=os.environ.get("ANTHROPIC_MODEL", "deepseek-chat"),
                max_tokens=4096,
                system=COWORKER_SYSTEM_PROMPT,
                messages=self.history
            )
            
            ai_content = response.content[0].text
            self.history.append({"role": "assistant", "content": ai_content})
            
            # Processa possíveis Tool Calls
            tool_result = await self._process_tools(ai_content)
            
            return {
                "response": ai_content,
                "tool_result": tool_result
            }
            
        except Exception as e:
            log.error(f"[Coworker] Chat error: {e}")
            return {"error": str(e)}

    async def _process_tools(self, content: str) -> Optional[Dict[str, Any]]:
        """Busca e executa a primeira ferramenta encontrada na resposta"""
        
        # 1. <bash> command </bash>
        bash_match = re.search(r"<bash>(.*?)</bash>", content, re.DOTALL)
        if bash_match:
            cmd = bash_match.group(1).strip().split()
            if not cmd: return None
            output = sandbox.run_command(cmd)
            return {"type": "bash", "command": " ".join(cmd), "output": output}

        # 2. <read_file> path </read_file>
        read_match = re.search(r"<read_file>(.*?)</read_file>", content, re.DOTALL)
        if read_match:
            path = read_match.group(1).strip()
            try:
                data = sandbox.read_file(path)
                return {"type": "read", "path": path, "output": data}
            except Exception as e:
                return {"type": "read", "path": path, "output": f"ERROR: {e}"}

        # 3. <write_file path="..."> content </write_file>
        write_match = re.search(r'<write_file path="(.*?)">(.*?)</write_file>', content, re.DOTALL)
        if write_match:
            path = write_match.group(1).strip()
            text = write_match.group(2).strip()
            try:
                sandbox.write_file(path, text)
                return {"type": "write", "path": path, "output": "SUCCESS: Arquivo gravado."}
            except Exception as e:
                return {"type": "write", "path": path, "output": f"ERROR: {e}"}

        return None

# Singleton da Engine
coworker_engine = CoworkerEngine()
