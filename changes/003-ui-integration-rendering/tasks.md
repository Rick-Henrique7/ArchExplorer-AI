# Change 003 — Tasks: UI integration com rendering

> Checklist executável. Marcar `[x]` conforme conclusão.

---

## Bloco A — Helpers puros (sem Qt)

- [ ] A1. Criar `app/ui/file_inspector.py` com `@dataclass InspectResult(ok, content, file_type, error_message)` e função `inspect_file(path) -> InspectResult` (lida com whitelist, size, UTF-8)
- [ ] A2. Criar `app/ui/html_template.py` com constantes `MARKED_VERSION`, `MARKED_CDN`, `GITHUB_MARKDOWN_CSS`, `MERMAID_CDN` e função `build_html_template(markdown_text: str) -> str`
- [ ] A3. Testar `inspect_file` em `tests/unit/test_file_inspector.py` (10+ casos: válido, extensão ruim, binário, grande demais, missing)
- [ ] A4. Testar `build_html_template` em `tests/unit/test_html_template.py` (5+ casos: vazio, com markdown, com bloco mermaid, XSS via `<script>`, escape de `&`)

## Bloco B — FileExplorerPanel real

- [ ] B1. Reescrever `app/ui/file_explorer.py`: `QWidget` com `QTreeView` + `QFileSystemModel`
- [ ] B2. Setar root para `Path(root)` passado no construtor (default = `Path(os.getcwd())`)
- [ ] B3. `Signal(str) file_selected` declarado no nível de classe
- [ ] B4. Conectar `QTreeView.clicked` ao handler que valida + emite `file_selected` (com path absoluto via `model.filePath(index)`)
- [ ] B5. Constante `SUPPORTED_EXTENSIONS` no módulo (frozenset)

## Bloco C — CodeEditorPanel real

- [ ] C1. Reescrever `app/ui/code_editor.py`: `QWidget` com `QPlainTextEdit` read-only, fonte mono
- [ ] C2. Métodos públicos `set_content(text: str)` e `clear()`
- [ ] C3. Sem syntax highlighter neste change (deixar para change dedicado)

## Bloco D — VisualizerPanel + QWebEngineView

- [ ] D1. Reescrever `app/ui/visualizer.py`: `QWidget` com `QWebEngineView`
- [ ] D2. Métodos públicos: `show_loading(label)`, `show_markdown(text)`, `show_error(message)`, `show_idle()`
- [ ] D3. `show_markdown` chama `self._web.setHtml(build_html_template(text))`
- [ ] D4. `show_idle`, `show_loading`, `show_error` produzem HTML inline (sem template) — strings simples
- [ ] D5. Verificar que `QWebEngineView` inicializa sem warnings no headless test (smoke de instanciação)

## Bloco E — AnalysisWorker

- [ ] E1. Criar `app/ui/analysis_worker.py` com `_WorkerSignals(QObject)` (signals `finished(str)`, `failed(str)`) e `AnalysisWorker(QRunnable)`
- [ ] E2. Construtor recebe `ai_engine, code_content, file_type, file_label` keyword-only
- [ ] E3. `run()` chama `self._engine.analyze_architecture(self._code, self._file_type)`, captura `AIServiceUnavailableError` e `Exception` (genérico), emite `finished` ou `failed` exatamente uma vez
- [ ] E4. Testar em `tests/unit/test_analysis_worker.py`: cria worker com `MockAIProvider`, chama `run()` diretamente, valida signal emitida

## Bloco F — MainWindow wiring

- [ ] F1. Atualizar `app/ui/main_window.py`:
  - Instancia `FileExplorerPanel(root=cwd)`, `CodeEditorPanel`, `VisualizerPanel`
  - Conecta `file_explorer.file_selected` ao slot `_on_file_selected`
  - `_on_file_selected(path)`:
    - Chama `inspect_file(path)`
    - Se `not ok`: `code_editor.clear()` + `visualizer.show_error(reason)` + return
    - Senão: `code_editor.set_content(content)` + `visualizer.show_loading(name)`
    - Cria `AnalysisWorker`, conecta signals ao `visualizer`, `QThreadPool.globalInstance().start(worker)`
