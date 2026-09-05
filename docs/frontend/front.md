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