# Change 007 — Spec: Contratos do Módulo LPS / SPL

> **Status:** draft · **Audience:** implementação + validação · **Data:** 2026-09-17

Este documento define os **contratos formais** do módulo LPS.
Implementação livre, mas estes 4 contratos são imutáveis até que
todos os blocos dependentes estejam escritos.

---

## Contrato 1 — DSL do Feature Model (JSON)

JSON que a GUI **exporta** para a engine de variabilidade. É o
"pacote" que viaja entre módulos: GUI → SAT Solver → Gerador Jinja2.

```json
{
  "spec_version": "1.0",
  "model_id": "lps-auth-system",
  "title": "Auth System LPS",
  "description": "Sistema de autenticação com 3 estratégias intercambiáveis.",
  "created_at": "2026-09-17T21:00:00+00:00",
  "nodes": [
    {
      "id": "node_root",
      "component_id": null,
      "variability": "ROOT",
      "label": "Auth System",
      "metadata": {}
    },
    {
      "id": "node_db",
      "component_id": "comp-sqlite-db",
      "variability": "MANDATORY",
      "label": "Database",
      "metadata": {"required_by": "Auth Service"}
    },
    {
      "id": "node_oauth",
      "component_id": "comp-oauth2",
      "variability": "OPTIONAL",
      "label": "OAuth2 Provider",
      "metadata": {}
    },
    {
      "id": "node_jwt",
      "component_id": "comp-jwt",
      "variability": "OPTIONAL",
      "label": "JWT Token",
      "metadata": {}
    },
    {
      "id": "node_basic",
      "component_id": "comp-basic-auth",
      "variability": "OPTIONAL",
      "label": "Basic Auth",
      "metadata": {}
    }
  ],
  "edges": [
    {"source": "node_jwt", "target": "node_db", "relation": "REQUIRES"},
    {"source": "node_oauth", "target": "node_db", "relation": "REQUIRES"},
    {"source": "node_jwt", "target": "node_basic", "relation": "EXCLUDES"},
    {"source": "node_oauth", "target": "node_basic", "relation": "EXCLUDES"}
  ],
  "groups": [
    {
      "id": "group_auth_strategy",
      "parent": "node_root",
      "kind": "ALTERNATIVE",
      "children": ["node_jwt", "node_oauth", "node_basic"]
    }
  ]
}
```

### Regras de validação do JSON

| Campo | Tipo | Obrigatório | Validação |
|---|---|---|---|
| `spec_version` | string | sim | deve ser `"1.0"` |
| `model_id` | string | sim | `^[a-z0-9_-]{1,64}$` |
| `nodes` | array | sim | length 1..200, ids únicos |
| `edges` | array | sim | source/target devem existir em nodes |
| `groups` | array | não | kind ∈ `{MANDATORY, OPTIONAL, ALTERNATIVE, OR}` |
| `variability` (em node) | enum | sim | `{ROOT, MANDATORY, OPTIONAL, ALTERNATIVE}` |
| `relation` (em edge) | enum | sim | `{REQUIRES, EXCLUDES}` |

### Cardinalidade

- `nodes`: 1..200
- `edges`: 0..500
- `groups`: 0..50
- Cada `node_id` único no escopo do model.
- Cada `group.children` length 1..20.
- Cada `group` deve ter exatamente **um** `parent` node.

### Erros

JSON inválido → `LpsSpecError` (subclasse de `ArchExplorerError`) com
`path=<caminho JSON Pointer>`, `reason=<motivo>`.

---

## Contrato 2 — Schema SQL (SQLite)

Mantemos as tabelas do catálogo (`entries`, `tags`, `entry_tags`,
`entries_fts`) intactas. As tabelas novas do módulo LPS convivem no
**mesmo arquivo** `catalogo.db` (decisão justificada no design.md).

