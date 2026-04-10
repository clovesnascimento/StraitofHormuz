"""
CNGSM — S.O.H.-X Cortex (Local Engine)
Módulo de execução local para modelos GGUF via llama.cpp.
"""

import argparse
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
log = logging.getLogger("cngsm.cortex")

def main():
    parser = argparse.ArgumentParser(description="CNGSM S.O.H.-X Cortex - Local Inference Engine")
    parser.add_argument("--model", type=str, help="Caminho para o arquivo .gguf do modelo")
    parser.add_argument("--threads", type=int, default=4, help="Número de threads para processamento")
    parser.add_argument("--n_gpu_layers", type=int, default=0, help="Camadas a serem enviadas para a GPU (se disponível)")
    parser.add_argument("--interactive", action="store_true", help="Iniciar em modo interativo")
    
    args = parser.parse_args()

    print("--- S.O.H.-X CORTEX (KERNEL ALPHA-10) ---")
    log.info("Booting Cortex Engine...")
    
    if not args.model:
        log.warning("Nenhum modelo especificado. O Cortex operará em modo 'Mock' para demonstração.")
        print("\n[CORTEX] Sistema aguardando carregamento de modelo GGUF...")
    else:
        log.info(f"Carregando modelo: {args.model}")
        print(f"\n[CORTEX] Modelo {args.model} engajado com {args.threads} threads.")

    if args.interactive:
        print("\nModo interativo ativado. Digite 'quit' para sair.")
        while True:
            user_input = input(">>> ")
            if user_input.lower() in ["quit", "exit"]:
                break
            print(f"Cortex Result: [O modo de inferência local requer a biblioteca llama-cpp-python instalada].")

    print("\nCortex Engine encerrada.")

if __name__ == "__main__":
    main()
