Detalhamento do Frontend (PyQt6 Desktop)
A interface precisa comportar as ações locais de manipulação de arquivos e a exibição em três colunas com painéis ajustáveis (QSplitter).

Componentes Visuais:

Painel Esquerdo (Explorador): QTreeView integrado a um QFileSystemModel.

Exibe pastas e arquivos locais em tempo real.

Suporta menu de contexto (clique direito) com opções do sistema de arquivos e comandos de IA.

Painel Central (Editor/Script): QTextEdit ou QPlainTextEdit.

Exibe o código do arquivo selecionado.

Conta com destaque de sintaxe (Syntax Highlighting) para Python, React/TSX e JSON.

Painel Direito (Renderizador): QWebEngineView (para renderizar diagramas gerados em HTML/Mermaid.js) ou QLabel (para imagens PNG/SVG).

Mecanismos de Sistema de Arquivos (Copiar, Recortar, Colar e Criar Pasta):

Ações Nativas: Mapeadas via atalhos de teclado (Ctrl+C, Ctrl+X, Ctrl+V, Delete, F2 para renomear).

Menu de Contexto (Clique Direito):

Nova Pasta... (Abre caixa de diálogo QInputDialog para nomear).

Novo Arquivo...

Criar Componente com IA... (Abre prompt do Qwen 2.5).

Copiar / Recortar / Colar (Gerenciado pela área de transferência do sistema via QClipboard ou funções shutil/os em Python).

Estrutura de Diretórios do Projeto (Código Fonte)
Plaintext
arch-explorer-ai/
├── app/
│   ├── __init__.py
│   ├── main.py                   # Ponto de entrada da aplicação PyQt6
│   ├── ui/                       # Componentes visuais da interface
│   │   ├── __init__.py
│   │   ├── main_window.py        # Janela principal com QSplitter (3 colunas)
│   │   ├── file_explorer.py      # Painel esquerdo (QTreeView + Menus)
│   │   ├── code_editor.py        # Painel central (Editor de código)
│   │   └── visualizer.py        # Painel direito (Mermaid/React Renderer)
│   ├── services/                 # Regras de negócio e integrações
│   │   ├── __init__.py
│   │   ├── ai_engine.py          # Cliente local para o Qwen 2.5-Coder (3B)
│   │   ├── file_manager.py       # Operações de sistema de arquivos (copy, move, mkdir)
│   │   └── diagram_generator.py # Conversor de código backend/UML para Mermaid.js
│   └── utils/
│       └── syntax_highlighter.py # Destaque de sintaxe para o editor
├── tests/                        # Suíte de testes automatizados
│   ├── test_file_manager.py
│   ├── test_ai_engine.py
│   └── test_diagram_generator.py
├── requirements.txt
└── README.md
Estrutura de Testes Automatizados
Sim, a criação de testes é fundamental, principalmente para garantir que as operações no disco e o parsing dos dados da IA funcionem sem corromper arquivos do usuário.

Escopo dos Testes (pytest):

Testes de Manipulação de Arquivos (test_file_manager.py):

Validação de criação, cópia, movimentação e exclusão de pastas/arquivos usando diretórios temporários (pytest-mock e tmp_path).

Garantia de que ações de recortar/colar não perdem dados.

Testes do Motor de IA (test_ai_engine.py):

Mock da resposta do modelo Qwen 2.5 (3B) para testar a integração sem depender da execução do modelo durante a suíte de testes rápidos.

Validação do parsing de saída do modelo (garantir que ele extraia blocos de código e sintaxe Mermaid corretamente).

Testes de Gerador de Diagramas (test_diagram_generator.py):

Testar a conversão de um script Python backend simples em uma string de sintaxe Mermaid válida.

# Especificação do Frontend e Interface Gráfica

Este documento detalha os componentes visuais, o fluxo de interação do usuário e a sincronização de estados entre as três colunas da aplicação desktop.

---

## 1. Estrutura de Layout da Janela Principal (`MainWindow`)

A interface é construída usando `PyQt6` com um `QSplitter` horizontal composto por três painéis redimensionáveis:

