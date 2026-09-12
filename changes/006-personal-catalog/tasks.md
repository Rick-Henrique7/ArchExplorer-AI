# Change 006 — Tasks: Catálogo Pessoal de Soluções

> Checklist executável. Marcar `[x]` conforme conclusão.

---

## Bloco A — Banco e models

- [ ] A1. `app/services/models.py`: criar `Entry`, `Tag`, `EntryTag` como `@dataclass(frozen=True)`
- [ ] A2. `app/services/catalogo_service.py`: classe `CatalogoService` com `__init__(db_path)` + `_init_schema()`
- [ ] A3. `_init_schema()`: executar schema completo (entries, tags, entry_tags, entries_fts, triggers, _migrations)
- [ ] A4. `app/services/exceptions.py`: adicionar `CatalogoError`
- [ ] A5. `app/services/__init__.py`: exportar `CatalogoService`, `Entry`, `Tag`, `CatalogoError`
- [ ] A6. Helpers: `default_catalog_path()` retorna `%USERPROFILE%/Documents/ArchExplorer/catalogo.db`
- [ ] A7. Helper: `normalize_tags(raw_tags) -> list[str]` (lowercase, strip, dedup, max 20)
- [ ] A8. `tests/unit/test_catalogo_models.py`: 8+ testes (dataclass + validação)

---

## Bloco B — CRUD do serviço

- [ ] B1. `create_entry(...) -> Entry`: valida, dedup tags, INSERT transacional, retorna dataclass preenchido
- [ ] B2. `get_entry(entry_id) -> Entry | None`: SELECT por id, retorna None se não existe
- [ ] B3. `update_entry(entry_id, **fields) -> Entry`: UPDATE parcial (só campos não-None)
- [ ] B4. `delete_entry(entry_id) -> None`: DELETE (CASCADE remove entry_tags)
- [ ] B5. `tests/unit/test_catalogo_service.py::test_*`: 12+ testes pra CRUD (insert/update/delete/get)

---

## Bloco C — Busca e listagem

- [ ] C1. `list_entries(*, language=None, category=None, tag=None, limit=200) -> list[Entry]`: filtros opcionais via WHERE
- [ ] C2. `search_entries(query, *, limit=50) -> list[Entry]`: FTS5 MATCH com prefixo `*` em cada termo
- [ ] C3. `list_tags() -> list[Tag]`: SELECT ordenado por nome
- [ ] C4. `list_categories() -> list[str]`: SELECT DISTINCT, ordenado
- [ ] C5. `stats() -> dict`: total + contagem por linguagem + categoria
- [ ] C6. `tests/unit/test_catalogo_service.py::test_search_*`: 5+ testes (FTS5, prefixo, multi-termo)
- [ ] C7. `tests/unit/test_catalogo_service.py::test_list_*`: 4+ testes (filtros)

---

## Bloco D — Import / Export

- [ ] D1. `export_json() -> str`: serializa todas as entries + tags pra JSON
- [ ] D2. `import_json(payload: str) -> int`: parse, valida, insere (com dedup de tags)
- [ ] D3. `tests/unit/test_catalogo_service.py::test_export_*` e `test_import_*`: 4+ testes
- [ ] D4. Teste de import com JSON malformado → mostra erro, não importa nada

---

## Bloco E — UI: Container LeftPanel

- [ ] E1. `app/ui/left_panel.py`: classe `LeftPanel(QWidget)` com `QStackedWidget`
- [ ] E2. Construtor recebe `FileExplorerPanel` + `CatalogoPanel` (injeção)
- [ ] E3. `show_explorer()` / `show_catalog()`: troca `_stack.setCurrentIndex(...)`
- [ ] E4. Signal `mode_changed = Signal(str)` pra MainWindow reagir
- [ ] E5. `tests/unit/test_left_panel.py`: 5+ testes (modo inicial, troca preserva estado)

---

## Bloco F — UI: CatalogoPanel

- [ ] F1. `app/ui/catalogo_panel.py`: classe `CatalogoPanel(QWidget)`
- [ ] F2. `__init__(catalogo_service)`: cria QLineEdit (busca), QToolBar (+Nova/Importar/Exportar), QComboBox×2 (categoria/linguagem), FlowLayout (tags), QListView
- [ ] F3. `CatalogoListModel(QAbstractListModel)`: `set_entries()`, `rowCount()`, `data()` (3 roles)
- [ ] F4. Signals: `entry_selected(int)`, `insert_into_editor_requested(int)`, `new_entry_requested()`, `edit_entry_requested(int)`, `delete_entry_requested(int)`
- [ ] F5. `_on_search_changed(text)`: debounce 200ms (QTimer single-shot) → `service.search_entries`
- [ ] F6. `_on_filter_changed()`: rebuild com filtros
- [ ] F7. `_on_entry_clicked(index)`: emite `entry_selected(self._current_entries[index.row()].id)`
- [ ] F8. `refresh()`: rebusca do banco e atualiza QListView
- [ ] F9. `tests/unit/test_catalogo_panel.py`: 10+ testes (busca, filtros, signals)

---

## Bloco G — UI: EntryEditorDialog

- [ ] G1. `app/ui/entry_editor_dialog.py`: classe `EntryEditorDialog(QDialog)` (mode: `create` ou `edit`)
- [ ] G2. Form: title (QLineEdit), category (QComboBox), language (QComboBox), tags (TagEditor custom), description (QTabWidget: edit + preview), code (QPlainTextEdit), origin (path+line picker), is_public (QCheckBox)
- [ ] G3. Validação inline (QValidator ou check no accept)
- [ ] G4. `get_draft() -> EntryDraft`: retorna dataclass preenchido ou None se cancelado
- [ ] G5. Modo edit: preenche form com entry existente
- [ ] G6. `tests/unit/test_entry_editor_dialog.py`: 6+ testes (validação, mode create/edit)

