# Change 003 — Spec: UI integration com rendering

> Comportamento observável. Para **como** é implementado, veja
> `design.md`.

---

## 1. Comportamento na abertura do app

1. `py -m app.main` é executado
2. Janela "ArchExplorer AI" 1100×700 abre
3. **Painel esquerdo** mostra a árvore de diretórios do `cwd` (raiz do processo)
4. **Painel central** mostra texto vazio (read-only)
5. **Painel direito** mostra o placeholder: "Click a file in the explorer to analyze its architecture."

## 2. Comportamento ao clicar num arquivo suportado

Disparo: clique simples do mouse em qualquer entrada do `QTreeView`
cuja extensão esteja em `SUPPORTED_EXTENSIONS` (e tamanho < 1 MB).

Sequência:
1. **Imediato** (na thread da UI):
   - `MainWindow._on_file_selected(path)` é chamado via signal
   - Lê o arquivo via `FileManager`-equivalente (helper local, ver `design.md` §3.3)
   - Detecta `file_type` a partir da extensão
   - Atualiza `CodeEditorPanel.set_content(text)` (síncrono)
   - Chama `VisualizerPanel.show_loading()`
2. **Em background** (no `QThreadPool`):
   - `AnalysisWorker.run()` chama `AIEngine.analyze_architecture(text, file_type)`
3. **Ao completar** (de volta na thread da UI via signal `finished`):
   - `VisualizerPanel.show_markdown(result)` atualiza o `QWebEngineView`
4. **Em caso de erro** (signal `failed`):
   - `VisualizerPanel.show_error(message)` mostra mensagem formatada

A UI nunca bloqueia — clicar em outros arquivos durante a inferência é
permitido (novo worker é despachado).

## 3. Comportamento por tipo de arquivo

| Extensão | file_type passado à IA |
|---|---|
| `.py` | `"python"` |
| `.ts`, `.tsx` | `"typescript"` |
| `.jsx`, `.js` | `"javascript"` |
| `.java` | `"java"` |
| `.json` | `"json"` |
| `.md` | `"markdown"` |
| `.txt` | `"text"` |
| (outras) | rejeitado — sem chamar IA |

## 4. Estados do painel direito

| Estado | Quando | Conteúdo |
|---|---|---|
| **idle** | boot ou após erro | `"Click a file in the explorer to analyze its architecture."` |
| **loading** | após clique, antes de `finished`/`failed` | `"Analyzing <basename> with Qwen 2.5 Coder..."` + spinner CSS |
| **rendered** | `finished(result)` | HTML com markdown renderizado (Mermaid blocks viram diagramas) |
| **error** | `failed(message)` | HTML com `<h1>Error</h1>` + `<pre>{message}</pre>` |

## 5. Worker: `AnalysisWorker`

```python
class AnalysisWorker(QRunnable):
    """Runs AIEngine.analyze_architecture in a background thread."""
    # Signals are declared on a companion QObject because QRunnable
    # itself is not a QObject. The worker takes a reference to that
    # QObject and emits via it.

    finished = Signal(str)   # result markdown
    failed = Signal(str)     # error message
```

API:
```python
def __init__(
    self,
    *,
    ai_engine: AIEngine,
    code_content: str,
    file_type: str,
    file_label: str,        # for logging/diagnostics
) -> None: ...

def run(self) -> None:
    # called by QThreadPool; emits finished or failed exactly once
```

## 6. HTML template

`build_html_template(markdown_text: str) -> str` produz:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>ArchExplorer</title>
  <link rel="stylesheet" href=".../github-markdown-css@5/.../github-markdown-dark.min.css">
  <script src=".../marked@11/marked.min.js"></script>
  <script src=".../mermaid@10.9.1/dist/mermaid.min.js"></script>
  <script>/* error handler if CDN fails */</script>
  <style>body { box-sizing: border-box; margin: 0 auto; padding: 24px; }</style>
</head>
<body>
  <article class="markdown-body" id="content">Loading...</article>
  <pre id="raw-md" style="display:none">{HTML_ESCAPED_MARKDOWN}</pre>
  <script>
    (function() {
      var md = document.getElementById('raw-md').textContent;
      var renderer = new marked.Renderer();
      var origCode = renderer.code.bind(renderer);
      renderer.code = function(code, lang) {
        if ((lang || '').toLowerCase() === 'mermaid') {
          return '<pre class="mermaid">' + code + '</pre>';
        }
        return origCode(code, lang);
      };
      marked.use({ renderer: renderer });
      document.getElementById('content').innerHTML = marked.parse(md);
      mermaid.initialize({ startOnLoad: true, securityLevel: 'loose' });
    })();
  </script>
</body>
</html>
```

Garantias:
- `marked@11.x` (latest stable v11)
- `mermaid@10.9.1` (já pinado no `MermaidRenderer` do 002)
- O `markdown_text` é HTML-escaped antes de ir para `<pre>`, impedindo
  XSS via `<script>` no markdown
- Erro de carregamento de CDN → `Failed to load dependencies` no
  `<div id="content">` (via listener `window.onerror`)

## 7. Extensões suportadas

`SUPPORTED_EXTENSIONS = frozenset({".py", ".ts", ".tsx", ".jsx", ".java", ".json", ".md", ".txt"})`

Constante em `app/ui/file_explorer.py`. Outros: rejeitados com
`File extension not supported.`

## 8. Limite de tamanho

`MAX_FILE_SIZE = 1 * 1024 * 1024` (1 MiB). Acima disso: rejeitado com
`File too large (X.X MB). Limit is 1.0 MB.`

## 9. Encoding

`utf-8` estrito. Se `read_text(encoding="utf-8")` levantar
`UnicodeDecodeError` ou `UnicodeEncodeError`: rejeitado com
`Binary file, not supported.`

## 10. Sinais expostos

| Painel | Signal | Payload |
|---|---|---|
| `FileExplorerPanel` | `file_selected(path)` | `str` (caminho absoluto) |
| `AnalysisWorker` | `finished(result)` | `str` (markdown) |
| `AnalysisWorker` | `failed(message)` | `str` (mensagem) |
| `VisualizerPanel` | nenhum público (é sink) | — |

## 11. Test contracts

### 11.1. Unit (sem QApplication)

- `test_html_template.py`: `build_html_template("")` contém `marked`, `mermaid`, `github-markdown-css`; HTML-escape preserva `<`/`>`/`&`; Mermaid block é interceptado
- `test_extensions.py`: `is_supported(Path("foo.py"))` é True; `is_supported(Path("foo.exe"))` é False
- `test_analysis_worker.py`: `AnalysisWorker.run()` com `MockAIProvider` emite `finished` com a string esperada
- `test_file_inspector.py`: `inspect_file(path)` retorna `(content, file_type)` ou levanta erros tipados

### 11.2. Integração (com `qapp` fixture)

- `test_main_window_flow.py`: instala `MockAIProvider`, simula `file_selected` signal, verifica que `VisualizerPanel.show_markdown` é chamado
- Não testa render visual (precisa display)

### 11.3. Manual

- Clicar num `.py` real, ver diagrama Mermaid renderizado (se o LLM incluir um bloco ```mermaid na resposta)

## 12. Restrições

- Python 3.10–3.13 (mesmo do 001/002)
- Windows 11 (mesmo)
- **Sem novas Python deps** (marked.js + Mermaid.js + github-markdown-css via CDN; offline-first é nice-to-have futuro)
- PySide6 6.11+ (já tem `QtWebEngineWidgets`)