```text
+---------------------+-----------------------+-----------------------+
|  Col. 1: Explorador  |    Col. 2: Editor     |   Col. 3: Diagrama    |
|   (FileExplorer)    |     (CodeEditor)      |     (Visualizer)      |
|                     |                       |                       |
| 📂 App/             | class UserService:    |  +-----------------+  |
|  📂 Services/       |   def get_user():     |  |   UserService   |  |
|   📄 UserService.py |     ...               |  +--------+--------+  |
|                     |                       |           |           |
+---------------------+-----------------------+-----------------------+
2. Componentes e Responsabilidades Visuais
2.1. Painel Esquerdo: Explorador de Arquivos (ui/file_explorer.py)
Componentes: QTreeView conectado a um QFileSystemModel.

Interações:

Clique simples/Seleção: Carrega o conteúdo do arquivo no painel central e aciona a geração do diagrama no painel direito.

Atalhos de Teclado: Ctrl+C (copiar), Ctrl+X (recortar), Ctrl+V (colar), Del (deletar), F2 (renomear).

Menu de Contexto (Clique Direito):

Novo Arquivo / Nova Pasta

Copiar / Recortar / Colar

✨ Criar Componente com IA... (abre caixa de diálogo para prompt)

🔍 Analisar Arquitetura com IA

2.2. Painel Central: Editor de Código (ui/code_editor.py)
Componentes: QPlainTextEdit com regras personalizadas de QSyntaxHighlighter.

Funcionalidades:

Destaque de sintaxe para Python, TypeScript/React (.tsx, .jsx) e JSON.

Suporte a salvamento automático ou via Ctrl+S.

Números de linha no painel lateral esquerdo do editor.

2.3. Painel Direito: Renderizador de Diagramas e UI (ui/visualizer.py)
Componentes: QWebEngineView para renderização web local de Mermaid.js / SVG.

Comportamento por Tipo de Arquivo:

Backend (.py, .ts, .java): Exibe diagramas de classe/sequência em Mermaid.js gerados em tempo real pela IA.

Frontend (.tsx, .jsx): Exibe a árvore de componentes React, props mapeadas e dependências do módulo.

Estado de Carregamento: Exibe um spinner/indicador visual durante a inferência do Qwen 2.5-Coder.

3. Gerenciamento de Estado e Sincronização
A sincronização entre os painéis é gerenciada por Sinais e Slots nativos do PyQt6 (pyqtSignal):

file_selected(file_path: str): Emitido pelo FileExplorer -> Notifica CodeEditor (para ler o arquivo) e Visualizer (para acionar o backend da IA).

code_changed(content: str): Emitido pelo CodeEditor -> Atualiza o modelo em memória e revalida o diagrama com delay de digitação (debounce).

diagram_ready(html_content: str): Emitido pelo serviço em background -> Atualiza o HTML do QWebEngineView.

---

## 4. Recursos Interativos (Change 005)

Esta seção documenta os recursos adicionados na **Change 005 — Interactive features**.

### 4.1. Chat com a IA no Painel Direito

O `VisualizerPanel` agora tem uma caixa de texto multi-linha no rodapé
que permite ao usuário conversar com a IA sobre o arquivo carregado.

**Layout:**

```text
+-----------------------------------+
| Render area (markdown / spinner) |
| ...                               |
+-----------------------------------+
| [History ▾]              [Clear]  |  ← histórico (até 50 turns)
+-----------------------------------+
| > Ask about this file...          |  ← input multi-linha
| (Enter = enviar, Shift+Enter = \n) |
+-----------------------------------+
|                         [Send →]   |
+-----------------------------------+
```

**Comportamento:**

- Enter envia a mensagem; Shift+Enter insere nova linha
- Cada turno (user, ai) é salvo em `chat_history` (LRU, max 50)
- O `QComboBox` no topo permite re-renderizar respostas anteriores
- "Clear" reseta o histórico e volta ao estado idle
- O prompt enviado para a IA inclui o caminho do arquivo e o conteúdo
  do arquivo carregado como contexto

### 4.2. Animação de Loading (Spinner)

O placeholder estático "Analyzing..." é substituído por um **spinner SVG**
animado por CSS `@keyframes spin` (1.2s, linear, infinite). Renderizado
inline no HTML da página do visualizer — zero dependência extra.

```svg
<svg viewBox="0 0 50 50" width="48" height="48" class="spinner">
  <circle cx="25" cy="25" r="20" fill="none" stroke="#888"
          stroke-width="4" stroke-linecap="round" stroke-dasharray="80 200" />
