# Change 005 — Design: Interactive features

> Decisões de **como** os 5 sub-features são implementados. Mapeia
> `spec.md` para código concreto.

---

## 1. Chat com IA — wire-up

### 1.1. Estrutura do `VisualizerPanel` revisada

```python
class VisualizerPanel(QWidget):
    MAX_HISTORY: int = 50

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.last_markdown: str | None = None
        self.last_error: str | None = None
        self.chat_history: list[ChatTurn] = []
        self._current_file_path: str | None = None
        self._current_file_content: str = ""
        self._build_ui()
        self.show_idle()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Top: render area (QWebEngineView)
        self._web = QWebEngineView(self)
        layout.addWidget(self._web, stretch=1)

        # History bar
        history_row = QHBoxLayout()
        self._history_combo = QComboBox(self)
        self._history_combo.setPlaceholderText("History")
        self._history_combo.currentIndexChanged.connect(self._on_history_selected)
        history_row.addWidget(self._history_combo, stretch=1)
        clear_btn = QPushButton("Clear", self)
        clear_btn.clicked.connect(self.clear_chat)
        history_row.addWidget(clear_btn)
        history_wrap = QWidget(self)
        history_wrap.setLayout(history_row)
        history_wrap.setContentsMargins(4, 2, 4, 2)
        layout.addWidget(history_wrap)

        # Input area
        input_row = QVBoxLayout()
        input_row.setContentsMargins(4, 2, 4, 4)
        self._input = QTextEdit(self)
        self._input.setPlaceholderText("Ask about this file…  (Enter to send, Shift+Enter for newline)")
        self._input.setMaximumHeight(80)
        self._input.installEventFilter(self)  # for Enter handling
        input_row.addWidget(self._input)

        send_row = QHBoxLayout()
        send_row.setContentsMargins(0, 0, 0, 0)
        send_row.addStretch(1)
        self._send_btn = QPushButton("Send", self)
        self._send_btn.setDefault(True)
        self._send_btn.clicked.connect(self._on_send_clicked)
        send_row.addWidget(self._send_btn)
        input_row.addLayout(send_row)

        input_wrap = QWidget(self)
        input_wrap.setLayout(input_row)
        layout.addWidget(input_wrap)
        layout.setStretchFactor(self._web, 1)
        layout.setStretchFactor(input_wrap, 0)
```

### 1.2. Event filter para Enter

```python
def eventFilter(self, obj, event) -> bool:
    if obj is self._input and event.type() == QEvent.Type.KeyPress:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                return False  # let Shift+Enter insert newline
            self._on_send_clicked()
            return True
    return super().eventFilter(obj, event)
```

### 1.3. Public methods para o `MainWindow` chamar

```python
def set_file_context(self, path: str | None, content: str) -> None:
    """Set the current file context for the chat."""
    self._current_file_path = path
    self._current_file_content = content

def show_markdown(self, text: str, theme: str = "dark") -> None:
    """Render and append to chat history if it's a chat response."""
    super().show_markdown(text, theme)  # or inline the implementation
    self.chat_history.append(ChatTurn(user=self._pending_user_msg, ai=text))
    self._refresh_history_combo()
    self._pending_user_msg = ""

def clear_chat(self) -> None:
    self.chat_history.clear()
    self._refresh_history_combo()
    self.show_idle()
```

### 1.4. Prompt generation

```python
def _build_chat_prompt(self, user_msg: str) -> str:
    context = f"File: {self._current_file_path}\n\n" if self._current_file_path else ""
    file_section = (
        f"File content:\n```\n{self._current_file_content}\n```\n\n"
        if self._current_file_content else ""
    )
    return f"{context}{file_section}User question:\n{user_msg}\n\nAnswer in markdown. Be concise."
```

## 2. Spinner animado

### 2.1. SVG inline

```html
<svg viewBox="0 0 50 50" width="48" height="48" class="spinner">
  <circle cx="25" cy="25" r="20" fill="none" stroke="#888" 
          stroke-width="4" stroke-linecap="round" 
          stroke-dasharray="80 200" />
</svg>
<style>
  @keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }
  .spinner {
    animation: spin 1.2s linear infinite;
  }
</style>
```

### 2.2. Template substitution

```python
_LOADING_HTML_TEMPLATE: str = (
    '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
    '<title>ArchExplorer</title>'
    '<style>'
    '@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }'
    '.spinner { animation: spin 1.2s linear infinite; }'
    '</style>'
    '</head>'
    '<body style="display: flex; align-items: center; justify-content: center; '
    'height: 200px; {body_style}">'
    '<div style="text-align: center;">'
    '<svg viewBox="0 0 50 50" width="48" height="48" class="spinner">'
    '<circle cx="25" cy="25" r="20" fill="none" stroke="{spinner_color}" '
    'stroke-width="4" stroke-linecap="round" stroke-dasharray="80 200" />'
    '</svg>'
    '<p style="margin-top: 12px;">Analyzing {label}...</p>'
    '</div>'
    '</body></html>'
)
```

