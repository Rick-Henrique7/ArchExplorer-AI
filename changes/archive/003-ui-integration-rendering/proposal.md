# Change 003 — UI integration com rendering (merge 003 + 004)

> **Status:** Aguardando aprovação
> **Tipo:** Feature (UI integration + primeira renderização real)
> **Risco:** Alto (primeira vez que QWebEngineView roda; thread + signals + CDN)
> **Pré-requisito externo:** Ollama rodando com `qwen2.5-coder:3b` ✅ (validado no 002)

---

## 1. Contexto

Changes 001 e 002 entregaram a casca PySide6 + a camada de services
(`FileManager`, `AIEngine`, `DiagramGenerator`) com 91 testes verdes e
smoke real contra Ollama validado. A janela 3-painéis abre, mas tudo é
placeholder: clicar em arquivo não faz nada, o painel direito é só um
label, e o Mermaid vive em texto cru (se o usuário o extraísse).

Este change **funde 003 + 004 originais** (a seu pedido) e entrega a
primeira versão verdadeiramente usável do app: clicar num arquivo `.py`
dispara `analyze_architecture` em background, e o painel direito mostra
o **markdown renderizado** com blocos ```mermaid renderizados como
diagramas via Mermaid.js.

## 2. Mudança

### 2.1. Painéis reais (substituem os placeholders)

| Painel | Antes (001) | Depois (003) |
|---|---|---|
| Esquerdo | `QLabel` "File Explorer" | `QTreeView` + `QFileSystemModel` apontando para `cwd`. Whitelist de extensões. Emite `pyqtSignal(str) file_selected(path)`. |
| Central | `QLabel` "Editor" | `QPlainTextEdit` read-only. Mostra o conteúdo do arquivo selecionado. Sem syntax highlight (próximo change). |
| Direito | `QLabel` "Visualizer" | `QWebEngineView` com template HTML que carrega `marked.js` + `Mermaid.js` via CDN. Renderiza a resposta markdown da IA. |

### 2.2. Worker assíncrono

`AnalysisWorker(QRunnable)`:
- Recebe `AIEngine`, `path`, `code_content`, `file_type` no construtor
- Executa `AIEngine.analyze_architecture(code, file_type)` em `run()`
- Emite `finished(result: str)` ou `failed(error: str)` via signals
- Despachado via `QThreadPool.globalInstance().start(worker)`

### 2.3. Wiring no MainWindow

```
FileExplorerPanel.file_selected(path)
    │
    ▼
MainWindow._on_file_selected(path)
    │
    ├─► FileManager.read_file(path)            # lê o arquivo
    │       │  (FileOperationError → mostra erro no Visualizer)
    │       ▼
    │   (text_content, file_type)
    │       │
    ├─► CodeEditorPanel.set_content(text)     # atualiza painel central
    │
    └─► QThreadPool.start(AnalysisWorker)     # dispara inferência
            │
            ▼ (signal finished)
        VisualizerPanel.set_markdown(result)
            │
            ▼
        QWebEngineView.setHtml(html)           # renderiza
```

Sinais do VisualizerPanel:
- `show_loading()` — mostra "Analyzing..." no QWebEngineView
- `show_markdown(text)` — renderiza markdown
- `show_error(message)` — mostra erro formatado

### 2.4. HTML template (no Python, gerado por função)

```python
def build_html_template(markdown_text: str) -> str:
    """Returns a self-contained HTML page that:
    1. Loads marked@11 + mermaid@10.9.1 from jsDelivr
    2. Renders the markdown via marked, with ```mermaid blocks
       intercepted and rendered by mermaid
    3. Uses github-markdown-css for readable typography
    """
