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

write_file(path: str, content: str) -> None **(Change 005)**: sobrescreve o conteúdo de um arquivo existente (UTF-8, sem BOM). Usado pelo botão **Salvar** do editor e pelo fluxo **Editar com IA → Aplicar**. Recusa criar o arquivo se o diretório pai não existir; recusa sobrescrever um diretório.

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

edit_file(content: str, instruction: str, file_type: str) -> str **(Change 005)**: Aplica uma instrução em linguagem natural ao conteúdo de um arquivo e devolve o arquivo inteiro modificado. Temperatura baixa (0.1) para edições determinísticas. Usado pelo fluxo **Editar com IA** do editor central — a MainWindow exibe um preview com diff antes de aplicar via `FileManager.write_file`.

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

Workers ativos (Change 005):

- **AnalysisWorker**: `analyze_architecture` ao clicar num arquivo do explorador.
- **AIEditWorker**: `edit_file` ao clicar em **Editar com IA**; a MainWindow recebe o resultado e exibe um `AIEditPreviewDialog` com diff unificado. Em **Aplicar**, grava via `FileManager.write_file`; em **Cancelar**, descarta.
- **ChatWorker**: prompt livre montado pelo `VisualizerPanel` (com contexto do arquivo + 5 últimos turnos). Usado pelo campo de chat da aba direita.

Os três workers usam o mesmo padrão (`_WorkerSignals(QObject)` companheiro + `QRunnable`) e fecham exceções para manter o event loop saudável.

4. Estrutura de Tratamento de Erros
FileOperationError: Lançada quando ocorrem falhas de permissão de disco ou arquivo inexistente.

AIServiceUnavailableError: Lançada quando o serviço local Ollama/Qwen não estiver respondendo na porta configurada.

DiagramParsingError: Lançada quando a resposta da IA não puder ser convertida em uma sintaxe Mermaid válida.

CatalogoError (Change 006): Lançada pelo `CatalogoService` quando uma operação no banco SQLite falha (validação, FK violation, corrupção do arquivo, import malformado).

---

## 5. Catálogo Pessoal (Change 006)

### 5.1. `CatalogoService` — SQLite raw + FTS5

Schema (em `app/services/catalog_service.py:_SCHEMA_SQL`):

```sql
CREATE TABLE entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL CHECK(length(title) BETWEEN 1 AND 200),
    description TEXT CHECK(description IS NULL OR length(description) <= 10000),
    code TEXT NOT NULL CHECK(length(code) BETWEEN 1 AND 100000),
    language TEXT NOT NULL DEFAULT 'text' CHECK(length(language) <= 30),
    category TEXT CHECK(category IS NULL OR length(category) <= 50),
    origin_path TEXT,
    origin_line INTEGER CHECK(origin_line IS NULL OR origin_line >= 1),
    is_public INTEGER NOT NULL DEFAULT 0 CHECK(is_public IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE CHECK(length(name) BETWEEN 1 AND 30)
);

CREATE TABLE entry_tags (
    entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    tag_id   INTEGER NOT NULL REFERENCES tags(id)   ON DELETE CASCADE,
    PRIMARY KEY (entry_id, tag_id)
);

CREATE VIRTUAL TABLE entries_fts USING fts5(
    title, description, code,
    content='entries', content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'
);

-- triggers keep entries_fts in sync with entries
-- (AFTER INSERT / AFTER DELETE / AFTER UPDATE)
```

### 5.2. Operações principais

- `create_entry(...)` — INSERT transacional, upsert de tags, retorna `Entry` com id.
- `update_entry(id, **fields)` — UPDATE parcial; tags substituídos quando passados.
- `delete_entry(id)` — DELETE; `entry_tags` removido via FK CASCADE.
- `get_entry(id)` — SELECT + tags; `None` se não existe.
- `list_entries(language=, category=, tag=, limit=200)` — filtros via WHERE.
- `search_entries(query, limit=50)` — FTS5 MATCH com prefixo `term*` por token; BM25 ranking.
- `list_tags() / list_categories() / list_languages() / stats()` — agregações.
- `export_json() / import_json(payload)` — serialização self-contained.

### 5.3. Decisões técnicas

- **SQLite raw (não ORM)**: schema é simples (3 tabelas + 1 FTS5), queries customizadas (FTS5 MATCH, prefixo `*`, triggers), zero dependências extras. O custo é ~200 linhas de SQL em vez de abstrações mágicas.
- **FTS5 (não LIKE)**: ~100× mais rápido em catálogos com 10k+ entries; ranking BM25 nativo.
- **Tags normalizadas**: `normalize_tags()` faz lowercase, strip, dedup case-insensitive, max 20, regex `^[a-z0-9_.-]{1,30}$`. Espaços e uppercase são silenciosamente descartados (sem erro).
- **`Cursor.lastrowid` é sticky** após `INSERT OR IGNORE` — sempre re-SELECT pelo nome depois de upsert.
- **Backup `*.bak` automático** quando `_init_schema` detecta corrupção: renomeia o `.db` existente para `.db.bak` e segue com DB novo.
- **Default location**: `~/Documents/ArchExplorer/catalogo.db` (criado no primeiro run); override por `ARCHEXPLORER_CATALOG_DB` (env), `--catalog-db` (CLI) ou `catalog/db_path` (QSettings). Precedência: CLI > env > QSettings > default.

### 5.4. Modelos (`app/services/models.py`)

`Entry` e `Tag` são `@dataclass(frozen=True)`. `Entry.tags` é `tuple[str, ...]` (não lista) para garantir hashabilidade e imutabilidade. `Entry.to_dict/from_dict` permitem round-trip via JSON.

### 5.5. Exceções

`CatalogoError(message, **context)` é a única exceção custom do catálogo. Carrega contexto (entry_id, payload_keys, errors list, cause, etc.) e é capturada na UI para mostrar `QMessageBox.warning`.