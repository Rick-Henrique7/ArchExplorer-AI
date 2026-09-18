# Change 007 — Design: Arquitetura Interna do Módulo LPS

> **Status:** draft · **Audience:** implementação + revisão de código

Este documento define **como** implementar os contratos do `spec.md`.
Decisões locais (nomes de classe, layout de arquivos, threading)
ficam aqui; tudo que afeta contrato externo fica no `spec.md`.

---

## 1. Decisões locais

### 1.1. Mesmo arquivo SQLite (`catalogo.db`)?

**Decisão:** mesmo arquivo.

**Por quê:** o catálogo já hospeda "componentes" (Change 006) com
título, descrição, código, tags. Um `lps_components` é um super-set
(categoria, svg_icon_path, jinja_template, metadata_json). Adicionar
tabelas novas no mesmo arquivo simplifica backup, migração e
distribuição (1 arquivo em vez de 2).

**Mitigação:** o `CatalogoService` continua expondo apenas os métodos
do Change 006. O acesso às tabelas `lps_*` vive num
`LpsService` separado que abre **a mesma conexão**.

### 1.2. Estrutura de pastas

```
app/
├── services/
│   ├── catalog_service.py          # Change 006 (intocado)
│   ├── lps_service.py              # NOVO — CRUD de components/models/runs
│   ├── variability_solver.py       # NOVO — wrapper pysat
│   ├── template_engine.py          # NOVO — wrapper Jinja2 sandboxed
│   ├── llm_adapter.py              # NOVO — wrapper LiteLLM
│   ├── filesystem_agent.py         # NOVO — sandbox + Tool Use exec
│   └── ...
├── ui/
│   ├── main_window.py              # modificado — adiciona Ctrl+3
│   ├── left_panel.py               # modificado — adiciona modo LPS
│   ├── lps_palette_panel.py        # NOVO
│   ├── lps_canvas_view.py          # NOVO — QGraphicsView
│   ├── lps_canvas_scene.py         # NOVO — QGraphicsScene
│   ├── lps_node_item.py            # NOVO — QGraphicsItem customizado
│   ├── lps_edge_item.py            # NOVO — QGraphicsItem aresta
│   ├── lps_inspector_panel.py      # NOVO
│   └── ...
├── workers/
│   ├── lps_solver_worker.py        # NOVO — QRunnable para SAT
│   ├── lps_generator_worker.py     # NOVO — QRunnable para Jinja2
│   └── lps_llm_worker.py           # NOVO — QRunnable para LLM
├── templates/
│   └── lps/
│       ├── base/...
│       ├── services/...
│       ├── infra/...
│       └── ui/...
└── ...
```

### 1.3. Threading

3 workers novos, todos seguindo o pattern `_WorkerSignals` (já
adotado em Change 005):

| Worker | O que faz | Signals |
|---|---|---|
| `LpsSolverWorker` | Roda pysat num feature model | `finished(status, resolved_json)` |
| `LpsGeneratorWorker` | Renderiza templates Jinja2 → arquivos | `progress(done, total)`, `finished(output_dir, file_count)` |
| `LpsLlmWorker` | Chama LiteLLM + executa tool calls | `chunk(delta_text)`, `tool_call(name, args)`, `finished(response)` |

UI nunca bloqueia; `QThreadPool.globalInstance().start(worker)`.

### 1.4. Validação de JSON (DSL)

Usar **`pydantic` v2** (já no requirements-dev via FastAPI? — se não,
adicionar) para validar o JSON do Contrato 1. Vantagens:

- Schema declarativo em Python (1:1 com o JSON Schema).
- Erros estruturados com `path` (JSON Pointer).
- `model_dump_json()` para re-export.

### 1.5. SAT Solver (pysat)

```python
from pysat.solvers import Solver
from pysat.formula import CNF
from pysat.card import CardEnc, EncType


class VariabilitySolver:
    """Wrapper sobre pysat para validar feature models."""

    def __init__(self):
        self._next_var = 1
        self._node_to_var: dict[str, int] = {}

    def encode(self, model: dict) -> "EncodedModel":
        """Converte o JSON do Contrato 1 em cláusulas CNF."""
        ...

    def is_satisfiable(
        self, encoded: "EncodedModel", selection: set[str]
    ) -> tuple[bool, "list[str] | None"]:
        """Testa se ``selection`` (ids de nodes selecionados) é válida.
        Retorna (is_valid, conflicting_nodes)."""
        ...
```

