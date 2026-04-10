# CNGSM — Contemplating Mode
## Multi-Agent Parallel Search Architecture
## Versão: 1.0 — Design Document

---

## 1. VISÃO GERAL

O **Contemplating Mode** é o modo de raciocínio profundo do CNGSM.
Ao receber uma query, o orquestrador não responde diretamente — ele spawna
múltiplos agentes de pesquisa em paralelo, cada um com acesso exclusivo à
sua fonte de dados, coleta os resultados e executa síntese profunda antes
de responder.

```
QUERY DO OPERADOR
      │
      ▼
┌─────────────────────┐
│  ContemplatingOrch  │  ← raciocínio profundo: decompõe a query em
│  estrator           │    sub-queries por domínio de agente
└──────┬──────────────┘
       │  spawn paralelo
  ┌────┴────────────────────────────────┐
  │            │            │           │
  ▼            ▼            ▼           ▼
Agent A      Agent B      Agent C    Agent N
GDrive pub  GDrive priv  Local Silo  Local FS
  │            │            │           │
  ▼            ▼            ▼           ▼
ResearchResult ResearchResult ...      ...
  │            │            │           │
  └────────────┴────────────┴───────────┘
                     │
                     ▼
          ┌──────────────────┐
          │  SynthesisEngine │  ← fusão + raciocínio + resposta final
          └──────────────────┘
                     │
                     ▼
             RESPOSTA FINAL
```

---

## 2. COMPONENTES PRINCIPAIS

### 2.1 AgentRegistry

Mapa central de agentes disponíveis. Cada agente tem:

```python
{
  "agent_id": str,              # identificador único
  "name": str,                  # nome legível
  "source_type": str,           # "gdrive_public" | "gdrive_private" | "silo" | "local"
  "source_ref": str,            # URL pública | folder_id | silo_name | path local
  "domain": str,                # domínio de especialização do agente
  "description": str,           # o que este agente sabe / cobre
  "permissions": str,           # "read" (default) | "read_write"
  "active": bool                # se está disponível para spawn
}
```

**Exemplo de registry:**
```python
AGENT_REGISTRY = [
  {
    "agent_id": "ag-security",
    "name": "Security Research Agent",
    "source_type": "silo",
    "source_ref": "silo_core",
    "domain": "security, threat modeling, MITRE ATLAS, defense layers",
    "description": "Acesso ao silo core do CNGSM com documentação de segurança",
    "permissions": "read",
    "active": True
  },
  {
    "agent_id": "ag-gdrive-pub",
    "name": "Public Research Agent",
    "source_type": "gdrive_public",
    "source_ref": "https://drive.google.com/drive/folders/FOLDER_ID",
    "domain": "documentos públicos compartilhados pelo operador",
    "description": "Acesso a pasta pública do Google Drive",
    "permissions": "read",
    "active": True
  },
  {
    "agent_id": "ag-gdrive-priv",
    "name": "Private Drive Agent",
    "source_type": "gdrive_private",
    "source_ref": "FOLDER_ID_PRIVADO",
    "domain": "documentos privados do operador",
    "description": "Acesso autenticado a pasta privada do Google Drive",
    "permissions": "read",
    "active": True
  },
  {
    "agent_id": "ag-local-powershell",
    "name": "PowerShell Silo Agent",
    "source_type": "silo",
    "source_ref": "silo_powershell",
    "domain": "scripts PowerShell, automação Windows",
    "description": "Acesso ao silo de scripts e conhecimento PowerShell",
    "permissions": "read",
    "active": True
  }
]
```

---

### 2.2 ContemplatingOrchestrator

**Responsabilidades:**
1. Receber a query do operador
2. **Contemplar** — raciocínio profundo sobre QUAL sub-query enviar para QUAL agente
3. Spawnar agentes em paralelo via `asyncio.gather`
4. Coletar `ResearchResult` de cada agente
5. Executar síntese profunda com o LLM
6. Retornar resposta final estruturada

**Fluxo interno:**

```
query → _decompose_query() → [(agent_id, sub_query), ...]
      → _spawn_parallel(agents, sub_queries)
      → _collect_results() → [ResearchResult, ...]
      → _synthesize(results, original_query)
      → FinalResponse
```

