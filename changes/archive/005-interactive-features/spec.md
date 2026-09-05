# Change 005 — Spec: Interactive features

> Comportamento observável. Para **como** é implementado, veja `design.md`.

---

## 1. Chat com IA

### 1.1. Layout do `VisualizerPanel`

```
+-----------------------------------+
|                                   |
|  Render area (markdown / spinner) |
|  (existing QWebEngineView)        |
|                                   |
|                                   |
+-----------------------------------+
| [History dropdown ▾]  [Clear]     |  ← new: history controls
+-----------------------------------+
| > Ask about this file...         |  ← new: QTextEdit multi-line
|                                   |     (Enter sends, Shift+Enter newline)
+-----------------------------------+
|                          [Send →] |  ← new: send button
+-----------------------------------+
```

### 1.2. Estado

```python
class VisualizerPanel:
    chat_history: list[ChatTurn]   # [(user_msg, ai_response), ...]
    current_file_path: str | None  # path of the file currently loaded
    current_file_content: str      # content of the file currently loaded
```

`ChatTurn` is a `@dataclass(frozen=True)` with `user: str`, `ai: str`.

### 1.3. Comportamento

1. User digita mensagem + clica Send (ou Enter)
2. `chat_history.append(ChatTurn(user_msg, ai_response))` quando IA responde
3. Render area mostra a última resposta
4. History dropdown: lista de turns anteriores; clicar re-renderiza
5. "Clear" button: limpa `chat_history` e mostra idle state
6. Cap: 50 turns (LRU — descarta o mais antigo)

### 1.4. Prompt para a IA

```
You are analyzing the file at {path}.

File content:
```
{file_content}
```

User question:
{user_message}

Answer in markdown. Be concise.
```

## 2. Animação de loading

### 2.1. SVG spinner

```svg
<svg viewBox="0 0 50 50" width="48" height="48" class="spinner">
  <circle cx="25" cy="25" r="20" fill="none" stroke="#888" stroke-width="4" 
          stroke-linecap="round" stroke-dasharray="80 200" />
</svg>
```

Com CSS `@keyframes spin` rotacionando 360° em 1.2s linear infinite.

### 2.2. Integração

Substitui o `<h1>Analyzing...</h1>` atual em `_LOADING_HTML_TEMPLATE`.
Aparece imediatamente quando `show_loading()` é chamado.
Some quando `show_markdown()` ou `show_error()` é chamado.

## 3. Editor editável

### 3.1. Toolbar do `CodeEditorPanel`

```
+--------------------------------------------+
| [Save] [Undo] [Redo] | [Edit with AI ▾] |
+--------------------------------------------+
|                                            |
|  QPlainTextEdit (now editable)             |
|  ...                                       |
+--------------------------------------------+
| file: app/services/ai_engine.py | dirty? *|
+--------------------------------------------+
```

### 3.2. Comportamento

- **Save** (`Ctrl+S`): chama `FileManager.write_file(path, content)`.
  - Sucesso: status bar "Saved at HH:MM:SS"
  - Erro: visualizer mostra erro
- **Undo/Redo**: nativos do QPlainTextEdit (`Ctrl+Z`, `Ctrl+Y`)
- **Edit with AI**:
  1. Dialog pede confirmação (Yes/No) + campo de instrução
  2. Se Yes, dispara `AIEngine.edit_file(content, instruction, file_type)`
  3. Worker roda em background, mostra spinner
  4. Quando termina, mostra dialog de preview com:
     - Diff (linhas adicionadas em verde, removidas em vermelho)
     - Botões "Apply" / "Cancel"
  5. Apply: `FileManager.write_file` + atualiza editor
  6. Cancel: descarta
- **Dirty marker**: `*` no título quando há mudanças não salvas
- **Modified external**: aviso se arquivo foi modificado no disco

### 3.3. `FileManager.write_file` (novo método)

```python
def write_file(self, path: str, content: str) -> None:
    """Write `content` to `path`. Creates parent dirs if needed.
    
    Raises FileOperationError on permission/disk error.
    """
```

Adiciona test `test_write_file_creates_overwrites_round_trip` etc.

### 3.4. `AIEngine.edit_file` (novo pipeline)

```python
def edit_file(self, content: str, instruction: str, file_type: str) -> str:
    """Ask the LLM to edit the file according to the user's instruction.
    
    Returns the full new file content (no diff, no markdown).
    """
```

Prompt:
```
You are an expert {file_type} developer.
Apply this change to the file:
{instruction}

Current file:
```{file_type}
{content}
```

Output ONLY the new file content. No markdown, no explanation, no fences.
```

## 4. Toolbar do FileExplorer

### 4.1. Layout

```
+--------------------------------------------+
| [📁 Select] [+ Folder] [↻ Refresh]    |
+--------------------------------------------+
| 📁 .github                              |
| 📁 app                                 |
| ...                                    |
+--------------------------------------------+
```

### 4.2. Comportamento

- **Select Folder** (`Ctrl+O`): `QFileDialog.getExistingDirectory` →
  `set_root_path()` + persiste em QSettings
- **New Folder** (`Ctrl+Shift+N`):
  - Click → input inline aparece
  - User digita nome + Enter → `FileManager.create_folder(current_root, name)`
  - Esc ou click fora → fecha input
  - Sucesso: tree atualiza, input fecha
  - Erro: status bar mostra mensagem
- **Refresh** (`F5`): `QFileSystemModel.refresh()` em todos os roots

### 4.3. Persistência

QSettings key `root_dir` (string). Lido em `MainWindow._build_ui` ao
construir o `FileExplorerPanel`. Default: `os.getcwd()`.

## 5. Polish QSS

### 5.1. Light theme folder visibility fix

```css
/* light.qss - antes */
QTreeView::branch { background-color: transparent; }

/* light.qss - depois */
QTreeView::branch {
    background-color: #e8e8e8;     /* light gray bg so lines are visible */
}
```

(Contraste da linha do branch sobre o background: ~3:1)

### 5.2. Padding interno

```css
/* dark.qss + light.qss */
QTreeView { padding: 4px; }
QPlainTextEdit { padding: 4px; }
/* QWebEngineView não tem padding no QSS (a página interna já tem) */
```

## 6. Test contracts

### 6.1. Unit (sem Qt graphics, só objetos QWidget)

- `test_chat_history.py`: append, clear, cap at 50
- `test_file_manager_write.py`: write + read roundtrip, permission error
- `test_ai_engine_edit_file.py`: mock provider, prompt format check
- `test_editor_save_undo.py`: dirty marker, save invokes write_file
- `test_explorer_toolbar.py`: 3 actions present, signals connected
- `test_light_qss_contrast.py`: QSS has updated branch color

### 6.2. Integration (com `qapp` fixture)

- `test_chat_sends_message.py`: type → click Send → worker runs → history
  grows
- `test_editor_save_writes_file.py`: edit text, Ctrl+S, file on disk updates
- `test_ai_edit_preview_apply.py`: trigger edit, preview shows, apply writes
- `test_select_folder_re_roots.py`: simulate dialog, tree root changes
- `test_new_folder_input_flow.py`: type name, Enter, folder created

## 7. Restrições

- Python 3.10–3.13
- Windows 11 (target)
- **Sem novas Python deps** (usa só PySide6 já instalado)
- `QSettings` (built-in PySide6)
- `QFileDialog`, `QPainter` (built-in)
