# Change 003 — Design: UI integration com rendering

> Decisões de **como** o wiring é montado. Mapeia `spec.md` para
> código concreto.

---

## 1. Mudanças nos painéis (substituem os do 001)

### 1.1. `FileExplorerPanel` — `QTreeView` + `QFileSystemModel`

```python
class FileExplorerPanel(QWidget):
    file_selected = Signal(str)  # absolute path

    SUPPORTED_EXTENSIONS = frozenset({...})
    MAX_FILE_SIZE = 1 * 1024 * 1024  # 1 MiB

    def __init__(self, root: Path, parent=None) -> None:
        super().__init__(parent)
        self._model = QFileSystemModel(self)
        self._model.setRootPath(str(root))
        # Optional: hide files outside whitelist? No — show everything,
        # reject in MainWindow. Visual filter is too limiting.
        self._view = QTreeView(self)
        self._view.setModel(self._model)
        self._view.setRootIndex(self._model.index(str(root)))
        self._view.clicked.connect(self._on_clicked)
        # ... layout
```

Decisões:
- Sem `QSortFilterProxyModel` neste change (risco: scroll/filter em
  diretórios grandes). Vem em change de UX.
- `setRootPath` + `setRootIndex` aponta a árvore para o `cwd` (sem
  mostrar os diretórios-ancestrais)
- Click signal conecta direto no handler que emite `file_selected`

### 1.2. `CodeEditorPanel` — `QPlainTextEdit` read-only

```python
class CodeEditorPanel(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._editor = QPlainTextEdit(self)
        self._editor.setReadOnly(True)
        # No syntax highlighter in this change
        # Use a monospace font for code legibility
        font = QFont("Consolas, Menlo, monospace", 10)
        self._editor.setFont(font)
        # ... layout

    def set_content(self, text: str) -> None:
        self._editor.setPlainText(text)

    def clear(self) -> None:
        self._editor.clear()
```

### 1.3. `VisualizerPanel` — `QWebEngineView` com template HTML

```python
class VisualizerPanel(QWidget):
    IDLE_HTML = "<h1>Click a file...</h1>"
    LOADING_HTML = "<h1>Analyzing...</h1>"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._web = QWebEngineView(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._web)
        self._set_idle()

    def _set_idle(self) -> None: ...
    def show_loading(self, label: str) -> None: ...
    def show_markdown(self, markdown: str) -> None:
        self._web.setHtml(build_html_template(markdown))
    def show_error(self, message: str) -> None: ...
```

`build_html_template` é **função pura** (testável sem QApplication) em
`app/ui/html_template.py`. Detalhes em §3.

## 2. Worker assíncrono

`QRunnable` não pode ter signals diretamente (não é `QObject`). Padrão
padrão: companion `QObject` com os signals, passada ao worker.

```python
# app/ui/analysis_worker.py

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

class _WorkerSignals(QObject):
    finished = Signal(str)  # result
    failed = Signal(str)    # error message

class AnalysisWorker(QRunnable):
    def __init__(self, *, ai_engine, code_content, file_type, file_label):
        super().__init__()
        self._engine = ai_engine
        self._code = code_content
        self._file_type = file_type
        self._label = file_label
        self.signals = _WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            result = self._engine.analyze_architecture(self._code, self._file_type)
        except AIServiceUnavailableError as exc:
            self.signals.failed.emit(f"AI service unavailable: {exc.message}")
        except Exception as exc:  # noqa: BLE001  (we want to catch all)
            self.signals.failed.emit(f"{type(exc).__name__}: {exc}")
        else:
            self.signals.finished.emit(result)
```

## 3. `build_html_template` (app/ui/html_template.py)

