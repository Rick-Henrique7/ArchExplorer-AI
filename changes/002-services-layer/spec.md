# Change 002 — Spec: Services layer

> Comportamento observável dos 3 serviços. Para **como** são
> implementados, veja `design.md`.

---

## 1. FileManager (`app/services/file_manager.py`)

### 1.1. Dataclass `FileItem`

```python
@dataclass(frozen=True)
class FileItem:
    name: str          # "main.py"
    path: str          # "C:/projeto/app/main.py"  (absoluto, normalizado)
    is_dir: bool
    size: int          # bytes; 0 para diretórios
```

### 1.2. API

```python
class FileManager:
    def __init__(self) -> None: ...
    def list_directory(self, path: str) -> list[FileItem]: ...
    def create_folder(self, target_dir: str, name: str) -> str: ...   # retorna path criado
    def create_file(self, target_dir: str, name: str, content: str = "") -> str: ...
    def copy_item(self, source_path: str, destination_dir: str) -> str: ...
    def move_item(self, source_path: str, destination_dir: str) -> str: ...
    def delete_item(self, path: str) -> None: ...
    def copy_to_clipboard(self, path: str) -> None: ...   # marca origem + modo COPY
    def cut_to_clipboard(self, path: str) -> None: ...    # marca origem + modo CUT
    def paste_from_clipboard(self, destination_dir: str) -> str | None: ...
    def clipboard_state(self) -> ClipboardState | None: ...
```

### 1.3. Comportamento

- `list_directory` falha com `FileOperationError` se `path` não existe
  ou não é diretório. Retorna lista **vazia** se diretório vazio.
- `create_folder` / `create_file` falham se nome já existe, caracteres
  ilegais no SO, ou sem permissão. **Não sobrescreve.**
- `copy_item` / `move_item` preservam o nome do item de origem. Se já
  existir destino com mesmo nome, falha com `FileOperationError` (sem
  auto-rename).
- `delete_item` remove arquivo **ou** árvore de diretório recursivamente.
  Falha com `FileOperationError` em caso de permissão.
- Clipboard interno: armazena **um único** item por vez (origem + modo).
  `paste_from_clipboard` retorna `None` se clipboard vazio; caso
  contrário executa a operação, limpa o clipboard se era CUT (operação
  destrutiva), mantém se era COPY.

### 1.4. Erros

- `FileOperationError(message: str, path: str | None = None)` — toda
  falha de I/O. `path` é o caminho envolvido, se aplicável.

## 2. AIEngine (`app/services/ai_engine.py`)

### 2.1. Protocol `IAIProvider`

```python
class IAIProvider(Protocol):
    def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float | None = None,
    ) -> str: ...
```

LSP: qualquer implementação concreta é intercambiável sem que
`AIEngine` saiba qual é.

### 2.2. `OllamaProvider`

```python
class OllamaProvider:
    def __init__(
        self,
        *,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5-coder:3b",
        timeout: float = 120.0,
        session: requests.Session | None = None,
    ) -> None: ...
```

- `POST {base_url}/api/generate` com body `{"model", "prompt", "stream": false, "options": {"temperature": ...}, "system": ...}`
- Lê `response.response` do JSON retornado
- Falha com `AIServiceUnavailableError` se:
  - Conexão recusada / timeout
  - HTTP status >= 400
  - Resposta sem campo `response`

### 2.3. `MockAIProvider`

```python
class MockAIProvider:
    def __init__(self, fixtures: dict[str, str] | None = None) -> None: ...
    def generate(self, prompt: str, *, system=None, temperature=None) -> str: ...
```

- `fixtures` mapeia substring do prompt → resposta fixa
- Se nenhuma fixture casa, retorna string determinística baseada no hash do prompt (para reprodutibilidade de testes)

### 2.4. `AIEngine` (orquestrador)

```python
class AIEngine:
    def __init__(self, provider: IAIProvider) -> None: ...
    def generate_component(self, prompt: str, context_path: str) -> str: ...
    def analyze_architecture(self, code_content: str, file_type: str) -> str: ...
    def extract_uml_structure(self, code_content: str) -> str: ...
```

