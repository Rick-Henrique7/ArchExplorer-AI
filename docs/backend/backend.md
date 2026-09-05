# Especificação do Backend e Serviços Internos

Este documento detalha a arquitetura lógica do backend, gerenciamento de I/O, threads e integração com o motor de IA local para o ArchExplorer AI.

---

## 1. Visão Geral da Arquitetura do Backend

O backend é executado de forma embutida na aplicação Python, desacoplado da camada de apresentação (PyQt6). Toda operação assíncrona ou custosa (I/O de disco e inferência do LLM) é gerenciada via **Worker Threads** (`QThread` / `QThreadPool`) para manter a interface gráfica fluida e sem congelamentos.

```text
[ PyQt6 UI ]
     │
     ├── (Dispara Evento)
     ▼
[ Controller / Event Handler ]
     │
     ├── (Executa em Background Thread via QThread)
     ▼
┌──────────────────────────────────────────────────────────┐
│                   BACKEND SERVICES                       │
│                                                          │
│  ┌────────────────┐  ┌───────────────┐  ┌─────────────┐  │
│  │  FileManager   │  │  AIEngine     │  │ DiagramGen  │  │
│  └───────┬────────┘  └───────┬───────┘  └──────┬──────┘  │
└──────────┼───────────────────┼─────────────────┼─────────┘
           │                   │                 │
           ▼                   ▼                 ▼
     [ Sistema I/O ]    [ Qwen 2.5 (3B) ]  [ Mermaid.js ]
2. Componentes e Módulos Principais
2.1. File Manager (services/file_manager.py)
Responsável pela abstração e execução segura de operações no sistema de arquivos local.

Interface / Métodos Principais:

list_directory(path: str) -> List[FileItem]: Mapeia a estrutura de arquivos e pastas.

create_folder(target_dir: str, name: str) -> bool: Cria novo diretório.

create_file(target_dir: str, name: str, content: str = "") -> bool: Cria novo arquivo.

copy_item(source_path: str, destination_dir: str) -> str: Copia arquivo/pasta.

move_item(source_path: str, destination_dir: str) -> str: Recorta/move arquivo ou pasta.

delete_item(path: str) -> bool: Remove item do disco.

Mecanismo de Clipboard Interno:

Mantém o estado da operação ativa (COPY ou CUT) e o caminho de origem até a confirmação da colagem (paste).

2.2. AI Engine & Provider (services/ai_engine.py)
Gerencia a comunicação local com o modelo Qwen 2.5-Coder (3B).

Contrato IAIProvider:

Define a interface abstrata para permitir a troca do backend da IA sem alterar o restante da aplicação.

Implementação OllamaProvider:

Comunica-se com a instância local do Ollama (http://localhost:11434/api/generate) via requisições HTTP REST assíncronas.

Pipelines de Prompting:

generate_component(prompt: str, context_path: str) -> str: Gera código de novos componentes React ou Backend com base na instrução do usuário.

analyze_architecture(code_content: str, file_type: str) -> str: Examina o arquivo ativo em busca de acoplamento, vazamento de responsabilidade e violações de padrões de projeto.

extract_uml_structure(code_content: str) -> str: Processa o código Backend e retorna estritamente a sintaxe Mermaid.js correspondente.

2.3. Diagram Generator (services/diagram_generator.py)
Converte as saídas de análise e o código do usuário em especificações de diagramas de arquitetura e UML.

Responsabilidades:

Sanitizar a saída textual da IA, extraindo apenas blocos de código mermaid ... .

Validar a sintaxe do diagrama gerado (Classes, Sequência, Componentes) antes do envio para renderização no frontend.

Construir o template HTML minimalista que carrega a biblioteca Mermaid.js para exibição dentro do QWebEngineView.

3. Estratégia de Concorrência e Threads
Para evitar bloqueios na UI durante a geração de código ou leitura de diretórios pesados:

WorkerThread (Base): Herda de QThread ou usa QRunnable com sinais (pyqtSignal) para notificar a UI sobre status (started, finished, error).

Fluxo de Requisição de IA:

Usuário solicita geração ou análise.

A UI exibe indicador de carregamento e dispara um AIWorker em background.

Ao finalizar, o sinal finished(result) envia a resposta para atualizar o editor e o renderizador na thread principal da UI.

4. Estrutura de Tratamento de Erros
FileOperationError: Lançada quando ocorrem falhas de permissão de disco ou arquivo inexistente.

AIServiceUnavailableError: Lançada quando o serviço local Ollama/Qwen não estiver respondendo na porta configurada.

DiagramParsingError: Lançada quando a resposta da IA não puder ser convertida em uma sintaxe Mermaid válida.