```python
from html import escape

MARKED_VERSION = "11.1.1"
MARKED_CDN = f"https://cdn.jsdelivr.net/npm/marked@{MARKED_VERSION}/marked.min.js"
GITHUB_MARKDOWN_CSS = (
    "https://cdn.jsdelivr.net/npm/github-markdown-css@5.5.1/"
    "github-markdown-dark.min.css"
)
MERMAID_CDN = "https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"


def build_html_template(markdown_text: str) -> str:
    escaped = escape(markdown_text)  # HTML-escape for safe embedding
    return _HTML_TEMPLATE.format(
        github_markdown_css=GITHUB_MARKDOWN_CSS,
        marked_cdn=MARKED_CDN,
        mermaid_cdn=MERMAID_CDN,
        raw_md=escaped,
    )


_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>ArchExplorer</title>
  <link rel="stylesheet" href="{github_markdown_css}">
  <script src="{marked_cdn}"></script>
  <script src="{mermaid_cdn}"></script>
  <style>
    body {{ box-sizing: border-box; margin: 0 auto; padding: 24px; max-width: 980px; }}
    .markdown-body {{ background: transparent; }}
  </style>
  <script>
    window.addEventListener('error', function(e) {{
      document.getElementById('content').innerHTML =
        '<h1>Failed to load dependencies</h1><p>' + e.message + '</p>';
    }});
  </script>
</head>
<body>
  <article class="markdown-body" id="content">Loading...</article>
  <pre id="raw-md" style="display:none">{raw_md}</pre>
  <script>
    (function() {{
      var md = document.getElementById('raw-md').textContent;
      var renderer = new marked.Renderer();
      var origCode = renderer.code.bind(renderer);
      renderer.code = function(code, lang) {{
        if ((lang || '').toLowerCase() === 'mermaid') {{
          return '<pre class="mermaid">' + code + '</pre>';
        }}
        return origCode(code, lang);
      }};
      marked.use({{ renderer: renderer }});
      document.getElementById('content').innerHTML = marked.parse(md);
      mermaid.initialize({{ startOnLoad: true, securityLevel: 'loose' }});
    }})();
  </script>
</body>
</html>
"""
```

**Por que `<pre id="raw-md">` com `.textContent` em vez de string JS literal:**
- O usuário pode colar markdown com `</script>` ou `${template}` — fácil de quebrar
- `<pre>` com display:none não renderiza visualmente, e `.textContent` retorna o texto decodificado de HTML entities (so `<` vira `<` de novo)
- `html.escape` (stdlib) faz exatamente o necessário: escapa `<`, `>`, `&`, `"`, `'`

**Por que CDN e não bundling:**
- Mudar marked/mermaid = bump version em uma linha, sem recompilar
- jsDelivr é confiável, cache global
- Offline-first fica para change futuro (pode-se usar `QWebEngineProfile` com `setHttpCacheType`)

**Por que `securityLevel: 'loose'`:**
- Mermaid v10 default é `strict` que bloqueia `<script>` e `onclick` no SVG
- 'loose' permite que LLMs coloquem HTML/Mermaid arbitrário
- Risco de XSS é mitigado pelo escape Python-side + `.textContent` (nenhum HTML do markdown vira HTML ativo)

## 4. Wiring no `MainWindow`

```python
class MainWindow(QMainWindow):
    def __init__(self, services: dict | None = None, parent=None) -> None:
        super().__init__(parent)
        self._services = services or {}
        self._build_ui()
        self._wire()

    def _build_ui(self) -> None:
        # ... same as 001 but with real panels
        cwd = Path(os.getcwd())
        self._file_explorer = FileExplorerPanel(root=cwd, parent=self)
        self._code_editor = CodeEditorPanel(self)
        self._visualizer = VisualizerPanel(self)
        # ... splitter setup (same as 001)

    def _wire(self) -> None:
        self._file_explorer.file_selected.connect(self._on_file_selected)

    @Slot(str)
    def _on_file_selected(self, path: str) -> None:
        # 1. Validate
        ok, reason = inspect_file(path)
        if not ok:
            self._code_editor.clear()
            self._visualizer.show_error(reason)
            return
        content, file_type = read_file(path), reason  # reason carries file_type here? no
        # (refactor: inspect_file returns InspectResult dataclass)
        # 2. Update editor
        self._code_editor.set_content(content)
        # 3. Dispatch worker
        self._visualizer.show_loading(Path(path).name)
        worker = AnalysisWorker(
            ai_engine=self._services["ai_engine"],
            code_content=content,
            file_type=file_type,
            file_label=Path(path).name,
        )
        worker.signals.finished.connect(self._visualizer.show_markdown)
        worker.signals.failed.connect(self._visualizer.show_error)
        QThreadPool.globalInstance().start(worker)
```

**Refinamento de `inspect_file`:** retorna `InspectResult` (dataclass):

```python
@dataclass
class InspectResult:
    ok: bool
    content: str
    file_type: str
    error_message: str  # populated when ok is False
```

Helper em `app/ui/file_inspector.py`. Lida com:
- Path validation
- Extension whitelist
- File size check
- UTF-8 decode
- file_type mapping

## 5. DI no `MainWindow`

O `MainWindow` agora **requer** `services` (ou tem fallback). Para
desenvolvimento local com `python -m app.main`, instancio
automaticamente no `app/main.py`:

```python
def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("ArchExplorer AI")
    services = {
        "ai_engine": AIEngine(OllamaProvider()),
    }
    window = MainWindow(services=services)
    window.show()
    return app.exec()
```