---

### 2.3 ResearchAgent (por instância)

Cada instância de `ResearchAgent`:
- Conhece apenas seu `source_ref`
- Executa a sub-query no seu domínio
- Retorna `ResearchResult` estruturado
- Aplica Module 9 (sanitização de output) antes de retornar

**Adaptadores de fonte:**

```
GDrivePublicAdapter   → requests + parsing de HTML/Drive API pública
GDrivePrivateAdapter  → Google Drive API autenticada (OAuth2 / service account)
SiloAdapter           → RAG query no silo CNGSM local
LocalFSAdapter        → busca em file system local via WorkspaceSandbox
```

---

### 2.4 SynthesisEngine

Recebe todos os `ResearchResult` e executa:
1. **Deduplicação** — remove informação idêntica de fontes diferentes
2. **Contradição** — identifica e sinaliza quando fontes discordam
3. **Gap Analysis** — identifica o que nenhum agente cobriu
4. **Síntese LLM** — prompt de síntese profunda com todos os resultados
5. **Atribuição** — cada trecho da resposta final indica de qual agente veio

---

## 3. ESTRUTURA DE DADOS

```python
@dataclass
class SubQuery:
    agent_id: str
    query: str
    rationale: str      # por que esta sub-query para este agente

@dataclass
class ResearchResult:
    agent_id: str
    agent_name: str
    source_type: str
    sub_query: str
    findings: list[str]       # lista de achados relevantes
    snippets: list[dict]      # {"text": str, "source": str, "relevance": float}
    confidence: float         # 0.0 - 1.0
    status: str               # "success" | "partial" | "empty" | "error"
    error: str | None
    elapsed_ms: int

@dataclass
class FinalResponse:
    original_query: str
    agents_consulted: list[str]
    agents_empty: list[str]
    synthesis: str
    sources: list[dict]       # atribuições por trecho
    gaps: list[str]           # o que não foi encontrado em nenhum agente
    contradictions: list[dict] # quando agentes discordam
    contemplation_trace: str  # raciocínio do orquestrador (opcional, modo debug)
    elapsed_total_ms: int
```

---

## 4. MODO CONTEMPLATING — FLUXO DETALHADO

### Fase 1 — Contemplação (antes do spawn)

O orquestrador usa um LLM call separado para raciocinar sobre a query:

```
PROMPT DE CONTEMPLAÇÃO:
  "Query: {query}
   Agentes disponíveis: {registry_summary}

   Raciocine profundamente:
   1. Quais dimensões da query cada agente pode cobrir?
   2. Que sub-query específica maximiza o yield de cada agente?
   3. Quais agentes são irrelevantes para esta query?
   4. Existe risco de resultados contraditórios? Como pré-sinalizar?

   Retorne JSON: [{agent_id, sub_query, rationale, priority}]"
```

### Fase 2 — Spawn Paralelo

```python
async def _spawn_parallel(sub_queries: list[SubQuery]) -> list[ResearchResult]:
    tasks = [
        agent_pool[sq.agent_id].search(sq.query)
        for sq in sub_queries
        if agent_pool[sq.agent_id].active
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return [r for r in results if isinstance(r, ResearchResult)]
```

### Fase 3 — Síntese Profunda

O SynthesisEngine monta um prompt de síntese com todos os resultados:

```
PROMPT DE SÍNTESE:
  "Query original: {query}

   Resultados por agente:
   [AG-SECURITY]: {findings}
   [AG-GDRIVE-PUB]: {findings}
   ...

   Execute síntese profunda:
   - Integre os achados em resposta coesa
   - Sinalize contradições explicitamente
   - Indique gaps (o que nenhum agente cobriu)
   - Atribua cada afirmação à sua fonte
   - Não invente informação ausente nos achados"
```

---

## 5. FONTES DE DADOS — ADAPTADORES

### GDrivePublicAdapter
```
Método: requests.get(url) + BeautifulSoup parsing
Autenticação: nenhuma (pasta pública)
Limitações: apenas arquivos com visualização pública habilitada
Fallback: tentar Drive API com chave pública se parsing falhar
```

