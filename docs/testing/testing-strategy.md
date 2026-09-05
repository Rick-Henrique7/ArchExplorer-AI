# Estratégia de Testes e Qualidade de Código

Este documento especifica a estratégia de testes automatizados para garantir a robustez, modularidade (SOLID) e estabilidade do ArchExplorer AI.

---

## 1. Arquitetura de Testes (`pytest`)

A suíte de testes é organizada de forma espelhada à estrutura do código-fonte em `app/`:

```text
tests/
├── unit/
│   ├── test_file_manager.py     # Operações de disco e clipboard
│   ├── test_ai_engine.py        # Mocks da comunicação HTTP/Ollama
│   └── test_diagram_generator.py# Parsing de blocos Mermaid.js
├── integration/
│   └── test_file_ai_flow.py     # Integração entre leitura de arquivo e pipeline de IA
└── conftest.py                  # Fixtures compartilhadas (tmp_path, Mocks de IA)
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