- [ ] F2. `app/main.py` agora instancia `services={"ai_engine": AIEngine(OllamaProvider())}` e passa para `MainWindow(services=services)`
- [ ] F3. Garantir que `MainWindow(services=None)` ainda funciona (com `MockAIProvider` como fallback, ou erro claro)

## Bloco G — Tests

- [ ] G1. `tests/unit/test_main_window.py`: atualizar para usar painéis reais; o smoke test continua passando
- [ ] G2. `tests/unit/test_supported_extensions.py`: parametrize com todas as extensões (whitelist + não-whitelist)
- [ ] G3. `tests/integration/test_ui_flow.py`:
  - Cria `MainWindow(services={"ai_engine": AIEngine(MockAIProvider({...}))})` com fixture que retorna markdown com bloco mermaid
  - Cria `tmp_path/calc.py` com 2 classes
  - Emite `file_explorer.file_selected.emit(str(calc_py))` diretamente
  - `QThreadPool.globalInstance().waitForDone(5000)`
  - Verifica que `code_editor._editor.toPlainText()` contém "class Calc"
  - Verifica que `visualizer._web` teve `setHtml` chamado (verifica via stub ou atributo público)
- [ ] G4. `py -m pytest` — todos verdes (≥ 100 testes)
- [ ] G5. `py -m pytest --cov=app.ui --cov-report=term-missing` — cobertura ≥ 85%

## Bloco H — Smoke manual

- [ ] H1. Ativar venv, `python -m app.main`
- [ ] H2. Janela abre com `QTreeView` mostrando o `cwd`
- [ ] H3. Clicar num `.py` (qualquer um do projeto) → editor central mostra código; painel direito mostra "Analyzing..." → depois markdown renderizado
- [ ] H4. Se o LLM incluir bloco ```mermaid, ver diagrama renderizado no painel direito
- [ ] H5. Clicar num `.png` (ou outra extensão não-whitelisted) → mensagem de erro, sem travar
- [ ] H6. Clicar em 3 arquivos rapidamente → todos completam, último resultado vence
- [ ] H7. Screenshot de evidência (opcional)

## Bloco I — Verificações finais

- [ ] I1. `py -m pytest` verde
- [ ] I2. `py -m app.main` abre sem warnings novos
- [ ] I3. Type hints em todas as funções públicas; `from __future__ import annotations` em todos os novos arquivos
- [ ] I4. Nenhuma referência a `PyQt6` no código
- [ ] I5. `git status` mostra apenas arquivos do change 003
- [ ] I6. Smoke ponta-a-ponta validado por screenshot ou confirmação verbal do Henrique

## Bloco J — Commit + arquivamento

- [ ] J1. `git add .` e revisar
- [ ] J2. `git commit -F .git/COMMIT_EDITMSG.tmp` com mensagem "feat: UI integration with QWebEngineView rendering"
- [ ] J3. `git log --oneline` → 6+ commits no `main`
- [ ] J4. Mover `changes/003-ui-integration-rendering/` para `changes/archive/003-ui-integration-rendering/`
- [ ] J5. Commit `chore: archive change 003`

## Bloco K — Comunicação

- [ ] K1. Reportar pytest verde + ≥ X tests + cobertura
- [ ] K2. Pedir screenshot de evidência (ou confirmação que viu o Mermaid renderizar)
- [ ] K3. Listar o que entra em **Change 004+** (próximos): syntax highlight, save/edit, atalhos, QSettings para última pasta, `extract_uml_structure` no menu de contexto, offline-first

---

## Definition of Done (DoD)

Todos os blocos A–J marcados, H1–H6 confirmados (pelo menos a janela
abrindo + 1 clique funcional), K1–K2 reportados ao usuário.
