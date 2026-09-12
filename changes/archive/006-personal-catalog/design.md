# Change 006 — Design: Catálogo Pessoal de Soluções

> **Como** implementamos o que está no `spec.md`.
> Decisões, alternativas rejeitadas, diagramas de fluxo.

---

## 1. Stack escolhida

| Camada | Tecnologia | Por quê |
|---|---|---|
| Banco | **SQLite** via stdlib `sqlite3` | Sem dependência, FTS5 built-in |
| ORM | **`sqlite3` raw** (sem ORM) | Schema simples, controle total do SQL, performance |
| Full-text | **FTS5** (módulo do SQLite) | Built-in, índice invertido, BM25 |
| Models | **`@dataclass(frozen=True)`** | Imutáveis, type-safe, sem dependência |
| UI panel | **`QStackedWidget`** | Alterna Explorer ↔ Catálogo sem rebuild |
| Lista virtualizada | **`QListView`** + `QAbstractListModel` | Performance com 10k+ entries |
| Tags chips | **`FlowLayout`** (do Qt examples) | Wrap automático, sem dep |
| Markdown editor | **`QPlainTextEdit`** + tabs | Já temos o pattern no chat |
| Markdown preview | **Mesmo `build_html_template` do Visualizer** | Reuso |
| Markdown export | **Stdlib** (`string.Template`) | Sem dep |
| Syntax highlight | **MVP: nenhum; v2: Pygments** | Pygments é dep nova, deferir |
| Testes | **pytest + sqlite3 in-memory (`:memory:`)** | Rápido, isolado |

---

## 2. Decisões-chave

### Decisão 1: SQLite raw (sem SQLAlchemy / SQLModel)

**Por quê:** O schema é simples (3 tabelas + 1 virtual). Usar um ORM
adianta pouco e adiciona uma dependência pesada pra um app que
promete ser leve.

**Trade-off aceito:** queries manuais em SQL string (mais
propenso a typo), validação de schema manual.

**Mitigação:** testes de integração com `:memory:` SQLite pegam
typos de SQL rapidamente.

### Decisão 2: FTS5 (e não LIKE)

**Por quê:** LIKE `%query%` faz scan completo da tabela. FTS5 tem
índice invertido + BM25 — busca em 10k entradas cai de ~100ms
(LIKE) pra ~1ms.

**Trade-off aceito:** schema mais complexo (tabela virtual + triggers).

**Mitigação:** FTS5 é parte do SQLite desde 3.9 (2015) — não precisa
instalar nada. Fallback automático pra LIKE se FTS5 não estiver
disponível (versão antiga do SQLite, improvável).

### Decisão 3: `@dataclass(frozen=True)` (e não Pydantic / SQLModel)

**Por quê:** Validação fica no `CatalogoService.create_entry()` (raise
`ValueError` com mensagens claras). Dataclass imutável impede mutação
acidental. Sem dependência.

**Trade-off aceito:** sem `entry.dict()` ou serialização automática.

**Mitigação:** métodos `to_dict()` / `from_dict()` explícitos nos
dataclasses.

### Decisão 4: Toggle via `QStackedWidget` (e não 2 widgets em `hide()/show()`)

**Por quê:** QStackedWidget só renderiza o widget visível, mantém o
outro "vivo" (estado preservado). `hide()/show()` no Explorer
destruiria a expansão da árvore quando voltasse.

**Trade-off aceito:** 2 instâncias de FileExplorerPanel/CatalogoPanel
em memória simultaneamente (~5 MB cada).

**Mitigação:** aceitável — é um desktop app, não mobile.

### Decisão 5: Toggle no menu View (e não toolbar)

**Por quê:** VS Code / IntelliJ fazem assim. Menu View já existe
(theme switcher), coerente adicionar lá.

**Trade-off aceito:** 1 click a mais pra acessar (vs botão na toolbar).

**Mitigação:** atalhos `Ctrl+1` / `Ctrl+2` na mesma ação.

### Decisão 6: Banco em `%USERPROFILE%/Documents/ArchExplorer/`

**Por quê:**
- **Documents** é o local padrão pra documentos do usuário
  (vs `%APPDATA%` que é escondido)
- Fácil de achar e fazer backup manual
- Multi-OS (Windows/Mac/Linux têm equivalents)
- **Não** em `%APPDATA%` porque o usuário não sabe que existe

