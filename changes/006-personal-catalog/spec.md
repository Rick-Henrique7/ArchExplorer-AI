# Change 006 — Spec: Catálogo Pessoal de Soluções

> **O que** o usuário consegue fazer (comportamento observável).
> **Como** está no `design.md`.

---

## 1. Modelo de dados

### Tabela `entries`

| Coluna | Tipo | Nullable | Default | Notas |
|---|---|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | não | — | |
| `title` | TEXT NOT NULL | não | — | ≤ 200 chars |
| `description` | TEXT | sim | NULL | Markdown |
| `code` | TEXT NOT NULL | não | — | o snippet |
| `language` | TEXT NOT NULL | não | `'text'` | ex: `python`, `javascript`, `sql`, `bash` |
| `category` | TEXT | sim | NULL | ex: `'Performance'`, `'Security'`, `'Patterns'` |
| `origin_path` | TEXT | sim | NULL | caminho do arquivo de onde veio |
| `origin_line` | INTEGER | sim | NULL | linha do snippet |
| `is_public` | INTEGER (bool) | não | `0` | marcado pra eventual gist sync (Change 007) |
| `created_at` | TEXT NOT NULL | não | — | ISO 8601 UTC |
| `updated_at` | TEXT NOT NULL | não | — | ISO 8601 UTC |

### Tabela `tags`

| Coluna | Tipo | Nullable | Default |
|---|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | não | — |
| `name` | TEXT NOT NULL UNIQUE | não | — | lowercase, sem espaços |

### Tabela `entry_tags`

| Coluna | Tipo |
|---|---|
| `entry_id` | INTEGER NOT NULL FK → entries(id) ON DELETE CASCADE |
| `tag_id` | INTEGER NOT NULL FK → tags(id) ON DELETE CASCADE |
| | PRIMARY KEY (entry_id, tag_id) |

### Tabela virtual `entries_fts` (FTS5)

```
CREATE VIRTUAL TABLE entries_fts USING fts5(
    title, description, code,
    content='entries', content_rowid='id'
);
```

+ triggers pra manter sincronizado (`AFTER INSERT/UPDATE/DELETE` em `entries`).

### Localização do arquivo

- **Windows:** `%USERPROFILE%/Documents/ArchExplorer/catalogo.db`
- **macOS:** `~/Documents/ArchExplorer/catalogo.db`
- **Linux:** `~/Documents/ArchExplorer/catalogo.db` (ou `XDG_DOCUMENTS_DIR`)
- Criado automaticamente se não existir
- Caminho configurável via QSettings (`catalog/db_path`)

---

## 2. API do `CatalogoService`

```python
# app/services/catalogo_service.py
class CatalogoService:
    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or default_catalog_path()
        self._init_schema()  # CREATE TABLE IF NOT EXISTS, FTS5, triggers

    # CRUD
    def create_entry(self, *, title: str, description: str | None,
                     code: str, language: str, category: str | None,
                     tags: list[str], origin_path: str | None = None,
                     origin_line: int | None = None,
                     is_public: bool = False) -> Entry:
        """Cria entrada + dedup de tags (lowercase)."""

    def get_entry(self, entry_id: int) -> Entry | None: ...

    def update_entry(self, entry_id: int, **fields) -> Entry: ...
        """Atualiza campos; sincroniza FTS5 via trigger."""

    def delete_entry(self, entry_id: int) -> None: ...
        """CASCADE remove entry_tags."""

    # Busca
    def list_entries(self, *, language: str | None = None,
                     category: str | None = None,
                     tag: str | None = None,
                     limit: int = 200) -> list[Entry]: ...

    def search_entries(self, query: str, *, limit: int = 50) -> list[Entry]:
        """Busca full-text via FTS5 MATCH. Suporta prefixo: 'cache*'."""

    # Tags
    def list_tags(self) -> list[Tag]: ...

    def list_categories(self) -> list[str]: ...  # DISTINCT, ordenado

    # Import / Export
    def export_json(self) -> str: ...
    def import_json(self, payload: str) -> int: ...  # retorna qtd importadas

    # Helpers
    def stats(self) -> dict: ...  # {"total": 42, "by_language": {...}}
```

### Modelos (SQLModel — opcional, mas type-safe)