```

A função vive em `app/ui/visualizer.py` (próxima do consumer) e é
**testável como string** — sem precisar de QApplication.

### 2.5. Error states

| Situação | Resposta no Visualizer |
|---|---|
| Arquivo binário (UnicodeDecodeError) | `Binary file, not supported.` (sem chamar IA) |
| Arquivo ≥ 1 MB | `File too large (X MB). Limit is 1 MB.` (sem chamar IA) |
| Extensão fora da whitelist | `File extension not supported.` |
| `FileOperationError` (permissão) | Mensagem do erro |
| `AIServiceUnavailableError` | `AI service unavailable: <message>` |
| Qualquer outra exceção | `Unexpected error: <message>` |

### 2.6. Whitelist de extensões

```python
SUPPORTED_EXTENSIONS = frozenset({
    ".py", ".ts", ".tsx", ".jsx", ".java", ".json", ".md", ".txt",
})
```

Constante em `app/ui/file_explorer.py`. Configurável em change futuro
via `QSettings`.

## 3. Fora do escopo (vai para Changes futuros)

- Syntax highlighting (change dedicado)
- Editar e salvar arquivo (read-only por enquanto)
- Multiple tabs / split view
- Drag-and-drop de arquivos
- Search within file (Ctrl+F)
- `QSettings` para persistir a pasta raiz ou preferências
- Streaming de tokens do Ollama
- File watcher (auto-reload quando arquivo muda)
- Múltiplas ações no clique (analyze vs extract_uml — só `analyze_architecture` por enquanto)
- Atalhos de teclado (Ctrl+C/X/V, F2, Delete)
- Menu de contexto

## 4. Critérios de aceitação

- [ ] `py -m app.main` abre a janela com `QTreeView` mostrando o `cwd` à esquerda
- [ ] Clicar num arquivo `.py` exibe seu conteúdo no painel central
- [ ] Em paralelo (sem travar UI), o painel direito mostra "Analyzing..." e depois renderiza o markdown com blocos Mermaid (se houver) como diagramas visuais
- [ ] Rodar o app e clicar 3 arquivos seguidos: cada clique dispara worker novo, todos completam, último resultado vence no painel direito
- [ ] `FileExplorerPanel.file_selected` é um `pyqtSignal(str)` tipado
- [ ] `AnalysisWorker` é um `QRunnable` com signals `finished(str)` e `failed(str)`
- [ ] HTML template contém `marked@11` (ou superior) e `mermaid@10.9.1` pinned
- [ ] Whitelist de extensões rejeita `.exe`, `.dll`, `.png`, etc. com mensagem clara
- [ ] Arquivo binário não chama IA (mostra mensagem)
- [ ] Arquivo ≥ 1 MB não chama IA (mostra mensagem)
- [ ] `py -m pytest` verde (incluindo novos testes do worker + HTML template)
- [ ] Cobertura de `app/ui/` ≥ 85%
- [ ] `py -m app.main` continua abrindo sem warnings novos
- [ ] Type hints em todas as funções públicas
- [ ] Nenhuma referência a `PyQt6`

## 5. Riscos e mitigações

| Risco | Mitigação |
|---|---|
| `QWebEngineView` é pesado (Chromium ~200 MB) e exige inicialização mais cara | Smoke test headless verifica só que o widget instancia; render real exige display (testado manualmente pelo usuário) |
| CDN falha offline | HTML template tem `crossorigin` + tratamento de erro JS que mostra "Failed to load dependencies" no `<div id="content">` |
| `marked.js` parse de markdown grande trava a thread do QWebEngineView | Render acontece na thread do Chromium (separada da UI); UI continua responsiva |
| Worker acumula se o usuário clica rápido em vários arquivos | `QThreadPool.globalInstance()` já tem fila; cada worker é independente. Último resultado vence (race é OK para o UX) |
| Markdown do LLM tem XSS (`<script>`) | O HTML é gerado server-side (Python) com `markdown_text` HTML-escaped no `<pre id="raw">`. `marked.parse` aceita HTML, mas o `raw-md` é `.textContent` (texto puro), não HTML |
| `MermaidRenderer` (do 002) não é mais usado | Ele continua existindo — só não é chamado neste change. Mantém a porta aberta para `extract_uml_structure` em change futuro |
| Permissão de leitura de arquivo (`PermissionError`) | Capturado no `try/except` e exibido como erro no Visualizer |
| Encoding não-UTF-8 | `try: read_text(encoding='utf-8') except UnicodeDecodeError: → "binary file"` |
| `QFileSystemModel` pesado em diretórios grandes | Não virtualiza por padrão; usuário pode clicar num subdiretório específico. Limitação conhecida — change futuro pode usar `QSortFilterProxyModel` |

## 6. Definição de Pronto (DoD)

- [ ] 4 artefatos revisados e aprovados
- [ ] Implementação completa, todos os blocos A–I do `tasks.md` marcados
- [ ] `py -m pytest` verde (≥ 100 testes totais)
- [ ] Cobertura `app/ui/` ≥ 85%
- [ ] Henrique confirma visualmente: clica num `.py`, vê markdown renderizado, blocos Mermaid viram diagramas
- [ ] 1 screenshot de evidência (opcional, mas recomendado)
- [ ] `git log` no `main` mostra o commit
- [ ] Change arquivado em `changes/archive/003-ui-integration-rendering/`

## 7. Rollback

`git revert <commit>` desfaz tudo. Services do 002 e skeleton do 001
permanecem funcionais. A janela volta a abrir com os 3 placeholders
(estado pré-003).
