import asyncio
import sys
import os
from pathlib import Path

# Adiciona o diretório backend ao sys.path para encontrar os módulos
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from contemplating_orchestrator import ContemplatingOrchestrator
from anthropic_stub import Anthropic

async def run_dry_run():
    print("=== S.O.H.-X Cognitive Dry-Run ===")
    
    # Instancia componentes
    client = Anthropic()
    orch = ContemplatingOrchestrator(config_path="contemplating_config.yaml")
    
    query = "Explique o que é o módulo Antigravity e como ele protege o sistema."
    print(f"QUERY: {query}\n")
    
    try:
        response = await orch.run(query, client)
        
        print("-" * 60)
        print("SÍNTESE FINAL:")
        print(response.synthesis)
        print("-" * 60)
        print(f"Agentes consultados: {response.agents_consulted}")
        print(f"Agentes vazios: {response.agents_empty}")
        print(f"Tempo total: {response.elapsed_total_ms}ms")
        
        if response.synthesis and "não encontrado" not in response.synthesis.lower():
            print("\n✅ DRY-RUN CONCLUÍDO COM SUCESSO")
            sys.exit(0)
        else:
            print("\n⚠️ DRY-RUN CONCLUÍDO (Informação não encontrada nos silos - Comportamento esperado se silos estiverem vazios)")
            sys.exit(0)
            
    except Exception as e:
        print(f"\n❌ ERRO NO DRY-RUN: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(run_dry_run())