```python
# app/services/models.py
class Entry(SQLModel, table=True):
    __tablename__ = "entries"
    id: int | None = Field(default=None, primary_key=True)
    title: str
    description: str | None = None
    code: str
    language: str = "text"
    category: str | None = None
    origin_path: str | None = None
    origin_line: int | None = None
    is_public: bool = False
    created_at: datetime
    updated_at: datetime
    tags: list[Tag] = Relationship(back_populates="entries",
                                   link_model=EntryTag)
```

> **Decisão:** se SQLModel virar peso demais pra o MVP, fallback pra
> `dataclass` + `sqlite3` raw (padrão stdlib). Avalia no spike.

---

## 3. UI — Toggle

### Menu View

```
View
  ├── Theme ▶  Dark / Light / System
  ├── ───────
  ├── Painel esquerdo ▶
  │     ☑ Projeto        Ctrl+1
  │     ☐ Catálogo       Ctrl+2
  └── ───────
  └── Toggle Theme       Ctrl+Shift+T
```

### Estado

- `QSettings` chave `workspace/left_panel_mode` (`"explorer"` ou `"catalog"`)
- Carregado na inicialização da `MainWindow`
- `Ctrl+1` / `Ctrl+2` (independente do menu)

---

## 4. UI — Painel do Catálogo (modo Catálogo)

```
┌─────────────────────────────────────────┐
│ [🔍 Buscar no catálogo...]            │  ← QLineEdit (debounce 200ms)
│                                         │
│ [+ Nova] [📥 Importar] [📤 Exportar]   │  ← toolbar
│                                         │
│ ─── Filtros ─────────────────────────── │
│ Categoria:  [Todas ▼]                   │  ← QComboBox populado por categories
│ Linguagem:  [Todas ▼]                   │  ← QComboBox populado por languages
│ Tags: [python] [lru] [+]                │  ← FlowLayout com chips + add novo
│                                         │
│ ─── 42 entradas ────────────────────── │
│                                         │
│ ▣ Cache LRU com TTL                     │
│   python · performance · 2024-03-15     │
│                                         │
│ ▣ Validação CPF                         │
│   python · validation · 2023-11-02     │
│                                         │
│ ▣ JWT middleware                         │
│   javascript · security · 2024-01-08    │
│                                         │
│ ▣ SQL anti-N+1 query                    │
│   sql · performance · 2023-08-20        │
│                                         │
│ ▣ ...                                   │
│                                         │
│ [scroll area — QListView virtualizado]   │
└─────────────────────────────────────────┘
```

### Click numa entrada

- O painel central (Editor) vira **preview mode** mostrando:
  - Título (h1)
  - Metadata: linguagem, categoria, tags, datas
  - Descrição (renderiza markdown)
  - Código (com botão de copiar)
  - Origem: link pro arquivo de origem (se houver)
  - Botões: **Inserir no editor** · **Editar** · **Excluir** · **Compartilhar (futuro)**
- O Visualizer continua intacto

### Botão "Inserir no editor"

- Pega o `code` da entrada selecionada
- Pede pro `CodeEditorPanel.insert_text_at_cursor(code)`
- Se não tem arquivo aberto no editor → dialog "Onde colar?"
  - Criar novo arquivo (pergunta nome + pasta)
  - Colar em arquivo existente (selecionável via Explorer mode)
- Volta automaticamente pro modo Explorer (foco volta pro código)

---

## 5. UI — Dialog de Nova/Editar Entrada

```
┌───────────────────────────────────────────────┐
│ Nova entrada no catálogo              [X]    │
├───────────────────────────────────────────────┤
│                                               │
│ Título:        [___________________________]  │
│ Categoria:     [Performance ▼]                │
│ Linguagem:     [python ▼]                     │
│ Tags:          [python] [lru] [cache] [+]      │
│ Descrição:     [markdown editor com preview]  │
│                [tabs: [Editar] [Preview]]       │
│ Código:        [editor com syntax highlight]   │
│ Origem:        [path:linha opcional]           │
│ ☐ Marcar como público                          │
│                                               │
│              [Cancelar]    [Salvar]           │
└───────────────────────────────────────────────┘
```