## 3. Editor editável

### 3.1. `CodeEditorPanel` revisado

```python
class CodeEditorPanel(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._current_path: str | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(4, 2, 4, 2)
        self._save_btn = QPushButton("Save", self)
        self._save_btn.setShortcut(QKeySequence("Ctrl+S"))
        self._save_btn.clicked.connect(self._on_save_clicked)
        toolbar.addWidget(self._save_btn)
        # Undo/Redo use native QPlainTextEdit shortcuts
        toolbar.addStretch(1)
        self._ai_edit_btn = QPushButton("Edit with AI", self)
        self._ai_edit_btn.clicked.connect(self._on_ai_edit_clicked)
        toolbar.addWidget(self._ai_edit_btn)
        toolbar_wrap = QWidget(self)
        toolbar_wrap.setLayout(toolbar)
        v.addWidget(toolbar_wrap)

        # Editor
        self._editor = QPlainTextEdit(self)
        self._editor.setFont(QFont("Consolas, Menlo, monospace", 10))
        self._editor.document().modificationChanged.connect(self._on_modified_changed)
        v.addWidget(self._editor, stretch=1)

    def _on_save_clicked(self) -> None:
        if self._current_path is None:
            return
        try:
            # Use FileManager if available, else plain write
            Path(self._current_path).write_text(
                self._editor.toPlainText(), encoding="utf-8"
            )
            self._editor.document().setModified(False)
        except OSError as exc:
            # Surface error via signal
            self.save_failed.emit(str(exc))
    
    save_failed = Signal(str)

    def _on_modified_changed(self, modified: bool) -> None:
        self._save_btn.setEnabled(modified)
```

### 3.2. AI-edit flow

```python
@Slot()
def _on_ai_edit_clicked(self) -> None:
    if self._current_path is None or self._editor.toPlainText() == "":
        return
    instruction, ok = QInputDialog.getText(
        self, "Edit with AI",
        "What change do you want? (leave empty to ask AI to improve)",
        text="Improve this code.",
    )
    if not ok:
        return
    self.ai_edit_requested.emit(self._current_path, instruction or "Improve this code.")

ai_edit_requested = Signal(str, str)  # path, instruction
```

The `MainWindow` connects this signal to a new `AIEditWorker` that:
1. Calls `AIEngine.edit_file(content, instruction, file_type)`
2. Emits `edit_preview(new_content)` 
3. `MainWindow` shows a preview dialog with Apply/Cancel

### 3.3. New `FileManager.write_file` method

```python
def write_file(self, path: str, content: str) -> None:
    p = Path(path)
    if not p.parent.exists():
        # Create parent dirs (one level)
        p.parent.mkdir(parents=True, exist_ok=True)
    try:
        p.write_text(content, encoding="utf-8")
    except OSError as exc:
        raise FileOperationError(f"Cannot write {path}: {exc}", path=path)
```

### 3.4. New `AIEngine.edit_file` pipeline

```python
EDIT_FILE_PROMPT: Final[str] = """You are an expert {file_type} developer.
Apply this change to the file:
{instruction}

Current file:
```{file_type}
{content}
```

Output ONLY the new file content. No markdown fences, no explanation.
"""

def edit_file(self, content: str, instruction: str, file_type: str) -> str:
    prompt = EDIT_FILE_PROMPT.format(
        file_type=file_type,
        instruction=instruction,
        content=content,
    )
    return self._provider.generate(prompt, temperature=0.3)
```

## 4. Toolbar do FileExplorer

### 4.1. `FileExplorerPanel` revisado

```python
class FileExplorerPanel(QWidget):
    file_selected = Signal(str)

    def __init__(self, root: Path | None = None, parent=None) -> None:
        super().__init__(parent)
        self._current_root = root or Path(os.getcwd())
        self._build_ui()

    def _build_ui(self) -> None:
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(4, 2, 4, 2)
        select_btn = QPushButton("Select Folder", self)
        select_btn.setShortcut(QKeySequence("Ctrl+O"))
        select_btn.clicked.connect(self._on_select_folder)
        toolbar.addWidget(select_btn)
        new_btn = QPushButton("+ Folder", self)
        new_btn.setShortcut(QKeySequence("Ctrl+Shift+N"))
        new_btn.clicked.connect(self._on_new_folder)
        toolbar.addWidget(new_btn)
        refresh_btn = QPushButton("Refresh", self)
        refresh_btn.setShortcut(QKeySequence("F5"))
        refresh_btn.clicked.connect(self._on_refresh)
        toolbar.addWidget(refresh_btn)
        toolbar.addStretch(1)
        toolbar_wrap = QWidget(self)
        toolbar_wrap.setLayout(toolbar)
        v.addWidget(toolbar_wrap)

        # Inline new-folder input (hidden by default)
        self._new_folder_input = QLineEdit(self)
        self._new_folder_input.setPlaceholderText("New folder name…")
        self._new_folder_input.setVisible(False)
        self._new_folder_input.returnPressed.connect(self._commit_new_folder)
        self._new_folder_input.escapePressed = self._cancel_new_folder  # custom
        v.addWidget(self._new_folder_input)

        # Tree
        self._model = QFileSystemModel(self)
        self._model.setIconProvider(CustomIconProvider())
        self._model.setRootPath(str(self._current_root))
        self._view = QTreeView(self)
        self._view.setModel(self._model)
        self._view.setRootIndex(self._model.index(str(self._current_root)))
        # ... rest as before
        v.addWidget(self._view, stretch=1)

    def _on_new_folder(self) -> None:
        self._new_folder_input.setVisible(True)
        self._new_folder_input.setFocus()

    def _commit_new_folder(self) -> None:
        name = self._new_folder_input.text().strip()
        if not name:
            self._new_folder_input.setVisible(False)
            return
        try:
            # Use FileManager (need DI here) or direct call
            from app.services import FileManager
            FileManager().create_folder(str(self._current_root), name)
            self._model.refresh()
        except FileOperationError as exc:
            QMessageBox.warning(self, "Cannot create folder", exc.message)
        self._new_folder_input.clear()
        self._new_folder_input.setVisible(False)
```

