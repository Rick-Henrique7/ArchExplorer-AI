O ArchExplorer AI é uma ferramenta desktop de produtividade e engenharia de software projetada para análise, visualização e geração de componentes de arquitetura de sistemas. Com uma interface estilo IDE de três painéis, a aplicação combina navegação por arquivos, edição de scripts e processamento de IA Embarcada para simplificar a documentação e o desenvolvimento de soluções Frontend e Backend.

Arquitetura do Sistema
1. Interface Gráfica (Três Colunas)
Coluna Esquerda (Explorador de Arquivos): Navegação em árvore de diretórios (QTreeView) mapeando pastas de projetos reais ou arquivos de definição de arquitetura.

Coluna Central (Editor de Código): Painel de edição de scripts (.tsx, .jsx, .py, .ts, .json, etc.) com syntax highlighting.

Coluna Direita (Painel Visual & Diagramas):

Backend: Exibe diagramas UML (Classes, Sequência, Arquitetura) gerados dinamicamente em tempo real.

Frontend (React): Exibe a árvore estrutural de componentes UI, props e estados.

2. Motor de IA Embarcada
Modelo: Qwen 2.5 Coder (executado localmente via Ollama ou llama-cpp-python).

Privacidade e Performance: Operação 100% offline, sem latência de rede e sem custo por tokens/API.

Funcionalidades Principais
Navegação Inteligente: Seleção de arquivos no explorador carrega o código no centro e aciona o motor de IA para renderizar a visualização na direita.

Geração Automática de UML (Backend): O modelo Qwen 2.5 Coder analisa scripts backend e gera sintaxe Mermaid.js/PlantUML, convertida instantaneamente em imagem no painel direito.

Inspeção de Componentes React: Mapeamento visual das dependências, subcomponentes e propriedades de arquivos React/TypeScript.

Criação de Componentes via Prompt: Criação de novos arquivos diretamente no explorador através de comandos em linguagem natural acionando a IA local.

Análise de Arquitetura: Identificação automática de acoplamentos, gargalos e sugestões de refatoração no código inspecionado.

Stack Tecnológica
Linguagem: Python 3.10+

GUI Framework: PyQt6 (utilizando QSplitter para redimensionamento flexível dos painéis)

LLM Local: Qwen 2.5 Coder (versão 3B ou 7B Quantizada)

Visual Engine: QWebEngineView ou Graphviz para renderização dos diagramas Mermaid.js/SVG