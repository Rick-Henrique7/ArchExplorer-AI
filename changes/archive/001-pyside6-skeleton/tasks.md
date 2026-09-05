# Change 001 — Tasks: Esqueleto PySide6

> Checklist executável. Cada item é uma unidade de commit ou de verificação.
> Marque `[x]` conforme for completando.

---

## Bloco A — Repositório e metadados

- [ ] A1. `git init` em `C:\dev\projects\ArchExplorer\` com `git init -b main`
- [ ] A2. Configurar `user.name` e `user.email` localmente (não usar global):
      `git config user.name "Rick-Henrique7"` e `git config user.email "henrique.mdsantos2003@gmail.com"`
- [ ] A3. Criar `.gitignore` (Python + PySide6 + IDEs + Windows)
- [ ] A4. Criar `LICENSE` (Apache-2.0, copyright `Henrique Moraes dos Santos, 2026`)
- [ ] A5. Criar `README.md` com quickstart, status, link para `docs/`
- [ ] A6. Criar `CODEOWNERS` apontando `@Rick-Henrique7` como owner de tudo

## Bloco B — Dependências

- [ ] B1. Criar `pyproject.toml` com metadados + deps runtime (PySide6, requests) + deps dev (pytest, pytest-cov, pytest-mock)
- [ ] B2. Criar `requirements.txt` espelhando runtime deps (com comentário no topo apontando para `pyproject.toml`)
- [ ] B3. Criar `requirements-dev.txt` espelhando dev deps
- [ ] B4. Smoke install: `py -m venv .venv ; .\.venv\Scripts\Activate.ps1 ; pip install -r requirements.txt -r requirements-dev.txt` e verificar que PySide6 importa sem erro (`py -c "import PySide6; print(PySide6.__version__)"`)

## Bloco C — Código do app

- [ ] C1. Criar `app/__init__.py` com `__version__ = "0.1.0"`
- [ ] C2. Criar `app/ui/__init__.py` (vazio)
- [ ] C3. Criar `app/services/__init__.py` (vazio)
- [ ] C4. Criar `app/utils/__init__.py` (vazio)
- [ ] C5. Criar `app/main.py` com `main()` que instancia `QApplication` + `MainWindow` e chama `app.exec()`
- [ ] C6. Criar `app/ui/file_explorer.py` com `FileExplorerPanel(QWidget)` (placeholder: QLabel centralizado "File Explorer")
- [ ] C7. Criar `app/ui/code_editor.py` com `CodeEditorPanel(QWidget)` (placeholder: QLabel centralizado "Editor")
- [ ] C8. Criar `app/ui/visualizer.py` com `VisualizerPanel(QWidget)` (placeholder: QLabel centralizado "Visualizer")
- [ ] C9. Criar `app/ui/main_window.py` com `MainWindow(QMainWindow)`:
      - aceita `services: dict | None = None` no construtor (DIP)
      - título "ArchExplorer AI"
      - tamanho padrão 1100x700
      - `QWidget` central contendo `QSplitter(Qt.Orientation.Horizontal)` com os 3 painéis (proporções 25/45/30)
      - método público `panels() -> tuple[FileExplorerPanel, CodeEditorPanel, VisualizerPanel]` para os testes

## Bloco D — Testes

- [ ] D1. Criar `tests/__init__.py` (vazio)
- [ ] D2. Criar `tests/unit/__init__.py` (vazio)
- [ ] D3. Criar `tests/integration/__init__.py` (vazio)
- [ ] D4. Criar `tests/conftest.py` com fixture `qapp` (session-scoped) + seta `QT_QPA_PLATFORM=offscreen`
- [ ] D5. Criar `tests/unit/test_main_window.py` com:
      - `test_window_title_is_archexplorer_ai(qapp)`
      - `test_window_has_three_panels(qapp)` — usa `window.panels()` e verifica tipos
      - `test_splitter_has_three_children(qapp)` — inspeção direta do splitter
- [ ] D6. Rodar `py -m pytest -v` e confirmar **3 passed**

## Bloco E — Smoke visual manual

- [ ] E1. Rodar `py -m app.main` em venv ativada
- [ ] E2. Confirmar que a janela "ArchExplorer AI" aparece
- [ ] E3. Confirmar que tem 3 painéis com labels "File Explorer" / "Editor" / "Visualizer"
- [ ] E4. Confirmar que os separadores do splitter são arrastáveis
- [ ] E5. Confirmar que fechar a janela encerra o processo
- [ ] E6. Tirar screenshot para evidência (opcional, mas recomendado)

## Bloco F — CI e templates

- [ ] F1. Criar `.github/workflows/ci.yml` (windows-latest, Python 3.13, install + pytest)
- [ ] F2. Criar `.github/ISSUE_TEMPLATE/bug_report.md`
- [ ] F3. Criar `.github/ISSUE_TEMPLATE/feature_request.md`
- [ ] F4. Criar `.github/PULL_REQUEST_TEMPLATE.md` (referenciando o `changes/NNN-name/` correspondente)

## Bloco G — Commit e arquivamento

- [ ] G1. `git add .` e revisar com `git status` antes de commitar
- [ ] G2. `git commit -m "chore: bootstrap ArchExplorer AI with PySide6 skeleton"` com corpo explicando o que entra
- [ ] G3. `git log --oneline` mostra 1 commit no `main`
- [ ] G4. (Futuro, quando houver remote) arquivar `changes/001-pyside6-skeleton/` em `changes/archive/001-pyside6-skeleton/` — **não fazer agora**, pois é o commit inicial e o remote ainda não existe

## Bloco H — Comunicação ao Henrique

- [ ] H1. Reportar smoke test verde (3 passed)
- [ ] H2. Pedir confirmação visual de que a janela abre no Windows dele
- [ ] H3. **Pausar e aguardar** instalação do Ollama + `qwen2.5-coder:3b` antes de iniciar Change 002 (AI Engine + DiagramGenerator)

---

## Definition of Done (DoD)

Todos os blocos A–G acima marcados como completos, E1–E5 confirmados
visualmente, e H3 comunicado ao usuário. Só então marco a task pai do
`TodoWrite` como `completed`.