### 4.2. Select Folder via QSettings

`MainWindow._build_ui`:
```python
settings = QSettings()  # uses app org/app
saved_root = settings.value("root_dir", str(Path(os.getcwd())), type=str)
self._file_explorer = FileExplorerPanel(root=Path(saved_root), parent=self)
```

When `select_folder` is triggered:
```python
@Slot()
def _on_select_folder(self) -> None:
    directory = QFileDialog.getExistingDirectory(
        self, "Select Project Root", str(self._current_root)
    )
    if directory:
        self.set_root(Path(directory))
        # Persist
        from PySide6.QtCore import QSettings
        QSettings().setValue("root_dir", directory)

def set_root(self, new_root: Path) -> None:
    self._current_root = new_root
    self._model.setRootPath(str(new_root))
    self._view.setRootIndex(self._model.index(str(new_root)))
```

## 5. Polish QSS

### 5.1. `light.qss` fix

```css
/* light.qss */
QTreeView::branch {
    background-color: #e8e8e8;  /* was: transparent — invisible on white */
}
```

### 5.2. Padding (dark + light)

```css
/* dark.qss + light.qss */
QTreeView { padding: 4px; }
QPlainTextEdit { padding: 4px; }
```

## 6. Estrutura de arquivos (pós-merge)

```
app/services/
├── file_manager.py          # modificado — add write_file
└── ai_engine.py              # modificado — add edit_file

app/ui/
├── visualizer.py             # modificado — chat input + history + spinner
├── code_editor.py            # modificado — toolbar + save/undo/AI-edit
├── file_explorer.py          # modificado — toolbar + new folder + select
├── main_window.py            # modificado — wire all signals, QSettings root
└── html_template.py          # modificado — add spinner CSS

app/services/ai_engine.py     # modificado — add edit_file pipeline

tests/
├── unit/
│   ├── test_chat_history.py
│   ├── test_file_manager_write.py
│   ├── test_ai_engine_edit_file.py
│   ├── test_editor_save_undo.py
│   ├── test_explorer_toolbar.py
│   ├── test_visualizer_themes.py  # modificado — add chat tests
│   ├── test_file_inspector.py
│   └── test_html_template.py      # modificado — add spinner test
└── integration/
    ├── test_chat_sends_message.py
    ├── test_editor_save_writes_file.py
    ├── test_ai_edit_preview_apply.py
    ├── test_select_folder_re_roots.py
    └── test_new_folder_input_flow.py
```

## 7. Compatibilidade

- `FileManager` ganha método `write_file` — backwards-compat
- `AIEngine` ganha método `edit_file` — backwards-compat
- `VisualizerPanel` ganha chat — UI extendida, public API estendida (não quebra)
- `CodeEditorPanel` muda de read-only pra editável — **breaking**
  (test_ai_engine já não assume read-only; o teste é o `_editor.setReadOnly(True)`)
  → atualizo o teste
- `FileExplorerPanel` ganha toolbar — UI extendida, signals idênticos
- `MainWindow` lê `QSettings` para raiz — se chave inválida, fallback
  para cwd

## 8. Trade-offs

| Decisão | Custo | Benefício |
|---|---|---|
| Chat history in-memory (não persistido) | Perde ao fechar | Simples; LRU cap evita RAM |
| AI-edit sem diff colorido | Diff mais simples | Preview é suficiente; diff colorido seria +~200 LOC |
| Toolbar no file explorer | +50 LOC | UX clara; sem toolbar, teríamos context menus |
| QSettings para root_dir | Pode ter path inválido | Persiste entre execuções |
| Spinner SVG inline em vez de GIF | Mais código HTML | Sem dependência de arquivo externo |
| Sem streaming de tokens | Latência visível | Muito mais simples; suficiente para 3B |
| Editor "dirty" com QPlainTextEdit nativo | Sem custom | Já vem grátis; só precisamos conectar ao botão Save |
