# Change 001 — Design: Esqueleto PySide6

> Decisões de **como** o esqueleto será estruturado. Mapeia os requisitos
> de `spec.md` para código concreto.

---

## 1. Adaptação PyQt6 → PySide6

Os documentos em `docs/` foram escritos para PyQt6. PySide6 mantém a
mesma API Qt6 com imports renomeados:

| PyQt6 (docs) | PySide6 (este projeto) |
|---|---|
| `from PyQt6.QtWidgets import ...` | `from PySide6.QtWidgets import ...` |
| `from PyQt6.QtCore import ...` | `from PySide6.QtCore import ...` |
| `from PyQt6.QtWebEngineWidgets import ...` | `from PySide6.QtWebEngineWidgets import ...` |
| Licença GPL/comercial | LGPL (mais permissiva) |

Sem `sip`/`PyQt6-specific` code paths — toda API usada nos docs é
idêntica entre as duas bindings. Nenhuma menção a "PyQt6" no código;
todos os imports usam PySide6.

## 2. Estrutura de arquivos (final, pós-change)

```
C:\dev\projects\ArchExplorer\
├── .git/
├── .github/
│   ├── workflows/
│   │   └── ci.yml
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug_report.md
│   │   └── feature_request.md
│   └── PULL_REQUEST_TEMPLATE.md
├── .gitignore
├── app/
│   ├── __init__.py                # version string, metadata
│   ├── main.py                    # entry point: QApplication + MainWindow
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── main_window.py         # QMainWindow + QSplitter (3 colunas)
│   │   ├── file_explorer.py       # FileExplorerPanel (placeholder)
│   │   ├── code_editor.py         # CodeEditorPanel (placeholder)
│   │   └── visualizer.py          # VisualizerPanel (placeholder)
│   ├── services/                  # vazio neste change, só __init__.py
│   │   └── __init__.py
│   └── utils/                     # vazio neste change, só __init__.py
│       └── __init__.py
├── tests/
│   ├── __init__.py
│   ├── unit/
│   │   ├── __init__.py
│   │   └── test_main_window.py    # smoke test dos 3 painéis
│   └── integration/               # vazio neste change
│       └── __init__.py
├── docs/                          # já existe, não mexer
├── changes/
│   └── 001-pyside6-skeleton/      # este change (4 artefatos)
├── CODEOWNERS
├── LICENSE                        # Apache-2.0
├── README.md                      # quickstart + status
├── pyproject.toml                 # build config + deps
└── requirements.txt               # deps runtime (gerado a partir do pyproject)
```

## 3. Decisões de design

### 3.1. Entry point em `app/main.py` (não `if __name__ == "__main__"` solto)

Permite `py -m app.main` (modular, evita problemas de import relativo
quando rodar de diretórios diferentes) e facilita testes que importam
`app.main` sem efeitos colaterais.

```python
# app/main.py
def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("ArchExplorer AI")
    window = MainWindow()
    window.show()
    return app.exec()

if __name__ == "__main__":
    sys.exit(main())
```

### 3.2. Painéis como classes separadas (não métodos do MainWindow)

Cada painel vira uma `QWidget` subclasse em arquivo próprio. Isso:

- casa com o `front.md` (cada painel é um módulo)
- facilita evolução independente (cada painel ganha funcionalidade no seu
  próprio change)
- permite mockar o painel em testes futuros

```python
# app/ui/file_explorer.py
class FileExplorerPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        label = QLabel("File Explorer", self)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
```

### 3.3. Sem `QFileSystemModel` ainda

`docs/frontend/front.md` pede `QTreeView` + `QFileSystemModel` populado
com a pasta do projeto. **Não fazemos isso no Change 001**: é
funcionalidade, não esqueleto. Vem no Change dedicado a `FileManager`.

### 3.4. Sem `QWebEngineView` ainda

`QWebEngineView` puxa Chromium (centenas de MB) e exige inicialização
mais cara. No Change 001 o painel direito é um `QWidget` com `QLabel`.
O `QWebEngineView` real entra quando o `DiagramGenerator` for
implementado (Change 003 ou posterior).

### 3.5. DI no MainWindow (preparado, não usado ainda)

`MainWindow.__init__` aceita `services: dict | None = None` para
permitir injeção de mocks em testes futuros. No Change 001 o dict é
ignorado, mas a assinatura fica pronta:

```python
class MainWindow(QMainWindow):
    def __init__(
        self,
        services: dict[str, object] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._services = services or {}
        ...
```

Isso casa com o **DIP** da `docs/guidelines/diretriz.md`.

### 3.6. Sem ícones (ainda)

A diretriz diz "não use emojis, prefira ícones". Mas como o Change 001
não tem UI funcional (só labels), ícones seriam prematuros. O change
de UI/UX de ícones virá depois (talvez Change 005 ou dedicado).

### 3.7. pyproject.toml como fonte da verdade das deps

- `pyproject.toml` define deps em `[project]` e `[project.optional-dependencies]`
- `requirements.txt` é gerado a partir dele (pinning simples, sem hash)
- CI e README referenciam o `pyproject.toml`

Razão: ferramentas modernas (`pip install -e .`, `uv`, `poetry`)
trabalham com pyproject. Manter o `requirements.txt` em sincronia é
fácil via comentário no topo do arquivo apontando para o pyproject.

### 3.8. Smoke test usando `qtbot`? **Não**

`pytest-qt` é uma dependência extra e traz boilerplate. Para UM smoke
test, criar `QApplication` manualmente com `QT_QPA_PLATFORM=offscreen`
via `conftest.py` é mais leve:

```python
# tests/conftest.py
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app
    app.quit()
```

## 4. Fluxo de inicialização (sequência)

```
[py -m app.main]
    │
    ▼
[app.main.main()]
    │
    ├─► QApplication(sys.argv)
    │       └─ setApplicationName("ArchExplorer AI")
    │
    ├─► MainWindow()                  # cria janela + 3 painéis (placeholders)
    │
    ├─► window.show()                 # exibe a janela
    │
    └─► app.exec()                    # loop de eventos (bloqueia)
            │
            └─► usuário fecha janela
                    │
                    └─► app.exec() retorna
                            │
                            └─► main() retorna 0
```

## 5. CI no GitHub Actions

Workflow único `ci.yml` que:

- roda em `windows-latest` (o ambiente alvo é Windows)
- Python 3.13
- `pip install -r requirements.txt -r requirements-dev.txt`
- `pytest -v`
- falha = status vermelho no PR

Sem matrix, sem cache, sem upload de artefato neste change (KISS).

## 6. Trade-offs assumidos

| Decisão | Custo | Benefício |
|---|---|---|
| PySide6 em vez de PyQt6 | Diverge dos docs | LGPL, mais moderno, sem licença comercial |
| Smoke test só (não cobre UI) | Cobertura baixa no MVP | Feedback rápido + CI verde cedo |
| Sem `QWebEngineView` | Panel direito é só QLabel | Evita 200MB de Chromium sem necessidade |
| Sem `QFileSystemModel` | Panel esquerdo é só QLabel | Mantém change focado em infra |
| `pyproject.toml` + `requirements.txt` | Dois arquivos para manter sincronizados | Compatibilidade com `pip install -r` e ferramentas modernas |
| Sem pytest-qt | Sem fixtures `qtbot` | Menos deps, smoke test simples basta |

## 7. O que **NÃO** está neste design

- Signals/slots entre painéis (não há eventos a emitir ainda)
- Theming / dark mode / customização visual
- Internacionalização (i18n)
- Logging estruturado
- Persistência de preferências
- Sistema de plugins

Tudo isso vira changes próprios.