**Trade-off aceito:** backup manual é responsabilidade do usuário
(não tem auto-backup no MVP).

**Mitigação:** doc no README + botão "Exportar JSON" sempre
disponível.

### Decisão 7: Sem drag-and-drop no MVP

**Por quê:** drag-and-drop com QListWidget + treeview é fiddly
(implementar `dragEnterEvent`, `dragMoveEvent`, `dropEvent`,
`mimeData`). Pra MVP, é overkill.

**Deferido para:** Change 007.

### Decisão 8: Sem syntax highlight no preview do código (MVP)

**Por quê:** Adicionar Pygments é +1 dep. Pygments roda só no
thread da UI (não async), então uma entrada com 5k linhas trava
o app.

**Deferido para:** Change 008, com cache de Pygments por hash
do código.

---

## 3. Diagrama de classes

```
┌─────────────────────────────────────────────────────────┐
│                  app.services                           │
│                                                         │
│  ┌──────────────┐  ┌────────────────────────┐           │
│  │ models.py    │  │ catalogo_service.py    │           │
│  │              │  │                        │           │
│  │ Entry        │◀─│ create_entry()         │           │
│  │ Tag          │  │ get_entry()            │           │
│  │ EntryTag     │  │ update_entry()         │           │
│  │ (dataclass)  │  │ delete_entry()         │           │
│  │              │  │ list_entries()         │           │
│  │              │  │ search_entries()       │           │
│  │              │  │ list_tags()            │           │
│  │              │  │ list_categories()      │           │
│  │              │  │ export_json()          │           │
│  │              │  │ import_json()          │           │
│  │              │  │ stats()                │           │
│  └──────────────┘  └────────────────────────┘           │
│                          │                              │
│                          ▼                              │
│                   ┌──────────────┐                      │
│                   │ exceptions.py│                      │
│                   │ CatalogoError│                      │
│                   └──────────────┘                      │
└─────────────────────────────────────────────────────────┘
                              ▲
                              │
┌─────────────────────────────────────────────────────────┐
│                  app.ui                                  │
│                                                         │
│  ┌────────────────────────────────────────────┐        │
│  │ left_panel.py                              │        │
│  │                                            │        │
│  │ QStackedWidget                             │        │
│  │  ├─ [0] FileExplorerPanel (existente)      │        │
│  │  └─ [1] CatalogoPanel (novo)              │        │
│  └────────────────────────────────────────────┘        │
│       ▲                                                 │
│       │ show_explorer() / show_catalog()                 │
│       │                                                 │
│  ┌────────────────────────────────────────────┐        │
│  │ catalogo_panel.py                          │        │
│  │                                            │        │
│  │ QListView + QAbstractListModel             │        │
│  │  ├─ QLineEdit (busca)                      │        │
│  │  ├─ QToolBar (+Nova, Importar, Exportar)   │        │
│  │  ├─ QComboBox (categoria, linguagem)       │        │
│  │  ├─ FlowLayout (tags chips)                 │        │
│  │  └─ QListView (lista virtualizada)          │        │
│  │                                            │        │
│  │ signals:                                    │        │
│  │  - entry_selected(int)                     │        │
│  │  - insert_into_editor_requested(int)       │        │
│  │  - new_entry_requested()                   │        │
│  └────────────────────────────────────────────┘        │
│       ▲                                                 │
│       │ show_entry_preview(entry_id)                    │
│       │                                                 │
│  ┌────────────────────────────────────────────┐        │
│  │ entry_editor_dialog.py                     │        │
│  │                                            │        │
│  │ QDialog com:                                │        │
│  │  - QLineEdit (título)                       │        │
│  │  - QComboBox (categoria, linguagem)         │        │
│  │  - TagEditor widget                         │        │
│  │  - QTabWidget (descrição: edit + preview)    │        │
│  │  - CodeEditor (QPlainTextEdit)              │        │
│  │  - Origem picker                            │        │
│  │  - Checkbox (público)                       │        │
│  └────────────────────────────────────────────┘        │
│                                                         │
│  ┌────────────────────────────────────────────┐        │
│  │ entry_preview_panel.py                     │        │
│  │  (mostra a entrada selecionada no centro    │        │
│  │   quando modo Catálogo está ativo)          │        │
│  └────────────────────────────────────────────┘        │
│                                                         │
│  ┌────────────────────────────────────────────┐        │
│  │ code_editor.py (modificado)                │        │
│  │  + insert_text_at_cursor(text)             │        │
│  └────────────────────────────────────────────┘        │
│                                                         │
│  ┌────────────────────────────────────────────┐        │
│  │ main_window.py (modificado)                │        │
│  │  + action "Catálogo" no menu View           │        │
│  │  + atalhos Ctrl+1 / Ctrl+2                  │        │
│  │  + splitter usa LeftPanel em vez de         │        │
│  │    FileExplorerPanel direto                │        │
│  └────────────────────────────────────────────┘        │
└─────────────────────────────────────────────────────────┘
```