---

## Bloco H — UI: EntryPreviewPanel

- [ ] H1. `app/ui/entry_preview_panel.py`: classe `EntryPreviewPanel(QWidget)` (mostra entry selecionada no centro)
- [ ] H2. Renderiza título (h1), metadata, descrição (markdown), código (botão copiar), origem, botões
- [ ] H3. Reuso: `build_html_template` do Visualizer
- [ ] H4. Signals: `insert_into_editor(int)`, `edit_entry(int)`, `delete_entry(int)`
- [ ] H5. `show_entry(entry: Entry)`, `clear()`, `current_entry() -> Entry | None`

---

## Bloco I — CodeEditorPanel.insert_text_at_cursor

- [ ] I1. Adicionar método `insert_text_at_cursor(text) -> bool` em `app/ui/code_editor.py`
- [ ] I2. Returns False se `_current_path is None`
- [ ] I3. Marca o documento como modified
- [ ] I4. `tests/unit/test_insert_text_at_cursor.py`: 4+ testes (com/sem path, marca dirty)

---

## Bloco J — MainWindow wiring

- [ ] J1. Refatorar `MainWindow._build_ui()`: usar `LeftPanel` em vez de `FileExplorerPanel` direto no splitter
- [ ] J2. Construir `CatalogoPanel(catalogo_service)` e injetar no `LeftPanel`
- [ ] J3. Construir `EntryPreviewPanel` e adicionar ao splitter (entre LeftPanel e CodeEditor? ou substituir Editor? — ver decision abaixo)
- [ ] J4. `_on_left_panel_mode_changed(mode)`: `self._left_panel.show_explorer()` ou `.show_catalog()`, persiste QSettings
- [ ] J5. Adicionar ação no menu View (`View > Painel esquerdo > Projeto/Catálogo`) com atalhos `Ctrl+1` / `Ctrl+2`
- [ ] J6. QSettings: chave `workspace/left_panel_mode`, lida na inicialização
- [ ] J7. Wire signals: `catalog.entry_selected` → `entry_preview.show_entry()`
- [ ] J8. Wire: `entry_preview.insert_into_editor` → `code_editor.insert_text_at_cursor()` + volta pra Explorer
- [ ] J9. Wire: `catalog.new_entry_requested` → abre `EntryEditorDialog`
- [ ] J10. Wire: `catalog.edit_entry_requested` → abre `EntryEditorDialog` em modo edit
- [ ] J11. Wire: `catalog.delete_entry_requested` → confirma e chama `service.delete_entry()`
- [ ] J12. `tests/integration/test_catalogo_full_flow.py`: 4+ testes end-to-end (cria→busca→insere→deleta)

> **Decisão J3:** EntryPreviewPanel substitui o **centro** (Editor) quando modo Catálogo está ativo e uma entry está selecionada. Quando muda pra Explorer, Editor volta normal. **OU** EntryPreviewPanel fica sempre visível como 4ª coluna. Vou começar com a primeira opção (mais simples) — se ficar estranho visualmente, refatora pra 4 colunas no Change 007.

---

## Bloco K — QSettings + paths

- [ ] K1. `default_catalog_path()`: cria `%USERPROFILE%/Documents/ArchExplorer/` se não existe
- [ ] K2. Override via env var `ARCHEXPLORER_CATALOG_DB`
- [ ] K3. Override via CLI `--catalog-db` (em `app/main.py`)
- [ ] K4. Override via QSettings `catalog/db_path`
- [ ] K5. Backup automático `catalogo.db.bak` quando banco corrompido no open

---

## Bloco L — Docs

- [ ] L1. `docs/frontend/front.md`: nova seção "Catálogo" com screenshots (placeholders)
- [ ] L2. `docs/backend/backend.md`: nova seção `CatalogoService` + schema SQL
- [ ] L3. `docs/features/catalog.md` **(NOVO)**: tutorial "Como usar o catálogo"
- [ ] L4. README: atualizar "Documentação" linkando o novo `features/catalog.md`
- [ ] L5. `docs/decisions/decisions.md`: adicionar seção "Por que SQLite raw (não ORM)"

---

## Bloco M — Smoke + commit + archive

- [ ] M1. `pytest` ≥ 350 passing (atual: 334; +16 mínimo)
- [ ] M2. Cobertura ≥ 85% nos módulos novos (`CatalogoService`, `CatalogoPanel`, `LeftPanel`, `EntryEditorDialog`)
- [ ] M3. Smoke: `python -m app.main` abre sem warnings, toggle funciona
- [ ] M4. Teste manual: criar entry → buscar → inserir no editor → excluir → ok
- [ ] M5. Commit único com mensagem completa (`feat(change-006): ...`)
- [ ] M6. Push pro remote
- [ ] M7. Move `changes/006-personal-catalog/` para `changes/archive/`
- [ ] M8. Commit `chore: archive change 006 (personal catalog shipped)`

---

## Definition of Done

Todos os blocos A–L marcados, M1–M4 confirmados, M5–M8 commitados.

---

## Notas

- **Bloco A** é fundação; fazer primeiro.
- **Bloco F/G** (UI) podem ir em paralelo depois de A/B/C.
- **Bloco J** (wiring) depende de E/F/G/H.
- **Bloco L** (docs) pode ir em paralelo com qualquer outro.
- Cada bloco deve terminar com `pytest tests/<bloco>_<test>.py` verde antes do próximo.
- Se SQLModel parecer útil no spike, fallback pra dataclass + sqlite3 raw é aceitável.