#### Regras de tradução (resumo)

| Conceito | Cláusula CNF |
|---|---|
| `MANDATORY` | `parent → child` ≡ `¬parent ∨ child` |
| `OPTIONAL` | nenhuma cláusula (pode ou não estar) |
| `REQUIRES(a, b)` | `a → b` ≡ `¬a ∨ b` |
| `EXCLUDES(a, b)` | `¬(a ∧ b)` ≡ `¬a ∨ ¬b` |
| Group `ALTERNATIVE(children)` | exatamente 1: `(at-least-1) ∧ (pairwise ¬(ci ∧ cj))` |
| Group `OR(children)` | pelo menos 1: `(at-least-1)` |
| Root selecionado | asserção fixa no solver |

#### Cardinalidade

Para `ALTERNATIVE` com N filhos, adicionamos cláusulas de par (`¬ci ∨
¬cj` para todo par i,j). Para N=10 isso é 45 cláusulas — pysat g3
aguenta bem.

### 1.6. Template Engine (Jinja2 sandboxed)

```python
from jinja2.sandbox import SandboxedEnvironment
from jinja2 import FileSystemLoader


class TemplateEngine:
    def __init__(self, template_root: Path):
        self._env = SandboxedEnvironment(
            loader=FileSystemLoader(str(template_root)),
            autoescape=False,            # templates são código, não HTML
            trim_blocks=True,
            lstrip_blocks=True,
        )
        # Whitelist explícita (nega qualquer global custom).
        self._env.globals["tojson"] = lambda v: __import__("json").dumps(v)

    def render(
        self, template_name: str, context: dict, output_path: Path
    ) -> None:
        template = self._env.get_template(template_name)
        content = template.render(**context)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")
```

### 1.7. LLM Adapter (LiteLLM)

```python
import json
from typing import Iterator, Protocol
import litellm


class LlmAdapter(Protocol):
    def generate(
        self, prompt: str, *, system_prompt: str = "",
        temperature: float | None = None, max_tokens: int | None = None,
        tools: list[dict] | None = None,
    ) -> "LlmResponse": ...
    def generate_stream(
        self, prompt: str, *, system_prompt: str = "", tools: list[dict] | None = None,
    ) -> Iterator[str]: ...


class LiteLlmAdapter:
    """Implementação única que cobre todos os providers via litellm."""

    def __init__(self, config: dict):
        self._config = config

    def _resolve_model(self) -> tuple[str, dict]:
        provider = self._config["active_provider"]
        pcfg = self._config["providers"][provider]
        model_name = pcfg["model"]
        # Translate short alias to LiteLLM format
        prefix = {
            "openai": "openai",
            "anthropic": "anthropic",
            "ollama_local": "ollama",
            "gemini": "gemini",
            "cohere": "cohere",
        }[provider]
        return f"{prefix}/{model_name}", pcfg

    def generate(self, prompt, *, system_prompt="", temperature=None,
                 max_tokens=None, tools=None) -> "LlmResponse":
        model, pcfg = self._resolve_model()
        kwargs = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature if temperature is not None else pcfg.get("temperature", 0.2),
            "max_tokens": max_tokens if max_tokens is not None else pcfg.get("max_tokens", 4096),
        }
        if tools:
            kwargs["tools"] = tools
        resp = litellm.completion(**kwargs)
        msg = resp.choices[0].message
        return LlmResponse(
            content=msg.content or "",
            tool_calls=[
                ToolCall(name=tc.function.name, arguments=json.loads(tc.function.arguments), raw=tc.model_dump())
                for tc in (msg.tool_calls or [])
            ],
            usage=resp.usage.model_dump() if resp.usage else {},
        )
```

### 1.8. FileSystemAgent (sandbox)