Cada método monta um prompt interno via template (constante na classe),
chama `provider.generate(...)`, e retorna a string crua. **Não faz
parsing** — parsing é responsabilidade do `DiagramGenerator` ou de quem
consumir.

### 2.5. Erros

- `AIServiceUnavailableError(message: str, cause: Exception | None = None)` — backend inacessível

## 3. DiagramGenerator (`app/services/diagram_generator.py`)

### 3.1. Protocol `BaseDiagramRenderer`

```python
class BaseDiagramRenderer(Protocol):
    def sanitize(self, raw_response: str) -> str: ...
    def validate(self, diagram_text: str) -> bool: ...
    def render_to_html(self, diagram_text: str) -> str: ...
```

OCP: futuros `PlantUMLRenderer`, `GraphvizRenderer` seguem o mesmo contrato.

### 3.2. `MermaidRenderer`

```python
class MermaidRenderer:
    MERMAID_VERSION = "10.9.1"
    MERMAID_CDN = "https://cdn.jsdelivr.net/npm/mermaid@{ver}/dist/mermaid.min.js"
    VALID_KEYWORDS = ("classDiagram", "sequenceDiagram", "flowchart", "graph", "stateDiagram", "erDiagram", "gantt", "pie")
    MERMAID_BLOCK_RE = re.compile(r"```mermaid\s*\n(.*?)```", re.DOTALL)
    GENERIC_BLOCK_RE = re.compile(r"```(\w+)?\s*\n(.*?)```", re.DOTALL)
```

**Comportamento de `sanitize`:**
1. Tenta `MERMAID_BLOCK_RE` (procura ```mermaid ... ```)
2. Se não achar, tenta `GENERIC_BLOCK_RE` e usa o bloco se a linguagem
   for `mermaid` (com ou sem suffix) ou se o conteúdo começar com um
   `VALID_KEYWORDS`
3. Se ainda não achar, retorna o texto cru (assume que já é Mermaid
   puro)
4. **Falha com `DiagramParsingError`** apenas se o texto resultante for
   vazio

**Comportamento de `validate`:**
- `True` se o texto não-vazio começar com qualquer `VALID_KEYWORDS` ou
  contiver `-->`, `--|>` ou outros operadores Mermaid comuns
- `False` caso contrário (caller decide se é erro fatal)

**Comportamento de `render_to_html`:**
- Retorna string HTML completa com:
  - `<!DOCTYPE html>` + meta charset
  - `<script src="MERMAID_CDN">` (com versão fixada)
  - `<script>mermaid.initialize({ startOnLoad: true })</script>`
  - `<body><div class="mermaid">{sanitized}</div></body>`
- Aplica `sanitize` antes de injetar (defesa em profundidade)

### 3.3. Erros

- `DiagramParsingError(message: str, raw: str | None = None)` — só
  levantado por `sanitize` quando o texto é vazio

## 4. Contratos de teste

### 4.1. Unitários

- **`test_file_manager.py`** — usa fixture `tmp_path` do pytest; testa
  cada operação em diretório temporário; valida exceções para casos
  de erro
- **`test_ai_engine.py`** — usa `MockAIProvider` para validar as
  pipelines isoladas; usa `requests_mock` para validar `OllamaProvider`
  com HTTP mockado; cobre `AIServiceUnavailableError`
- **`test_diagram_generator.py`** — testa cada caso de sanitize
  (com fence, sem fence, com lixo, vazio); valida detecção de
  keywords; verifica HTML output com Mermaid.js referenciado

### 4.2. Integration (gated)

- **`tests/integration/test_ai_ollama_live.py`** — decorado com
  `@pytest.mark.skipif(not os.getenv("OLLAMA_TEST"), reason="...")`;
  bate no Ollama real em `localhost:11434` com prompt mínimo; valida
  resposta não-vazia

## 5. Restrições de ambiente

- Mesmas do Change 001: Python 3.10–3.13, Windows 11
- Nova dep dev: `requests-mock>=1.12`
- Sem novas deps runtime
