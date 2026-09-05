# Change 005 — Tasks: Interactive features

> Checklist executável. Marcar `[x]` conforme conclusão.

---

## Bloco A — Foundation (services)

- [ ] A1. `app/services/file_manager.py`: add `write_file(path, content)` method
- [ ] A2. `app/services/ai_engine.py`: add `EDIT_FILE_PROMPT` + `edit_file(content, instruction, file_type)` method
- [ ] A3. `tests/unit/test_file_manager.py`: add `test_write_file_*` (5+ tests)
- [ ] A4. `tests/unit/test_ai_engine.py`: add `test_engine_edit_file_*` (3+ tests)

## Bloco B — Chat input (VisualizerPanel)

- [ ] B1. `app/ui/visualizer.py`: add `ChatTurn` dataclass, `chat_history` list
- [ ] B2. Add history row (QComboBox + Clear button)
- [ ] B3. Add input row (QTextEdit + Send button)
- [ ] B4. Event filter for Enter (send) vs Shift+Enter (newline)
- [ ] B5. `set_file_context(path, content)` method
- [ ] B6. `clear_chat()` method (resets history + idle)
- [ ] B7. LRU cap at 50 messages
- [ ] B8. `_build_chat_prompt(user_msg)` builds full prompt with file context
- [ ] B9. Public method `start_chat(user_msg, ai_engine)` for MainWindow to call
- [ ] B10. `tests/unit/test_chat_history.py`: append, clear, cap, prompt format

## Bloco C — Loading animation (spinner)

- [ ] C1. `app/ui/visualizer.py`: update `_LOADING_HTML_TEMPLATE` with SVG spinner + CSS `@keyframes`
- [ ] C2. Spinner color matches theme (gray for dark, gray for light)
- [ ] C3. `tests/unit/test_visualizer_themes.py`: add `test_loading_html_has_spinner`

## Bloco D — Editor editável (CodeEditorPanel)

- [ ] D1. `app/ui/code_editor.py`: add toolbar (Save, [Edit with AI])
- [ ] D2. Remove `setReadOnly(True)` — make editor editable
- [ ] D3. `set_content(path, text)` — also store path
- [ ] D4. `save_failed = Signal(str)` — surface OSError
- [ ] D5. `_on_save_clicked`: writes via Path.write_text, clears modified flag
- [ ] D6. `ai_edit_requested = Signal(str, str)` — path + instruction
- [ ] D7. `_on_ai_edit_clicked`: QInputDialog for instruction
- [ ] D8. Update test_main_window to reflect editable state
- [ ] D9. `tests/unit/test_editor_save_undo.py`: save, dirty marker, no-op when no path

## Bloco E — Toolbar do FileExplorer

- [ ] E1. `app/ui/file_explorer.py`: add toolbar row (3 buttons)
- [ ] E2. `_on_select_folder`: QFileDialog.getExistingDirectory, call set_root
- [ ] E3. `set_root(new_root)`: updates model + view
- [ ] E4. `_on_new_folder`: shows inline QLineEdit
- [ ] E5. `_commit_new_folder`: creates via FileManager, refreshes, hides input
- [ ] E6. `_cancel_new_folder`: hides input
- [ ] E7. `_on_refresh`: calls self._model.refresh()
- [ ] E8. `tests/unit/test_explorer_toolbar.py`: 3 actions present, signals connected

## Bloco F — MainWindow wiring

- [ ] F1. `app/ui/main_window.py`: read root_dir from QSettings in `_build_ui`
- [ ] F2. Connect `explorer.file_selected` → `editor.set_content(path, text)` → `visualizer.set_file_context(path, text)` → `visualizer.show_loading(name)`
- [ ] F3. Connect `explorer.select_folder` signal to QSettings persistence
- [ ] F4. New `AIEditWorker(QRunnable)` for the AI-edit flow
- [ ] F5. Wire AI-edit signal: editor emits → MainWindow creates worker → preview dialog → apply
- [ ] F6. Connect `editor.save_failed` → `visualizer.show_error`
- [ ] F7. Connect `editor.ai_edit_requested` → new `AIEditWorker`
- [ ] F8. Update `tests/integration/test_ui_flow.py` to cover new signals

## Bloco G — Polish QSS

- [ ] G1. `app/ui/qss/light.qss`: update `QTreeView::branch` background-color to `#e8e8e8`
- [ ] G2. `app/ui/qss/dark.qss`: add `QTreeView`, `QPlainTextEdit` padding
- [ ] G3. `app/ui/qss/light.qss`: add `QTreeView`, `QPlainTextEdit` padding
- [ ] G4. `tests/unit/test_theme.py`: assert light QSS has updated branch color
- [ ] G5. `tests/unit/test_html_template.py`: add `test_loading_html_has_spinner_css` (from C3)

## Bloco H — Integration tests

- [ ] H1. `tests/integration/test_chat_sends_message.py`: type → click Send → history grows
- [ ] H2. `tests/integration/test_editor_save_writes_file.py`: edit → save → file content updated
- [ ] H3. `tests/integration/test_ai_edit_preview_apply.py`: trigger edit → preview shows → apply writes
- [ ] H4. `tests/integration/test_new_folder_input_flow.py`: type name → Enter → folder created
- [ ] H5. `tests/integration/test_select_folder_persists.py`: select → close → reopen → still selected

## Bloco I — Docs

- [ ] I1. Update `docs/frontend/front.md` with: chat input, spinner, editor save/AI-edit, toolbar, padding
- [ ] I2. Update `docs/backend/backend.md` with: `edit_file` pipeline, `write_file` method
- [ ] I3. Update `docs/testing/testing-strategy.md` if new test patterns emerge

## Bloco J — Smoke + commit

- [ ] J1. `py -m pytest` verde (≥ 245 tests, was 228)
- [ ] J2. `py -m app.main` abre sem warnings
- [ ] J3. Manual: clicar num `.py` → chat input visível → enviar msg → resposta renderiza
- [ ] J4. Manual: editar texto no editor → Ctrl+S → arquivo no disco muda
- [ ] J5. Manual: toolbar do tree: Select Folder, +Folder, Refresh funcionam
- [ ] J6. Manual: tema light mostra pastas visíveis (contraste ≥ 3:1)
- [ ] J7. `git commit -F .git/COMMIT_EDITMSG.tmp` com mensagem completa
- [ ] J8. Move `changes/005-interactive-features/` para `changes/archive/`
- [ ] J9. Commit `chore: archive change 005`

## Definition of Done

Todos os blocos A–I marcados, J1–J6 confirmados pelo Henrique.

---

## Notas

- Bloco A (services) é a fundação; fazer primeiro.
- Bloco G (QSS) é o mais simples; pode ser feito em paralelo com os outros.
- Os integration tests (Bloco H) dependem dos services + UI; fazer depois dos blocos B–F.
- Docs (Bloco I) podem ser atualizados a qualquer momento.