```python
import os
import re
from pathlib import Path


_PATH_RE = re.compile(r"^[a-zA-Z0-9._/\-]+$")
_MAX_FILE_SIZE = 1_048_576  # 1 MB


class FileSystemAgent:
    def __init__(self, workspace_root: Path):
        self._root = workspace_root.resolve()

    def _safe_path(self, relative_path: str) -> Path:
        if not _PATH_RE.match(relative_path):
            raise LlmToolError("invalid_chars", path=relative_path)
        target = (self._root / relative_path).resolve()
        if not str(target).startswith(str(self._root)):
            raise LlmToolError("path_traversal", path=relative_path)
        return target

    def create_file(self, file_path: str, content: str) -> str:
        target = self._safe_path(file_path)
        if len(content.encode("utf-8")) > _MAX_FILE_SIZE:
            raise LlmToolError("file_too_large", path=file_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Created {file_path}"

    def create_directory(self, dir_path: str) -> str:
        target = self._safe_path(dir_path)
        target.mkdir(parents=True, exist_ok=True)
        return f"Created directory {dir_path}"

    def read_file(self, file_path: str) -> str:
        target = self._safe_path(file_path)
        if not target.is_file():
            raise LlmToolError("file_not_found", path=file_path)
        return target.read_text(encoding="utf-8")

    def list_directory(self, dir_path: str = ".") -> list[str]:
        target = self._safe_path(dir_path)
        if not target.is_dir():
            raise LlmToolError("not_a_directory", path=dir_path)
        return sorted(p.name + ("/" if p.is_dir() else "") for p in target.iterdir())
```

### 1.9. Tool Use loop

```python
def run_agent_loop(
    adapter: LlmAdapter,
    agent: FileSystemAgent,
    user_prompt: str,
    system_prompt: str,
    tools: list[dict],
    max_iterations: int = 10,
) -> str:
    """Loop básico de Tool Use: envia prompt, recebe tool_call, executa,
    envia resultado de volta, repete até resposta final ou max_iter."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    for _ in range(max_iterations):
        resp = adapter.generate("", messages=messages, tools=tools)
        if not resp.tool_calls:
            return resp.content
        for tc in resp.tool_calls:
            try:
                method = getattr(agent, tc.name)
                result = method(**tc.arguments)
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
            except LlmToolError as e:
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": f"ERROR: {e.reason}"})
    return "(loop limit reached)"
```

A UI mostra cada tool_call no chat como uma "ação" (cor diferenciada).

### 1.10. GUI — QGraphicsView

```
LpsCanvasView(QGraphicsView)
├── setScene(LpsCanvasScene)
├── setAcceptDrops(True)
├── dragEnterEvent / dropEvent     # aceita MIME "application/x-lps-component"
└── mousePressEvent / mouseMoveEvent  # detecção de "arrastar de anchor pra criar edge"

LpsCanvasScene(QGraphicsScene)
├── nodes: dict[str, LpsNodeItem]   # por node_id
├── edges: dict[str, LpsEdgeItem]
├── signal: node_selected(node_id)
├── signal: node_moved(node_id, x, y)
├── signal: edge_created(edge_id, source, target, relation)
├── signal: edge_relation_changed(edge_id, relation)
└── to_json() / from_json(model_dict)

LpsNodeItem(QGraphicsRectItem)
├── _node_id
├── _variability
├── _component_id
├── anchors: {top, bottom, left, right}  # 4 QGraphicsEllipseItem filhos
└── mousePressEvent em anchor  → inicia criação de edge

LpsEdgeItem(QGraphicsPathItem)
├── _edge_id
├── _relation: REQUIRES | EXCLUDES
└── set_relation(relation)  → muda estilo (sólida / tracejada)
```

### 1.11. Auto-save

`QTimer` em `MainWindow` (single-shot, 30s) que serializa o canvas
ativo em `tree_structure_json` no `lps_feature_models` se o dirty
flag estiver setado. Roda no thread principal (operação leve:
JSON ≤ 200KB → serialize ≤ 50ms).

---

## 2. Fluxo end-to-end