```sql
-- Componentes reutilizáveis: cada componente pode aparecer em vários
-- feature models e ter código/SVG/snippet associado.
CREATE TABLE IF NOT EXISTS lps_components (
    id              TEXT PRIMARY KEY,                   -- UUID v4
    name            TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 100),
    category        TEXT NOT NULL CHECK(category IN (
                        'ui_ux', 'architecture', 'design_pattern',
                        'database', 'service', 'infra', 'test'
                    )),
    description     TEXT CHECK(description IS NULL OR length(description) <= 5000),
    code_snippet    TEXT CHECK(code_snippet IS NULL OR length(code_snippet) <= 100000),
    svg_icon_path   TEXT,                               -- path relativo a ~/Documents/ArchExplorer/assets/
    jinja_template  TEXT,                               -- template path em app/templates/lps/
    metadata_json   TEXT NOT NULL DEFAULT '{}',         -- {"language": "python", "tags": [...], "props": {...}}
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_lps_components_category ON lps_components(category);

-- Feature Models: um modelo agrupa nodes + edges + groups.
CREATE TABLE IF NOT EXISTS lps_feature_models (
    id                  TEXT PRIMARY KEY,
    title               TEXT NOT NULL CHECK(length(title) BETWEEN 1 AND 200),
    description         TEXT,
    tree_structure_json TEXT NOT NULL,                  -- JSON do Contrato 1
    validation_status   TEXT NOT NULL DEFAULT 'DRAFT' CHECK(validation_status IN ('DRAFT', 'VALID', 'INVALID')),
    last_solved_at      TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_lps_models_status ON lps_feature_models(validation_status);

-- Auditoria: cada geração de produto fica registrada pra debug e
-- pra detectar deriva entre feature model e código gerado.
CREATE TABLE IF NOT EXISTS lps_product_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    feature_model_id TEXT NOT NULL REFERENCES lps_feature_models(id) ON DELETE CASCADE,
    resolved_json   TEXT NOT NULL,                      -- saída do SAT solver
    output_dir      TEXT NOT NULL,
    file_count      INTEGER NOT NULL,
    duration_ms     INTEGER NOT NULL,
    status          TEXT NOT NULL CHECK(status IN ('SUCCESS', 'FAILED', 'PARTIAL')),
    error_message   TEXT,
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_lps_runs_model ON lps_product_runs(feature_model_id);
```

### Convenções

- **IDs** são UUID v4 em string lowercase (compatível com JSON).
- **Timestamps** ISO 8601 em UTC com `+00:00` (mesma convenção do catálogo).
- **Categorias** enum-fechado (UI mostra combo; service rejeita outras).
- **Metadata JSON** é livre (livre-schema), mas o backend valida tipos
  básicos (`language` deve ser string, `tags` deve ser array de string).

---

## Contrato 3 — Template Spec (Jinja2)

O serviço gerador recebe:

- **`model_id`**: ID do `lps_feature_models`.
- **`output_dir`**: diretório absoluto de destino (validado pelo sandbox).
- **`overrides`**: dict opcional de variáveis para injetar nos templates.

E produz:

- Árvore de arquivos no `output_dir`.
- Cada arquivo é resultado de renderizar `lps_components[jinja_template]`
  com contexto `{ "component": {...}, "globals": {...}, "overrides": {...} }`.
- Pastas são criadas automaticamente (`os.makedirs(..., exist_ok=True)`).
- Operação registrada em `lps_product_runs`.

### Convenção de templates

```
app/templates/lps/
├── base/
│   ├── python_package.zip.j2     # template raiz (gera estrutura de projeto Python)
│   ├── readme.md.j2
│   └── gitignore.j2
├── services/
│   ├── fastapi_app.py.j2
│   ├── flask_app.py.j2
│   └── cli_app.py.j2
├── infra/
│   ├── docker_compose.yml.j2
│   ├── dockerfile.python.j2
│   └── github_actions_ci.yml.j2
└── ui/
    ├── react_component.tsx.j2
    └── html_landing.html.j2
```

### Sandbox Jinja2

- Usar `jinja2.sandbox.SandboxedEnvironment` (sem `__import__`, sem
  file I/O via template).
- Whitelist de filtros e funções built-in (`upper`, `lower`, `join`,
  `tojson`).
- Globais permitidos: `component`, `globals`, `overrides` — apenas.

### Exemplo de template