</svg>
```

A cor do círculo (`stroke`) acompanha o tema ativo (gray para dark/light).
Aparece imediatamente quando `show_loading()` é chamado e some quando
`show_markdown()` ou `show_error()` é invocado.

### 4.3. Editor Central: Save, Undo/Redo, e "Edit with AI"

O `CodeEditorPanel` deixou de ser read-only. Agora é totalmente editável,
com uma toolbar no topo e 3 recursos:

**Toolbar:**

```text
+--------------------------------------------+
| [Save]                [Edit with AI ▾]   |
+--------------------------------------------+
|                                            |
|  QPlainTextEdit (editável, monospace)      |
|  ...                                       |
+--------------------------------------------+
```

**Save (Ctrl+S):**

- Escreve o conteúdo do editor de volta ao arquivo no disco via
  `FileManager.write_file(path, content)`
- Sucesso: botão "Save" desabilita, status bar mostra "Saved at HH:MM:SS"
- Erro: emite `save_failed(str)` que o `MainWindow` roteia para o
  `visualizer.show_error`

**Undo/Redo:**

- Nativos do `QPlainTextEdit` (`Ctrl+Z`, `Ctrl+Y`)
- Marcador `*` no título quando há mudanças não salvas
- `document().modificationChanged` controla habilitação do botão Save

**Edit with AI (com autorização):**

1. Click → `QInputDialog.getText` pede instrução (ex: "Add type hints")
2. Confirmação → dispara `AIEngine.edit_file(content, instruction)`
3. Worker roda em background (spinner)
4. Resultado aparece em dialog de preview:
   - Mostra o novo conteúdo completo (sem diff colorido nesta versão)
   - Botões **Apply** / **Cancel**
5. Apply: `FileManager.write_file` + atualiza o editor
6. Cancel: descarta

A IA **nunca** edita o arquivo sem confirmação explícita do usuário.

### 4.4. Toolbar do FileExplorer (Select/New/Refresh)

O `FileExplorerPanel` ganha uma toolbar horizontal acima do tree com 3 ações:

**Select Folder (Ctrl+O):**

- Abre `QFileDialog.getExistingDirectory`
- Troca a raiz do tree (`QFileSystemModel.setRootPath`)
- Persiste em `QSettings` (key `root_dir`)
- Próxima execução do app abre direto na pasta escolhida

**+ New Folder (Ctrl+Shift+N):**

- Click → input inline (`QLineEdit`) aparece abaixo da toolbar
- Usuário digita o nome + Enter → `FileManager.create_folder(root, name)`
- Esc ou click fora → fecha input sem criar
- Sucesso: tree atualiza (`QFileSystemModel.refresh`)
- Erro (nome duplicado, sem permissão): `QMessageBox.warning`

**Refresh (F5):**

- `QFileSystemModel.refresh()` — re-escaneia o disco
- Útil quando arquivos mudam externamente (git pull, etc.)

### 4.5. Persistência da Raiz do Tree

A primeira ação do app ao abrir é ler a pasta raiz de `QSettings`:

```python
from PySide6.QtCore import QSettings
settings = QSettings()  # usa QApplication.organizationName() + applicationName()
saved_root = settings.value("root_dir", str(Path(os.getcwd())), type=str)
```

Default: `os.getcwd()` se nunca foi setado. Se a pasta não existir mais
(foi deletada), o app faz fallback para `cwd` e atualiza a setting.

### 4.6. Polish Visual (QSS)

- **Pastas visíveis no tema light**: o `QTreeView::branch` antes era
  `background-color: transparent` (invisível sobre fundo claro). Agora é
  `#e8e8e8` em light theme — contraste ≥ 3:1 com o bg do tree.
- **Padding interno**: `QTreeView` e `QPlainTextEdit` ganham
  `padding: 4px` no QSS, melhorando a legibilidade.

---

## 5. Estado dos Sinais (resumo consolidado)

| Origem | Signal | Payload | Conectado em |
|---|---|---|---|
| FileExplorerPanel | `file_selected` | `str` (path) | MainWindow → editor + visualizer |
| CodeEditorPanel | `save_failed` | `str` (erro) | MainWindow → visualizer.show_error |
| CodeEditorPanel | `ai_edit_requested` | `str, str` (path, instrução) | MainWindow → AIEditWorker |
| VisualizerPanel | `chat_send_requested` | `str` (msg) | MainWindow → ChatWorker |
| AIWorker | `finished` | `str` (markdown) | visualizer.show_markdown |
| AIWorker | `failed` | `str` (erro) | visualizer.show_error |

## 6. Atalhos de Teclado (consolidados)

| Atalho | Ação | Onde |
|---|---|---|
| `Ctrl+S` | Save | CodeEditorPanel |
| `Ctrl+Z` / `Ctrl+Y` | Undo / Redo | CodeEditorPanel (nativo) |
| `Ctrl+O` | Select Folder | FileExplorerPanel |
| `Ctrl+Shift+N` | New Folder | FileExplorerPanel |
| `F5` | Refresh | FileExplorerPanel |
| `Ctrl+Shift+T` | Toggle theme | MainWindow (do Change 004) |
| `Enter` (no chat) | Send message | VisualizerPanel |