E testes podem injetar `MockAIProvider` no `services` dict.

## 6. Tratamento de erros (matriz)

Disparado em `_on_file_selected` antes do worker:
| Condição | Mensagem no Visualizer | Chama IA? |
|---|---|---|
| Extensão não-whitelisted | `File extension not supported.` | ❌ |
| Arquivo ≥ 1 MB | `File too large (X.X MB). Limit is 1.0 MB.` | ❌ |
| UnicodeDecodeError | `Binary file, not supported.` | ❌ |
| FileOperationError | mensagem original | ❌ |

Disparado no worker:
| Condição | Mensagem no Visualizer |
|---|---|
| `AIServiceUnavailableError` | `AI service unavailable: <message>` |
| Qualquer `Exception` | `<ExceptionClass>: <message>` |
| Sucesso | markdown renderizado |

## 7. Test strategy

### 7.1. Unit (sem Qt)

- `test_html_template.py`: testa `build_html_template` como string pura
- `test_file_inspector.py`: testa `inspect_file` com `tmp_path`
- `test_analysis_worker.py`: chama `worker.run()` diretamente (sem thread), conecta signals via `QSignalSpy`-like pattern (criando um slot de teste que acumula resultados)
- `test_supported_extensions.py`: parametrize de extensões

### 7.2. Integração (com `qapp` fixture)

- `test_main_window_flow.py`:
  - Cria MainWindow com `services={"ai_engine": AIEngine(MockAIProvider({"Patterns": "## Patterns\n- Foo\n```mermaid\nclassDiagram\n  A --> B\n```"}))}`
  - Cria um arquivo `.py` em `tmp_path`
  - Emite `file_explorer.file_selected.emit(str(py_file))` direto
  - Espera o `QThreadPool` drenar (usa `QThreadPool.waitForDone(timeout=5000)`)
  - Verifica que `code_editor` tem o conteúdo e `visualizer.show_markdown` foi chamado com a fixture

### 7.3. Manual (Henrique)

- Rodar app
- Clicar num `.py` real
- Ver markdown renderizado
- Ver Mermaid blocks virarem diagramas

## 8. Estrutura de arquivos (pós-merge)

```
app/ui/
├── __init__.py
├── main_window.py       # modificado — wiring real
├── file_explorer.py     # modificado — QTreeView + QFileSystemModel + signals
├── code_editor.py       # modificado — QPlainTextEdit read-only
├── visualizer.py        # modificado — QWebEngineView
├── analysis_worker.py   # NOVO — QRunnable
├── file_inspector.py    # NOVO — InspectResult + inspect_file()
└── html_template.py     # NOVO — build_html_template + constantes
```

Tests:
```
tests/unit/
├── test_main_window.py       # modificado
├── test_html_template.py     # NOVO
├── test_file_inspector.py    # NOVO
├── test_analysis_worker.py   # NOVO
└── test_supported_extensions.py  # NOVO
```

## 9. Compatibilidade com Changes anteriores

- `app/main.py` muda: precisa instanciar `services={...}` com `AIEngine(OllamaProvider())`. Sem isso, o `MainWindow` quebra ao tentar despachar worker.
- `app/services/__init__.py`: nenhum export novo necessário
- `app/services/ai_engine.py`: nenhuma mudança
- `app/services/diagram_generator.py`: nenhuma mudança (continua disponível para futuro)

## 10. O que **NÃO** está neste design

- Code highlighting (Pygments no Qt? Mudança dedicada)
- Editar/salvar arquivo
- Streaming de tokens
- Offline (sem CDN)
- File watcher
- Múltiplas abas
- Syntax theme customizado
- Atalhos de teclado
- Múltiplas ações no clique (só `analyze_architecture` por enquanto)

## 11. Trade-offs

| Decisão | Custo | Benefício |
|---|---|---|
| CDN em vez de bundle | Requer internet no 1º uso | Bump trivial de versão, sem recompilar |
| `<pre id="raw-md">` em vez de string JS | HTML 1 elemento a mais | XSS-safe trivialmente |
| `QRunnable` + signals companion | Boilerplate (~10 LOC) | Worker reusável, signals limpos |
| Whitelist de extensões | Usuário não pode analisar `.yaml` por exemplo | Segurança: nada binário vira prompt |
| 1 MB limit | Arquivos grandes rejeitados | Inferência cabe no contexto de 32k do 3B (~24k tokens) |
| `MermaidRenderer` do 002 não usado | Código "morto" | Mantém porta aberta para `extract_uml_structure` |
| Sem `QSettings` | Pasta raiz não persiste | Menos código, mudança fica em change dedicado |