---

## 4. Diagrama de sequência — fluxo principal

### Fluxo: Toggle Explorer ↔ Catálogo

```
User press Ctrl+2
  │
  ▼
MainWindow.on_toggle_catalog()
  │
  ├─▶ self._left_panel.show_catalog()       # QStackedWidget → index 1
  ├─▶ self._mode_action_group.checked = "catalog"
  ├─▶ QSettings["workspace/left_panel_mode"] = "catalog"
  │
  └─▶ self._catalog_panel.refresh()         # rebusca do banco
```

### Fluxo: Salvar nova entrada

```
User clica [+ Nova] no CatalogoPanel
  │
  ▼
CatalogoPanel._on_new_entry_clicked()
  │
  ├─▶ EntryEditorDialog(parent=self).exec()
  │     │
  │     ▼
  │   EntryEditorDialog (QDialog):
  │     ├─ collect data do form
  │     ├─ validate (raise ValidationError)
  │     └─ return EntryDraft dataclass
  │
  ├─▶ CatalogoService.create_entry(**draft)
  │     │
  │     ▼
  │   CatalogoService:
  │     ├─ dedup tags (lowercase, strip)
  │     ├─ BEGIN TRANSACTION
  │     ├─ INSERT INTO entries (...)
  │     ├─ INSERT INTO tags (ON CONFLICT DO NOTHING) -- pra cada tag
  │     ├─ INSERT INTO entry_tags (...) -- pra cada tag
  │     ├─ COMMIT
  │     └─ trigger atualiza entries_fts automaticamente
  │
  ├─▶ model.refresh()                       # QListView rebinda
  └─▶ status bar: "Entrada 'X' salva"
```

### Fluxo: Buscar e inserir

```
User digita "cache" no QLineEdit (com debounce 200ms)
  │
  ▼
CatalogoPanel._on_search_changed(query)
  │
  ├─▶ if len(query) >= 2:
  │     └─▶ CatalogoService.search_entries(query)
  │           └─▶ SQL: SELECT ... FROM entries e JOIN entries_fts ...
  │                 WHERE entries_fts MATCH 'cache*'
  │
  └─▶ model.set_entries(results)
       └─▶ QListView rebinda (apenas itens visíveis)

User clica [Inserir no editor] no preview
  │
  ▼
EntryPreviewPanel._on_insert_clicked()
  │
  ├─▶ code = self._entry.code
  └─▶ MainWindow.on_insert_catalog_entry(code)
        │
        ├─▶ self._code_editor.insert_text_at_cursor(code)
        │     └─▶ insere na posição atual do cursor
        │
        ├─▶ self._left_panel.show_explorer()   # volta pro projeto
        └─▶ QSettings["workspace/left_panel_mode"] = "explorer"
```

---

## 5. Schema SQL completo