### GDrivePrivateAdapter
```
Método: Google Drive API v3 (google-api-python-client)
Autenticação: OAuth2 user credentials ou Service Account JSON
Escopos: https://www.googleapis.com/auth/drive.readonly
Listagem: files().list(q="'{folder_id}' in parents")
Download: files().export() para Docs/Sheets, get_media() para binários
```

### SiloAdapter
```
Método: RAG query no silo CNGSM local (ChromaDB / FAISS)
Input: texto da sub-query
Output: top-K chunks relevantes com score de similaridade
Threshold: descartar chunks com score < 0.65
```

### LocalFSAdapter
```
Método: busca recursiva via WorkspaceSandbox (read permission)
Suporte: .md, .txt, .py, .ts, .json, .pdf (via extração de texto)
Busca: keyword + embeddings locais se disponível
Sandbox: respeita limites do WorkspaceSandbox — sem acesso fora do escopo
```

---

## 6. SEGURANÇA — INTEGRAÇÃO COM ANTIGRAVITY v3.2.1

### Aplicação do Module 9 em ResearchAgent

Todo `ResearchResult` passa pelo pipeline antes de retornar ao orquestrador:

```
1. Schema validation: findings correspondem ao tipo esperado?
2. Instruction pattern scan: findings contêm padrões de instrução comportamental?
3. Size truncation: findings > limite → truncar
4. Wrapping:
   [RESEARCH_RESULT | agent_id: {id} | source: {type} | sanitized: YES]
   {findings sanitizados}
   [/RESEARCH_RESULT]
5. Falha em qualquer etapa → status: "error", findings: [], não propaga payload
```

### Aplicação do Module 7 (SSRF Guard) em GDriveAdapters

Qualquer URL processada pelos adaptadores passa pelo SSRF Guard:
- Apenas `https://` permitido
- Blocklist RFC 1918 + IMDS
- Allowlist de domínios: apenas `*.google.com`, `*.googleapis.com` para GDrive
- DNS rebinding check pós-resolução

### Isolamento entre Agentes

Cada `ResearchAgent` opera em sub-contexto isolado:
- Não tem acesso ao contexto de outro agente
- Não tem acesso ao system prompt do orquestrador
- Retorna apenas `ResearchResult` — sem acesso de escrita ao contexto principal

---

## 7. ARQUIVO DE CONFIGURAÇÃO

`contemplating_config.yaml`:
```yaml
contemplating_mode:
  enabled: true
  max_parallel_agents: 8
  timeout_per_agent_ms: 30000
  synthesis_model: "claude-sonnet-4-20250514"
  contemplation_model: "claude-sonnet-4-20250514"
  result_size_limit_tokens: 4096
  min_confidence_threshold: 0.4
  debug_trace: false          # se true: inclui contemplation_trace no FinalResponse

agent_registry:
  path: "config/agent_registry.json"
  hot_reload: true            # recarrega sem restart

gdrive:
  credentials_path: "config/gdrive_credentials.json"
  token_path: "config/gdrive_token.json"
  service_account_path: "config/service_account.json"

ssrf_guard:
  enabled: true
  allowed_domains:
    - "drive.google.com"
    - "googleapis.com"
    - "docs.google.com"

module9:
  enabled: true
  size_limit_tokens: 4096
  fail_closed: true
```

---

## 8. DECISÕES ARQUITETURAIS PENDENTES ANTES DA IMPLEMENTAÇÃO

| # | Decisão | Opções | Recomendação |
|---|---|---|---|
| 1 | Backend de RAG local para SiloAdapter | ChromaDB / FAISS / Qdrant | ChromaDB (já usado no CNGSM) |
| 2 | Autenticação GDrive privado | OAuth2 user / Service Account | Service Account para automação |
| 3 | Modelo de contemplação vs síntese | mesmo modelo / modelos diferentes | mesmo modelo, prompts distintos |
| 4 | Timeout behavior | fail closed / partial result | partial result com status="timeout" |
| 5 | Persistência de ResearchResults | ephemeral / cache / Obsidian | cache por sessão + write opcional ao Vault |

---
*CNGSM Contemplating Mode — Architecture Document v1.0*
*Dependências: Module 7 (SSRF Guard) + Module 9 (Sub-Agent Sanitization) do Antigravity v3.2.1*
