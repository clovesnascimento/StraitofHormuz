# ⚓ Manual de Operação: S.O.H.-X (Kernel Ω-9)

Este manual descreve o setup, configuração e operação do ecossistema **S.O.H.-X**, integrando o **Agente Hormuz v1.0**, o orquestrador **Contemplating Mode** e a arquitetura de segurança **CNGSM v3.3**.

---

## 1. Configuração Inicial (.env)

O sistema centraliza todas as chaves e modelos no arquivo `.env` na raiz do projeto.

1. Localize o arquivo `d:\Strait of Hormuz\Strait of Hormuz\.env`.
2. Configure sua chave API (Anthropic ou DeepSeek):
   ```env
   # Se usar DeepSeek:
   ANTHROPIC_API_KEY="YOUR_KEY_HERE"
   ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic
   ANTHROPIC_MODEL=deepseek-chat

   # Se usar Anthropic nativo:
   ANTHROPIC_API_KEY=sk-ant-...
   ANTHROPIC_BASE_URL=https://api.anthropic.com
   ANTHROPIC_MODEL=claude-sonnet-4-20250514
   ```

> **NOTA CRÍTICA:** O sistema utiliza um **Anthropic Stub** customizado que permite o uso de DeepSeek com o SDK da Anthropic, contornando incompatibilidades do Pydantic no Windows/Python 3.14.

---

## 2. Instalação e Ativação do Daemon (Agente Hormuz)

O Agente Hormuz roda em background permanentemente para processar tarefas ociosas e sincronização cross-device.

### Instalação (Windows Task Scheduler)
Abra um terminal (PowerShell) e execute:
```powershell
python backend\hormuz\daemon\daemon.py install "D:\Strait of Hormuz"
```

### Iniciar o Agente Agora
Se não quiser reiniciar o logoff/logon:
```powershell
schtasks /Run /TN "HormuzAgent"
```

### Verificar Status
```powershell
python backend\hormuz\daemon\daemon.py status
```

---

## 3. Interface de Monitoramento (Hormuz CLI)

Para gerenciar tarefas, ver o dashboard ao vivo e submeter novos comandos de arquivo.

```powershell
python backend\hormuz\ui\cli.py "D:\Strait of Hormuz"
```

**Comandos do Menu:**
1. **Dashboard:** Visão geral em tempo real de todas as tarefas.
2. **Status:** Relatório rápido de saúde do agente.
3. **Submeter Tarefa:**
    - `organize`: Classifica arquivos por tipo (docs, code, media).
    - `rename`: IA sugere nomes melhores baseado no conteúdo (requer API).
    - `tag`: Gera `tags.json` semântico para busca.
    - `ai`: Prompt direto para o LLM.

---

## 4. Orquestrador "Contemplating Mode"

O modo de pesquisa multi-agente que consulta silos de dados, local FS e Google Drive de forma segura.

### Inicialização
```powershell
python backend\contemplating_orchestrator.py
```

---

## 5. Protocolo de Segurança CNGSM (Zero Trust)

O sistema opera sob o protocolo **Ω-9**, que bloqueia injeções de prompt e escalonamento de privilégios.

### Module 9 (Sanitização de Output)
Qualquer dado retornado por um sub-agente ou tarefa de IA é escaneado em tempo real.
- Bloqueia automaticamente padrões de instrução maliciosos.

### Module 10 (Canal de Aprovação)
Operações de alto risco (como `organize` ou `rename` fora da sandbox padrão) geram um **Interrupt**.
1. O sistema para e pede autorização.
2. Você deve aprovar via API enviando o token correspondente.

---

## 6. Sincronização Cross-Device

Se você usar o S.O.H.-X em dois computadores:
1. Através do `SYNC_FILE` configurado (padrão em `HORMUZ_HOME`), o sistema sincroniza o estado.
2. Tarefas pausadas em um dispositivo podem ser retomadas em outro.

## 7. Estrutura de Pastas e Dados

Para que os agentes consigam pesquisar seus documentos reais, utilize a seguinte estrutura de diretórios:

### 📥 Workspace (`workspace/`)
Pasta principal para documentos de trabalho, relatórios e arquivos temporários.
- **Caminho:** `d:\Strait of Hormuz\Strait of Hormuz\workspace`
- **Agente:** `ag-workspace`

### 📓 Obsidian Vault (`workspace/vault/`)
Destino para suas notas estruturadas, memórias persistentes e bases de conhecimento em Markdown.
- **Caminho:** `d:\Strait of Hormuz\Strait of Hormuz\workspace\vault`
- **Agente:** `ag-obsidian`

### 🗄️ Pesquisa e Silos (`backend/silos/`)
Local onde o sistema armazena os bancos de dados vetoriais (ChromaDB) para pesquisa semântica rápida do Agente de Segurança e Python.
- **Caminho:** `d:\Strait of Hormuz\Strait of Hormuz\backend\silos`

---

## 8. Modo Coworker (Assistente de Programação IA)

Este é o modo "Power User" para desenvolvedores, permitindo um par de programação IA diretamente no terminal (Estilo Claude Code).

### Como Acessar
Inicie o `START_SOH.bat` e selecione a **Opção [2] COWORKER Modo**.

### Principais Capacidades:
- **Codificação Proativa:** Peça para criar novas funcionalidades, classes ou scripts completos.
- **Análise de Erros:** Cole logs de erro e o sistema lerá os arquivos necessários para sugerir correções.
- **Execução em Sandbox:** O Coworker pode rodar comandos `python`, `pytest` ou `npm` dentro da sandbox e analisar o retorno.
- **Raciocínio Multi-Etapa:** O agente pensa (Thought), executa uma ação e ajusta sua estratégia baseada na observação do resultado.

---
*Manual gerado por Antigravity | CNGSM Integrity: PRESERVED*