```sql
-- Tabela principal
CREATE TABLE IF NOT EXISTS entries (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    title         TEXT NOT NULL CHECK(length(title) BETWEEN 1 AND 200),
    description   TEXT CHECK(description IS NULL OR length(description) <= 10000),
    code          TEXT NOT NULL CHECK(length(code) BETWEEN 1 AND 100000),
    language      TEXT NOT NULL DEFAULT 'text' CHECK(length(language) <= 30),
    category      TEXT CHECK(category IS NULL OR length(category) <= 50),
    origin_path   TEXT,
    origin_line   INTEGER CHECK(origin_line IS NULL OR origin_line >= 1),
    is_public     INTEGER NOT NULL DEFAULT 0 CHECK(is_public IN (0, 1)),
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_entries_language  ON entries(language);
CREATE INDEX IF NOT EXISTS idx_entries_category  ON entries(category);
CREATE INDEX IF NOT EXISTS idx_entries_created_at ON entries(created_at DESC);

-- Tags (únicas por nome lowercase)
CREATE TABLE IF NOT EXISTS tags (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE CHECK(length(name) BETWEEN 1 AND 30)
);

-- N:N
CREATE TABLE IF NOT EXISTS entry_tags (
    entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    tag_id   INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (entry_id, tag_id)
);

-- FTS5 (full-text search)
CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
    title,
    description,
    code,
    content='entries',
    content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'
);

-- Triggers pra manter FTS5 sincronizado
CREATE TRIGGER IF NOT EXISTS entries_ai AFTER INSERT ON entries BEGIN
    INSERT INTO entries_fts(rowid, title, description, code)
    VALUES (new.id, new.title, new.description, new.code);
END;

CREATE TRIGGER IF NOT EXISTS entries_ad AFTER DELETE ON entries BEGIN
    INSERT INTO entries_fts(entries_fts, rowid, title, description, code)
    VALUES ('delete', old.id, old.title, old.description, old.code);
END;

CREATE TRIGGER IF NOT EXISTS entries_au AFTER UPDATE ON entries BEGIN
    INSERT INTO entries_fts(entries_fts, rowid, title, description, code)
    VALUES ('delete', old.id, old.title, old.description, old.code);
    INSERT INTO entries_fts(rowid, title, description, code)
    VALUES (new.id, new.title, new.description, new.code);
END;

-- Tabela de migrations (versionamento manual)
CREATE TABLE IF NOT EXISTS _migrations (
    version    INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

-- Migration inicial
INSERT OR IGNORE INTO _migrations (version, applied_at) VALUES (1, datetime('now'));
```

---

## 6. Algoritmo de dedup de tags

```python
def normalize_tags(raw_tags: list[str]) -> list[str]:
    """Normaliza tags para storage: lowercase, strip, dedup, max 20."""
    seen: set[str] = set()
    result: list[str] = []
    for tag in raw_tags:
        normalized = tag.strip().lower()
        if not normalized:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
        if len(result) >= 20:
            break
    return result
```

Regras:
- Lowercase (`"Python"` → `"python"`)
- Strip de whitespace
- Dedup via `set`
- Max 20 tags por entrada
- Rejeita tags vazias
- Caracteres Unicode permitidos (regex `^[a-z0-9_.\-]{1,30}$` no MVP)

---

## 7. Algoritmo de busca FTS5

```python
def search_entries(self, query: str, *, limit: int = 50) -> list[Entry]:
    query = query.strip()
    if not query:
        return self.list_entries(limit=limit)

    # FTS5 syntax: prefixo com *
    # "cache" → "cache*"
    # "cache lru" → "cache* lru*"  (AND implícito)
    fts_query = " ".join(
        f'"{term}"' if " " in term else f"{term}*"
        for term in query.split()
        if term
    )

    sql = """
        SELECT e.*
        FROM entries_fts fts
        JOIN entries e ON e.id = fts.rowid
        WHERE entries_fts MATCH ?
        ORDER BY rank
        LIMIT ?
    """
    with self._connect() as conn:
        rows = conn.execute(sql, (fts_query, limit)).fetchall()
    return [self._row_to_entry(r) for r in rows]
```

`rank` é o score BM25 calculado pelo FTS5 — quanto menor, melhor
match. Sem precisar de `ORDER BY` adicional.

---

## 8. Padrão de QSettings

| Chave | Tipo | Default | Propósito |
|---|---|---|---|
| `workspace/left_panel_mode` | `str` | `"explorer"` | `"explorer"` ou `"catalog"` |
| `catalog/db_path` | `str` | (calculado) | Override do path do banco |
| `catalog/last_search` | `str` | `""` | Última query de busca |
| `catalog/last_filter_category` | `str` | `""` | Última categoria selecionada |
| `catalog/last_filter_language` | `str` | `""` | Última linguagem selecionada |

---

## 9. Lista virtualizada (QListView + Model custom)

