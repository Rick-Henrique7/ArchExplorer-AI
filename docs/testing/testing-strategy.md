# Estratégia de Testes e Qualidade de Código

Este documento especifica a estratégia de testes automatizados para garantir a robustez, modularidade (SOLID) e estabilidade do ArchExplorer AI.

---

## 1. Arquitetura de Testes (`pytest`)

A suíte de testes é organizada de forma espelhada à estrutura do código-fonte em `app/`:

```text
tests/
├── unit/
│   ├── test_file_manager.py        # Operações de disco e clipboard (write_file*)
│   ├── test_ai_engine.py           # Mocks da comunicação HTTP/Ollama (edit_file*)
│   ├── test_diagram_generator.py   # Parsing de blocos Mermaid.js
│   ├── test_chat_history.py        # **Change 005** — ChatTurn, LRU, prompt
│   ├── test_editor_save_undo.py    # **Change 005** — Save / Edit com IA
│   ├── test_explorer_toolbar.py    # **Change 005** — Select/+Folder/Refresh
│   └── test_visualizer_themes.py   # Inclui teste do spinner (Bloco C)
├── integration/
│   ├── test_ui_flow.py             # file click → AI → visualizer
│   ├── test_chat_sends_message.py  # **Change 005** — input → worker → history
│   ├── test_editor_save_writes_file.py   # **Change 005** — save end-to-end
│   ├── test_ai_edit_preview_apply.py     # **Change 005** — preview/apply
│   ├── test_new_folder_input_flow.py     # **Change 005** — +Folder flow
│   └── test_select_folder_persists.py    # **Change 005** — QSettings roundtrip
└── conftest.py                     # Fixtures compartilhadas (qapp, tmp_path)
2. Tipos de Teste e Mocks
2.1. Testes Unitários de Arquivo (test_file_manager.py)
Isolamento: Uso estrito da fixture tmp_path do pytest para evitar manipulação de arquivos reais do sistema durante os testes.

Cenários:

Validação de criação, movimentação e remoção de pastas e arquivos.

Validação de colisão de nomes e exceções de permissão (FileOperationError).

Comportamento do fluxo Copiar/Recortar/Colar (preservação do estado no clipboard).

2.2. Testes da Engine de IA (test_ai_engine.py)
Mocks: Uso de unittest.mock ou requests-mock para simular as respostas da API local do Ollama (http://localhost:11434).

Injeção de Dependência: Teste do contrato IAIProvider trocando a implementação concreta pelo MockAIProvider.

Cenários:

Retorno com sucesso de código gerado.

Tratamento do erro AIServiceUnavailableError quando o Ollama está offline.

2.3. Testes do Gerador de Diagramas (test_diagram_generator.py)
Cenários:

Sanitização de respostas brutas da IA contendo marcações Markdown (ex: extrair apenas o conteúdo dentro de ````mermaid`).

Tratamento de respostas malformatadas com a exceção DiagramParsingError.

2.4. Testes de UI — Padrões Específicos (Change 005)

**Worker signals cross-thread**: `QRunnable` emite `finished(str)` num thread pool; o slot roda na main thread. **Importante** — PySide6 tem um bug sutil com `lambda response, um=user_msg: ...` em conexões cross-thread: a closure com default-arg não recebe a chamada. **Sempre use bound methods** (`self._handle_chat_response`) ou armazene o estado no próprio worker.

**QSettings em testes**: a fixture `qapp` define `setOrganizationName("ArchExplorer-Test")` / `setApplicationName("ArchExplorer-AI-Test")` para que `QSettings()` dentro da `MainWindow` aponte para um local estável. Testes que precisem de isolamento total instanciam `QSettings(str(tmp_path / "x.ini"), QSettings.Format.IniFormat)`.

**Spinner / HTML inline**: a presença de elementos específicos do template (ex: `@keyframes`, `<svg>` no `_LOADING_HTML_TEMPLATE`) é testada lendo o atributo de classe (`VisualizerPanel._LOADING_HTML_TEMPLATE`) — `QWebEngineView` é difícil de introspectar no teste.

**Refresh do `QFileSystemModel`**: o `QFileSystemModel` do PySide6 **não expõe** `refresh()` (apesar de existir em C++). Workaround usado no `FileExplorerPanel._on_refresh()`: re-aplicar `setRootPath(root)` + `view.setRootIndex(model.index(root))`.

3. Execução dos Testes
Bash
# Executar todos os testes
pytest

# Executar apenas testes unitários com cobertura
pytest tests/unit/ --cov=app

---

### `docs/setup-and-deployment.md`

```markdown
# Guia de Configuração e Execução Local

Este documento orienta o setup do ambiente de desenvolvimento do ArchExplorer AI.

---

## 1. Pré-requisitos

* **Python 3.10+**
* **Ollama** (para execução local do modelo `Qwen 2.5 Coder 3B`)

---

## 2. Configuração do Modelo de IA (Ollama)

1. Instale o Ollama em sua máquina: [ollama.com](https://ollama.com)
2. Baixe e execute o modelo **Qwen 2.5 Coder (3B)**:

```bash
ollama pull qwen2.5-coder:3b
Verifique se o servidor do Ollama está rodando na porta padrão:

Bash
curl http://localhost:11434
3. Instalação do Projeto Python
Clone o repositório e acesse a pasta raiz:

Bash
git clone https://github.com/usuario/arch-explorer-ai.git
cd arch-explorer-ai
Crie e ative um ambiente virtual (venv):

Bash
python -m venv venv
# Linux/macOS:
source venv/bin/activate
# Windows:
venv\Scripts\activate
Instale as dependências:

Bash
pip install -r requirements.txt
4. Execução da Aplicação
Para iniciar a interface desktop PyQt6:

Bash
python -m app.main