```jinja2
{# app/templates/lps/services/fastapi_app.py.j2 #}
"""{{ component.name }} — auto-generated by ArchExplorer LPS."""
from fastapi import FastAPI
{% if component.metadata.requirements %}
# Requirements: {{ component.metadata.requirements | join(', ') }}
{% endif %}

app = FastAPI(title="{{ component.name }}")


@app.get("/health")
async def health():
    return {"status": "ok", "component": "{{ component.id }}"}
```

---

## Contrato 4 — LLM Adapter Spec

Multi-provider via LiteLLM. Config persistida em
`config/llm_config.json` (local) **ou** QSettings (registry).

```json
{
  "active_provider": "ollama_local",
  "providers": {
    "openai": {
      "model": "gpt-4o",
      "api_key_env": "OPENAI_API_KEY",
      "max_tokens": 4096,
      "temperature": 0.2
    },
    "anthropic": {
      "model": "claude-3-5-sonnet-20241022",
      "api_key_env": "ANTHROPIC_API_KEY",
      "max_tokens": 4096,
      "temperature": 0.2
    },
    "ollama_local": {
      "model": "qwen2.5-coder:3b",
      "base_url": "http://localhost:11434",
      "max_tokens": 4096,
      "temperature": 0.2
    }
  },
  "tools_enabled": true,
  "workspace_root": "~/Documents/ArchExplorer/workspaces/"
}
```

### Interface `LlmAdapter` (Protocol)

```python
class LlmAdapter(Protocol):
    def generate(
        self,
        prompt: str,
        *,
        system_prompt: str = "",
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: list[dict] | None = None,
    ) -> "LlmResponse": ...
    def generate_stream(
        self, prompt: str, *, system_prompt: str = "", tools: list[dict] | None = None,
    ) -> Iterator[str]: ...


@dataclass
class LlmResponse:
    content: str
    tool_calls: list["ToolCall"] = field(default_factory=list)
    usage: dict = field(default_factory=dict)


@dataclass
class ToolCall:
    name: str                              # "create_file" | "create_directory"
    arguments: dict                        # JSON parsed do payload da IA
    raw: dict                              # payload original (debug)
```

### Providers suportados (via LiteLLM)

- `openai` (gpt-4o, gpt-4-turbo, gpt-3.5-turbo)
- `anthropic` (claude-3-5-sonnet, claude-3-opus)
- `gemini` (gemini-1.5-pro, gemini-2.0-flash)
- `ollama_local` (qwen2.5-coder, llama3, mistral)
- `cohere` (command-r-plus)

### Erros

- `LlmAuthError`: API key ausente ou inválida.
- `LlmRateLimitError`: 429 do provider.
- `LlmTimeoutError`: timeout > configurado (default 300s).
- `LlmToolFormatError`: IA emitiu tool_call com schema inválido.

---

## Contrato 5 — Tool Spec (MCP-style)

Ferramentas que a IA pode invocar para manipular o filesystem. Cada
tool tem JSON Schema explícito; a IA emite uma **tool call** que
validamos contra o schema antes de executar.

### Tool 1: `create_file`

```json
{
  "type": "function",
  "function": {
    "name": "create_file",
    "description": "Cria um novo arquivo de código na estrutura do projeto.",
    "parameters": {
      "type": "object",
      "properties": {
        "file_path": {
          "type": "string",
          "pattern": "^[a-zA-Z0-9._/-]+$",
          "description": "Caminho relativo ao workspace_root (sem ..)"
        },
        "content": {"type": "string", "description": "Conteúdo completo do arquivo"}
      },
      "required": ["file_path", "content"],
      "additionalProperties": false
    }
  }
}
```

### Tool 2: `create_directory`

```json
{
  "type": "function",
  "function": {
    "name": "create_directory",
    "description": "Cria uma nova pasta no projeto (recursivo).",
    "parameters": {
      "type": "object",
      "properties": {
        "dir_path": {
          "type": "string",
          "pattern": "^[a-zA-Z0-9._/-]+$"
        }
      },
      "required": ["dir_path"],
      "additionalProperties": false
    }
  }
}
```

### Tool 3: `read_file`