```python
class CatalogoListModel(QAbstractListModel):
    """Model custom pra QListView, suporta 10k+ entradas sem travar."""

    EntryRole = Qt.UserRole + 1

    def __init__(self, entries: list[Entry] | None = None):
        super().__init__()
        self._entries: list[Entry] = entries or []

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._entries)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._entries):
            return None
        entry = self._entries[index.row()]
        if role == Qt.DisplayRole:
            return entry.title
        if role == Qt.UserRole:
            return entry
        if role == Qt.ToolTipRole:
            return f"{entry.title}\n{entry.language} · {entry.category or '—'}"
        return None

    def set_entries(self, entries: list[Entry]) -> None:
        self.beginResetModel()
        self._entries = entries
        self.endResetModel()
```

QListView já é virtualizado por padrão (só renderiza itens
visíveis). Com 10k entries, scroll é instantâneo.

---

## 10. Onde entra no menu (MainWindow)

```python
# No _build_menu() da MainWindow:
view_menu = menubar.addMenu("&View")
theme_menu = view_menu.addMenu("&Theme")  # existente
view_menu.addSeparator()
painel_menu = view_menu.addMenu("&Painel esquerdo")
self._explorer_action = QAction("&Projeto", self, checkable=True)
self._explorer_action.setShortcut(QKeySequence("Ctrl+1"))
self._explorer_action.triggered.connect(
    lambda: self._on_left_panel_mode_changed("explorer")
)
self._catalog_action = QAction("&Catálogo", self, checkable=True)
self._catalog_action.setShortcut(QKeySequence("Ctrl+2"))
self._catalog_action.triggered.connect(
    lambda: self._on_left_panel_mode_changed("catalog")
)
painel_menu.addAction(self._explorer_action)
painel_menu.addAction(self._catalog_action)
self._panel_actions = QActionGroup(self)
self._panel_actions.setExclusive(True)
self._panel_actions.addAction(self._explorer_action)
self._panel_actions.addAction(self._catalog_action)
```

---

## 11. CodeEditorPanel.insert_text_at_cursor(text)

```python
# Adicionar em app/ui/code_editor.py:

def insert_text_at_cursor(self, text: str) -> bool:
    """Insere ``text`` na posição atual do cursor.
    
    Returns False se não tem arquivo aberto (caller decide o que fazer).
    """
    if self._current_path is None:
        return False
    cursor = self._editor.textCursor()
    cursor.insertText(text)
    # Marca como modified pro usuário saber que tem mudança não salva.
    self._editor.document().setModified(True)
    return True
```

---

## 12. Testes (estrutura)

```
tests/unit/test_catalogo_service.py    # CRUD + FTS5 + dedup + import/export
tests/unit/test_catalogo_models.py     # dataclasses + validation
tests/integration/test_catalogo_panel.py  # UI: toggle, search, insert
tests/unit/test_left_panel.py           # container QStackedWidget
tests/unit/test_insert_text_at_cursor.py # code_editor extension
```

Cobertura alvo: ≥ 85% nos módulos novos.

---

## 13. Risco + mitigações

| Risco | Probabilidade | Mitigação |
|---|---|---|
| FTS5 indisponível no SQLite do sistema | Baixíssima (≥ 3.9 desde 2015) | Fallback `LIKE '%query%'` com warning |
| Banco corrompido | Baixa | Backup automático `.bak` + cria novo |
| Disco cheio | Baixa | Try/except OSError → mensagem amigável |
| Performance com 100k+ entradas | Média | Testes de carga com `pytest-benchmark` no Change 007 |
| Tags com caracteres estranhos | Média | Regex `^[a-z0-9_.\-]{1,30}$` no MVP |
| Conflito entre 2 janelas abertas | Baixa | Lock file (`*.db.lock`) — deferido pra Change 007 |

---

## 14. Decisões deferidas (vão pro Change 007+)

- **Gist sync** (botão "Compartilhar")
- **Site estático** pras públicas
- **Markdown export** com 1 arquivo `.md` por entrada
- **Drag-and-drop** de arquivo pro catálogo
- **Syntax highlight** nos snippets do preview
- **Templates** com placeholders
- **Links** entre entradas
- **RAG / indexação semântica** (LlamaIndex)
- **`.exe` instalável**
- **Lock file** pra multi-janela
