"""Center column: editable code viewer with Save / Edit with AI toolbar."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from app.services import FileManager, FileOperationError


class CodeEditorPanel(QWidget):
    """Editable file content viewer with a Save / Edit-with-AI toolbar.

    Public API (Change 005 additions in **bold**):

    - :meth:`set_content` — replace the editor content
    - :meth:`clear` — empty the editor
    - :attr:`save_failed` **— emitted when writing the file fails**
    - :attr:`ai_edit_requested` **— emitted with the user instruction
      when "Edit with AI" is clicked**
    - :meth:`current_path` **— absolute path of the open file, or None**
    - :meth:`current_content` **— live text in the editor**

    Built-in shortcuts:

    - **Ctrl+S** — save the current file (also exposed as a button)
    - **Ctrl+Z / Ctrl+Y** — Qt's default undo/redo (QPlainTextEdit builtin)
    """

    save_failed = Signal(str)        # error message
    file_saved = Signal(str)         # absolute path of the saved file
    ai_edit_requested = Signal(str, str)  # (absolute_path, instruction)

    def __init__(
        self,
        file_manager: FileManager | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        # None is allowed so tests that don't exercise saving can ignore it.
        self._file_manager = file_manager or FileManager()
        self._current_path: str | None = None
        # file_type mirrors what the inspector returned (e.g. "python").
        # Required by the AI-edit flow to ask the LLM to produce code in
        # the right language/format.
        self._current_file_type: str | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- Toolbar -------------------------------------------------------
        toolbar = QToolBar(self)
        toolbar.setMovable(False)
        toolbar.setIconSize(toolbar.iconSize())  # leave default size

        self._save_button = QPushButton("Salvar", self)
        self._save_button.setShortcut(QKeySequence("Ctrl+S"))
        self._save_button.setToolTip("Salvar o arquivo aberto (Ctrl+S)")
        self._save_button.clicked.connect(self._on_save_clicked)
        toolbar.addWidget(self._save_button)

        self._ai_edit_button = QPushButton("Editar com IA", self)
        self._ai_edit_button.setToolTip(
            "Pede à IA que modifique o arquivo (exibe preview antes de aplicar)"
        )
        self._ai_edit_button.clicked.connect(self._on_ai_edit_clicked)
        toolbar.addWidget(self._ai_edit_button)

        # Add the toolbar to the layout, above the editor.
        toolbar_container = QWidget(self)
        tb_layout = QHBoxLayout(toolbar_container)
        tb_layout.setContentsMargins(4, 4, 4, 4)
        tb_layout.addWidget(toolbar)
        tb_layout.addStretch(1)
        layout.addWidget(toolbar_container)

        # --- Editor --------------------------------------------------------
        self._editor = QPlainTextEdit(self)
        # No longer read-only: Change 005.
        font = QFont("Consolas, Menlo, monospace", 10)
        self._editor.setFont(font)
        # setLineWrapMode left at default (no wrap) for code legibility.

        layout.addWidget(self._editor)

        # Initial button state: disabled until a file is bound.
        self._update_buttons()

    # ----- Public API -------------------------------------------------------

    def set_content(
        self,
        text: str,
        path: str | None = None,
        file_type: str | None = None,
    ) -> None:
        """Replace the editor content with ``text``.

        If ``path`` is given, it is stored so the user can later save /
        send-to-AI. When called with no path (legacy / read-only), the
        editor becomes anonymous — Save and Edit-with-AI become no-ops.

        ``file_type`` is the inspector's classification (e.g. ``"python"``)
        and is used by the AI-edit flow. It is stored only when a path
        is also bound (anonymous content cannot be AI-edited).
        """
        self._current_path = path
        self._current_file_type = file_type if path is not None else None
        self._editor.setPlainText(text)
        self._editor.document().setModified(False)
        self._update_buttons()

    def clear(self) -> None:
        """Empty the editor and forget the current file."""
        self._current_path = None
        self._current_file_type = None
        self._editor.clear()
        self._editor.document().setModified(False)
        self._update_buttons()

    def current_path(self) -> str | None:
        """Return the absolute path of the open file, or ``None``."""
        return self._current_path

    def current_file_type(self) -> str | None:
        """Return the inspector's file_type for the open file, or ``None``."""
        return self._current_file_type

    def current_content(self) -> str:
        """Return the live text in the editor (what the user is currently looking at)."""
        return self._editor.toPlainText()

    def is_dirty(self) -> bool:
        """True if the editor has unsaved changes vs the loaded file."""
        return self._editor.document().isModified()

    def insert_text_at_cursor(self, text: str) -> bool:
        """Insert ``text`` at the current cursor position.

        Used by the catalog flow ("Inserir no editor") to paste a saved
        snippet into the currently open file without overwriting it.
        Returns ``False`` if no file is bound (anonymous editor) — the
        caller should bounce the user back to the Explorer first.

        The document is marked as modified so ``is_dirty()`` reports
        ``True`` until the user saves (Ctrl+S). The cursor is moved to
        the end of the inserted block.
        """
        if self._current_path is None:
            return False
        cursor = self._editor.textCursor()
        cursor.insertText(text)
        # Move cursor to the end of the inserted block so subsequent
        # insertions continue right after this one (intuitive behavior
        # when pasting multiple snippets in a row).
        cursor.movePosition(
            cursor.MoveOperation.EndOfBlock
            if hasattr(cursor, "MoveOperation")
            else 6  # QTextCursor.EndOfBlock (fallback if enum missing)
        )
        self._editor.setTextCursor(cursor)
        self._editor.document().setModified(True)
        return True

    # ----- Internal handlers -----------------------------------------------

    def _on_save_clicked(self) -> None:
        if self._current_path is None:
            # No file bound — silently ignore (toolbar button is also
            # disabled in this state, but Ctrl+S should be a no-op).
            return
        try:
            self._file_manager.write_file(
                self._current_path, self._editor.toPlainText()
            )
        except FileOperationError as exc:
            self.save_failed.emit(exc.message)
            return
        self._editor.document().setModified(False)
        # Notify the MainWindow so it can invalidate the analysis cache
        # (file content just changed on disk).
        self.file_saved.emit(self._current_path)
        self._update_buttons()

    def _on_ai_edit_clicked(self) -> None:
        if self._current_path is None:
            return
        instruction, ok = QInputDialog.getText(
            self,
            "Editar com IA",
            "O que você quer que a IA altere no arquivo?",
            QLineEdit.EchoMode.Normal,
            "",
        )
        if not ok:
            return
        instruction = instruction.strip()
        if not instruction:
            return
        self.ai_edit_requested.emit(self._current_path, instruction)

    def _update_buttons(self) -> None:
        """Enable/disable Save and Edit-with-AI based on whether a file is bound."""
        has_file = self._current_path is not None
        self._save_button.setEnabled(has_file)
        self._ai_edit_button.setEnabled(has_file)
