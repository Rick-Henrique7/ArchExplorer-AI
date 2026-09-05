# Change 001 — Esqueleto PySide6 + layout 3-painéis

> **Status:** Aguardando aprovação
> **Tipo:** Bootstrap de projeto
> **Risco:** Baixo (zero lógica de negócio)
> **Pré-requisito externo:** Nenhum (Ollama fica fora deste change)

---

## 1. Contexto

O workspace `C:\dev\projects\ArchExplorer\` contém apenas os 5 documentos de especificação (`docs/`) e está sem repositório Git, sem dependências instaladas e sem código. O ambiente do Henrique tem:

- Python **3.13.13** (via `py` launcher, fora do PATH direto)
- Git **2.53.0**
- **Ollama não instalado** (decidido que será instalado antes do Change 002)
- Windows 11 + PowerShell 5.x

A escolha de toolchain já foi fechada com o usuário nesta sessão:

| Decisão | Valor |
|---|---|
| Workflow | SDD no estilo Agro-IoT (trunk-based, `changes/NNN-name/`, squash) |
| GUI toolkit | **PySide6** (LGPL, drop-in do PyQt6 dos docs) |
| LLM backend | **Aguardar Ollama** — sai no Change 002 |
| Escopo do 001 | Esqueleto + layout 3-painéis, **0 features de IA** |

Os documentos `docs/` estão escritos para **PyQt6**. Como PySide6 é drop-in, vou apenas trocar os imports (`from PySide6.QtWidgets import ...` em vez de `from PyQt6.QtWidgets import ...`). Todo o resto — interfaces, nomenclatura, SOLID, diretriz de "não usar emojis, usar ícones" — permanece válido.

## 2. Mudança

Criar a base executável do ArchExplorer AI:

1. **Repositório Git** inicializado em `C:\dev\projects\ArchExplorer\` com branch `main` e `.gitignore` Python.
2. **Estrutura de pastas** espelhando a árvore proposta em `docs/frontend/front.md`:
   - `app/` (entry point + ui/ + services/ + utils/)
   - `tests/unit/` e `tests/integration/`
   - `.github/workflows/`, `.github/ISSUE_TEMPLATE/`, `.github/PULL_REQUEST_TEMPLATE.md`
   - `CODEOWNERS`
3. **`app/main.py`** com `QApplication` + `MainWindow`, executável via `py -m app.main`.
4. **`app/ui/main_window.py`** com `QMainWindow` + `QSplitter` horizontal de 3 painéis:
   - Coluna esquerda: `FileExplorerPanel` (placeholder com label "File Explorer")
   - Coluna central: `CodeEditorPanel` (placeholder com label "Editor")
   - Coluna direita: `VisualizerPanel` (placeholder com label "Visualizer")
5. **Pyproject + requirements** fixando PySide6, pytest, pytest-cov, pytest-mock, requests.
6. **1 smoke test** (`tests/unit/test_main_window.py`) que:
   - instancia `MainWindow` com `QApplication` headless (`offscreen` platform)
   - afirma que a janela tem título "ArchExplorer AI"
   - afirma que o splitter tem exatamente 3 filhos
   - afirma que cada painel é uma subclasse esperada
7. **CI no GitHub Actions** (`windows-latest`, Python 3.13): install + pytest.
8. **Documentação inicial**: `README.md` com quickstart, `LICENSE` Apache-2.0, `CODEOWNERS`.
9. **Templates** de issue (bug + feature) e PR.

## 3. Fora do escopo (vai para Changes futuros)

- Qualquer chamada ao Ollama ou ao Qwen 2.5 Coder
- `FileManager`, `AIEngine`, `DiagramGenerator` concretos
- Syntax highlighter real (só placeholder)
- `QFileSystemModel` populado (só placeholder vazio)
- Renderização Mermaid.js no `QWebEngineView` (só placeholder)
- Menu de contexto funcional, atalhos de teclado
- Ícones reais (só labels por enquanto — ícones viram em change dedicado)
- Empacotamento (PyInstaller/Nuitka) — outro change

## 4. Critérios de aceitação

- [ ] `py -m app.main` abre uma janela "ArchExplorer AI" com 3 painéis lado a lado
- [ ] `py -m pytest` roda e exibe **1 passed** (smoke test)
- [ ] Estrutura de pastas confere com `docs/frontend/front.md` (adaptada para PySide6)
- [ ] `git log` no `main` mostra 1 commit inicial contendo tudo (docs + change artifacts + skeleton)
- [ ] `requirements.txt` instala limpo em venv novo no Windows
- [ ] `LICENSE` é Apache-2.0
- [ ] `.github/workflows/ci.yml` é sintaticamente válido (validável via `actionlint` ou por inspeção)

## 5. Riscos e mitigações

| Risco | Mitigação |
|---|---|
| PySide6 não instala no Python 3.13 (que é recém-saído) | Fixar `PySide6>=6.8` na requirements; se falhar, voltar para 3.12 ou PyQt6 |
| `QWebEngineView` requer Chromium pesado — pode falhar no smoke test | Smoke test usa plataforma `offscreen` e **não instancia** `QWebEngineView` real; só verifica que o placeholder é um `QWidget` |
| `py` launcher vs `python` no PATH | Documentar no README que o comando é `py -m ...` (não `python -m ...`) |
| GitHub Actions sem `secrets`/`PAT` configurados | CI só faz `pip install` + `pytest`; não precisa de credenciais |

## 6. Rollback

Por ser o **commit inicial** do repositório, rollback = `git update-ref -d HEAD` ou apagar o repo e reiniciar. Sem risco de perda de trabalho pré-existente.

## 7. Definition of Done

- [ ] 4 artefatos deste change revisados e aprovados pelo Henrique
- [ ] Commit inicial no `main` verde
- [ ] Smoke test passando localmente
- [ ] Henrique confirma que a janela abre no Windows dele (screenshot ou confirmação verbal)
- [ ] Este change é arquivado (movido para `changes/archive/001-pyside6-skeleton/`) após merge — quando houver PR flow ativo. No commit inicial, fica em `changes/001-...` mesmo.