```
┌─────────────────────┐
│ User drag de comp A │
│ da paleta → canvas  │
└──────────┬──────────┘
           │
           ▼
┌──────────────────────────────────────────┐
│ LpsCanvasScene.dropEvent                 │
│ → cria LpsNodeItem em (x, y)             │
│ → LpsService.upsert_node(model_id, ...)  │
└──────────┬───────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────┐
│ User clica anchor do nó A e arrasta      │
│ até o nó B → cria edge REQUIRES         │
└──────────┬───────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────┐
│ User clica "Validar"                     │
│ → LpsSolverWorker.run()                  │
│ → pysat.Solver() — valida selection      │
│ → signals.finished(VALID|INVALID, info)  │
└──────────┬───────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────┐
│ User clica "Gerar Produto"                  │
│ → Dialog "Selecionar diretório de saída"    │
│ → LpsGeneratorWorker.run(model_id, output)  │
│ → TemplateEngine.render(...) por componente│
│ → LpsService.record_run(...)                │
└─────────────────────────────────────────────┘

(Fluxo alternativo: LLM agentic)
┌─────────────────────────────────────────────┐
│ User digita no chat:                        │
│   "Adicione OAuth2 e gere o esqueleto"      │
└──────────┬──────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────┐
│ LpsLlmWorker.run(prompt, system_prompt)     │
│ → LlmAdapter.generate(...)                  │
│ → IA emite tool_call(create_file, ...)      │
│ → FileSystemAgent.create_file(...)          │
│ → IA emite tool_call(create_directory, ...)│
│ → FileSystemAgent.create_directory(...)     │
│ → IA responde com resumo do que fez         │
└─────────────────────────────────────────────┘
```

---

## 3. Threading diagram

```
Main Thread (GUI)
├── MainWindow
│   ├── LpsPalettePanel        (read-only, dados do LpsService)
│   ├── LpsCanvasView/Scene    (QGraphicsView — todo input)
│   │   └── signals → emit na thread principal
│   └── LpsInspectorPanel      (form widgets — Qt signals)
│
└── QThreadPool.globalInstance()
    ├── LpsSolverWorker       (QRunnable — pysat — CPU-bound)
    ├── LpsGeneratorWorker    (QRunnable — Jinja2 — I/O bound)
    └── LpsLlmWorker          (QRunnable — HTTP — I/O bound)
            │
            └── _WorkerSignals(QObject) companion
                ├── finished(...)
                ├── failed(...)
                └── progress(...) (generator only)
```

### Gotcha PySide6 (já documentado em decisions.md)

Closures cross-thread quebram. Workers usam **bound methods** (não
lambda) — `_on_solve_finished(self, ...)` em vez de `lambda r: ...`.

---

## 4. Segurança

| Vetor | Mitigação |
|---|---|
| Path traversal da IA | `_safe_path` valida `target.startswith(workspace_root)` |
| Path injection | regex `_PATH_RE = r"^[a-zA-Z0-9._/\-]+$"` (sem `..`, sem `\\`, sem null bytes) |
| File bomb (1 GB) | `_MAX_FILE_SIZE = 1 MB` |
| Template injection (Jinja2 SSTI) | `SandboxedEnvironment` sem `__import__` |
| LLM prompt injection | system prompt reforça: "só use as tools; nunca execute comandos de sistema" |
| API key leak | ler de env var, nunca persistir no QSettings |

---

## 5. Migrações

Como o catálogo já tem dados do Change 006, o `lps_service` precisa
garantir que as tabelas novas existem (CREATE IF NOT EXISTS) sem
tocar nas antigas. A migração é **aditiva** — não destrói nada.

```python
class LpsService:
    _SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS lps_components (...);
    CREATE INDEX IF NOT EXISTS idx_lps_components_category ...;
    CREATE TABLE IF NOT EXISTS lps_feature_models (...);
    ...
    """

    def __init__(self, db_path: Path | None = None):
        self._db_path = db_path or default_catalog_path()
        with self._connect() as conn:
            conn.executescript(self._SCHEMA_SQL)
            conn.commit()
```

---

## 6. Trade-offs registrados

| Decisão | Trade-off |
|---|---|
| Mesmo DB (catalogo.db) | Backup único, mas misturar domínios no mesmo arquivo |
| pysat (não z3 puro-Python) | Velocidade > simplicidade; dependência C |
| QGraphicsView (não React Flow) | Performance nativa; curva Qt |
| LiteLLM | +50 deps transitivas; mas vale a abstração |
| SandboxedEnvironment | Limitado (sem `__import__`); aceitável pro caso de uso |
| pydantic para validação DSL | +1 dep; mas erros estruturados valem |

---

## 7. Anti-decisões (o que NÃO fazer)

- ❌ Implementar SAT solving manualmente — inviável, perde valor técnico.
- ❌ LLM provider-por-provider sem adapter — explosão de código.
- ❌ Executar tool calls sem sandbox — RCE esperando pra acontecer.
- ❌ Auto-save síncrono no thread principal (não bloqueia aqui, mas é
  princípio).
- ❌ Persistir feature model em JSON em vez de SQLite — perde queries,
  backup, FTS.