```json
{
  "type": "function",
  "function": {
    "name": "read_file",
    "description": "Lê o conteúdo de um arquivo existente (read-only).",
    "parameters": {
      "type": "object",
      "properties": {
        "file_path": {"type": "string", "pattern": "^[a-zA-Z0-9._/-]+$"}
      },
      "required": ["file_path"],
      "additionalProperties": false
    }
  }
}
```

### Tool 4: `list_directory`

```json
{
  "type": "function",
  "function": {
    "name": "list_directory",
    "description": "Lista arquivos e pastas de um diretório (read-only).",
    "parameters": {
      "type": "object",
      "properties": {
        "dir_path": {"type": "string", "pattern": "^[a-zA-Z0-9._/-]+$"}
      },
      "required": ["dir_path"],
      "additionalProperties": false
    }
  }
}
```

### Sandbox

Todas as ferramentas passam pelo `FileSystemAgent` que valida:

1. `target_path = abspath(join(workspace_root, file_path))`
2. `target_path.startswith(workspace_root)` — path traversal protection.
3. `file_path` casa o regex do schema (sem `..`, sem `\\`, sem null bytes).
4. Tamanho do `content` ≤ 1 MB (rejeição silenciosa).
5. Encoding UTF-8 válido.

Violações → `PermissionError` propagado como `LlmToolError` com
`reason="path_outside_workspace" | "path_traversal" | "invalid_chars"`.

---

## Contrato 6 — UI Spec

### Toggle

- `Ctrl+3` ativa o modo LPS.
- `View > Painel esquerdo > LPS` no menu.
- O modo LPS **substitui** temporariamente o canvas central
  (`CodeEditorPanel`) por um `LpsCanvasView`.
- As colunas 1 e 3 (esquerda/direita) também mudam:
  - Coluna 1: `LpsPalettePanel` (lista de componentes arrastáveis).
  - Coluna 3: `LpsInspectorPanel` (propriedades do nó selecionado).

### Layout

```
+--------+------------------+------------------+
|PALETTE | CANVAS (GRAFO)   | INSPECTOR        |
|(Ctrl+3)| QGraphicsView    | (regras / props) |
|        | drag-drop OK     |                  |
| 📄 ... |   [A]──REQUIRES─▶[B]  | Nome: Auth      |
| 📄 ... |                  | Tipo: Mandatory  |
|        |                  | Regras: ...      |
+--------+------------------+------------------+
```

### Interações

| Ação | Comportamento |
|---|---|
| Drag de item da paleta para canvas | Cria `QGraphicsRectItem` na posição do drop |
| Click num nó | Seleciona; inspector à direita mostra props |
| Drag de um nó | Move o nó (snap to grid opcional) |
| Drag de um "anchor point" para outro nó | Cria aresta (linha) tipada |
| Click na aresta | Mostra dialog para escolher `REQUIRES` ou `EXCLUDES` |
| Botão **Validar** | Roda pysat; status badge fica verde/vermelho |
| Botão **Gerar Produto** | Abre dialog "Selecionar diretório de saída" → Jinja2 |

### Persistência

- Estado do canvas serializa em `tree_structure_json` (Contrato 1).
- Auto-save a cada 30s em `lps_feature_models.tree_structure_json`.

---

## Critérios de aceite

- [ ] AC-01: Ctrl+3 abre o modo LPS; Ctrl+1 volta pro Explorer.
- [ ] AC-02: Drag-and-drop cria nó visual na posição correta.
- [ ] AC-03: Conexão entre nós aceita REQUIRES / EXCLUDES.
- [ ] AC-04: SAT solver rejeita combinações inválidas em < 100ms para
  modelo de 20 features.
- [ ] AC-05: Gerar Produto cria a árvore de arquivos esperada; o zip
  abre e os arquivos batem com o template.
- [ ] AC-06: LLM com Tool Use cria arquivos no diretório correto;
  tentativa de path traversal falha com erro claro.
- [ ] AC-07: Provider OpenAI/Anthropic/Ollama trocam via config sem
  mudar código.
- [ ] AC-08: Feature model persiste em SQLite e é restaurado após
  fechar/reabrir o app.
- [ ] AC-09: Auto-save não bloqueia a UI (worker thread).
- [ ] AC-10: ≥ 30 testes novos, ≥ 85% cobertura nos módulos novos.