- Tabs na descrição: alterna entre editar e preview (markdown renderizado)
- Code editor com syntax highlight baseado em linguagem escolhida (Pygments MVP)
- Tags como chips; "+" abre input pra digitar nova tag (autocomplete?)
- Origem é opcional; tem botão "📌 Capturar do editor" que preenche
  automaticamente com o arquivo/linha atual

---

## 6. Validação

| Campo | Regra |
|---|---|
| `title` | 1-200 chars, obrigatório |
| `code` | 1-100.000 chars, obrigatório |
| `language` | 1-30 chars, obrigatório (default: `'text'`) |
| `category` | 0-50 chars, opcional |
| `description` | 0-10.000 chars, opcional (markdown) |
| `tags` | 0-20 tags, cada uma 1-30 chars, lowercase, sem espaços |
| `origin_path` | caminho válido se preenchido, opcional |
| `origin_line` | ≥ 1 se preenchido |

---

## 7. Persistência & Migração

### Onde fica o banco

- **Padrão:** `%USERPROFILE%/Documents/ArchExplorer/catalogo.db`
- Sobrescrevível por:
  - `ARCHEXPLORER_CATALOG_DB` env var
  - `--catalog-db` CLI flag
  - QSettings `catalog/db_path` (escolha do usuário em Settings)

### Migrations

- Tabela `_migrations(version INTEGER PRIMARY KEY, applied_at TEXT)` —
  versionamento manual
- Cada migração bumpa o número e roda SQL idempotente
- MVP: 1 migration inicial (cria tudo)

---

## 8. Casos extremos

| Cenário | Comportamento |
|---|---|
| Banco corrompido | Backup automático `.bak`, cria novo |
| Disco cheio | `CatalogoError("disk full")`, mensagem amigável |
| Permissão negada | `CatalogoError("permission denied")`, sugere local alternativo |
| Tag duplicada | Dedup automático (lowercase) |
| Import JSON malformado | Mostra erros linha por linha, não importa nada |
| FTS5 indisponível | Fallback pra `LIKE '%query%'` (warning no startup) |

---

## 9. Acceptance Criteria (checklist)

- [ ] Toggle `View > Catálogo` (`Ctrl+2`) troca o painel esquerdo
- [ ] Toggle `View > Projeto` (`Ctrl+1`) volta pro Explorer
- [ ] Estado do toggle persiste entre execuções
- [ ] Banco SQLite criado em `%USERPROFILE%/Documents/ArchExplorer/catalogo.db`
- [ ] Banco é criado automaticamente se não existir
- [ ] Schema inclui tabelas `entries`, `tags`, `entry_tags`, `entries_fts` + triggers
- [ ] Botão "Nova entrada" abre dialog com todos os campos
- [ ] Validação impede salvar entrada inválida
- [ ] Tags são dedupadas (lowercase)
- [ ] Lista mostra 42+ entradas com scroll fluido (QListView virtualizado)
- [ ] Busca por texto livre (FTS5) funciona — digitar "cache" filtra
- [ ] Filtro por linguagem funciona
- [ ] Filtro por categoria funciona
- [ ] Filtro por tag funciona
- [ ] Click numa entrada mostra preview completo no centro
- [ ] Botão "Inserir no editor" cola o snippet na posição do cursor
- [ ] Botão "Editar" reabre dialog preenchido
- [ ] Botão "Excluir" pede confirmação e remove
- [ ] Export JSON cria arquivo com todas as entradas
- [ ] Import JSON lê arquivo e insere entradas (com dedup)
- [ ] Backup automático quando banco corrompido
- [ ] `pytest` ≥ 350 passing (atual: 334)
- [ ] Cobertura ≥ 85% nos módulos novos
- [ ] Docs atualizados

---

## 10. Não-objetivos (reforço)

Fora do escopo do Change 006:

- Gist sync (Change 007)
- Site estático pras públicas (Change 007)
- Markdown export com 1 arquivo `.md` por entrada (Change 007)
- Drag-and-drop de arquivo pro catálogo (Change 007)
- Syntax highlight nos snippets do catálogo (Change 008 — Pygments no preview do editor já basta)
- Templates com placeholders (Change 008)
- Links entre entradas (Change 008)
- RAG / indexação semântica (Change 008)
- `.exe` instalável (Change 009)
