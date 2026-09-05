"""Preview dialog shown before applying an AI-suggested file edit (Change 005)."""

from __future__ import annotations

import difflib
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class AIEditPreviewDialog(QDialog):
    """Modal preview of an AI-suggested edit with Apply / Cancel buttons.

    The user reviews a unified diff of the original vs the proposed new
    content and chooses to apply (write the new content to disk) or
    cancel (do nothing). The dialog returns ``QDialog.Accepted`` when
    the user applies and ``QDialog.Rejected`` on cancel / window close.
    """

    def __init__(
        self,
        *,
        original_content: str,
        new_content: str,
        file_path: str,
        instruction: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Preview da edição com IA")
        self.resize(820, 600)
        # Make the dialog modal so the user must explicitly apply / cancel.
        self.setModal(True)
        self._new_content = new_content
        self._file_path = file_path
        self._build_ui(original_content, instruction)

    def _build_ui(self, original_content: str, instruction: str) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # --- Header --------------------------------------------------------
        header = QLabel(
            f"<b>Arquivo:</b> {Path(self._file_path).name}<br>"
            f"<b>Instrução:</b> {instruction}"
        )
        header.setWordWrap(True)
        layout.addWidget(header)

        # --- Diff viewer ---------------------------------------------------
        diff_text = self._make_diff(original_content, self._new_content, self._file_path)
        diff_view = QPlainTextEdit(self)
        diff_view.setReadOnly(True)
        diff_view.setFont(QFont("Consolas, Menlo, monospace", 10))
        diff_view.setPlainText(diff_text)
        layout.addWidget(diff_view, stretch=1)

        # --- Action buttons ------------------------------------------------
        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self._cancel_button = QPushButton("Cancelar", self)
        self._cancel_button.clicked.connect(self.reject)
        self._apply_button = QPushButton("Aplicar", self)
        self._apply_button.setDefault(True)
        self._apply_button.clicked.connect(self.accept)
        button_row.addWidget(self._cancel_button)
        button_row.addWidget(self._apply_button)
        layout.addLayout(button_row)

    def new_content(self) -> str:
        """Return the proposed new content (caller writes this to disk)."""
        return self._new_content

    @staticmethod
    def _make_diff(original: str, new: str, file_path: str) -> str:
        """Return a unified diff between ``original`` and ``new``.

        Falls back to a plain-text dump if difflib produces nothing
        (e.g. when the two contents are identical).
        """
        diff = list(
            difflib.unified_diff(
                original.splitlines(keepends=True),
                new.splitlines(keepends=True),
                fromfile=f"a/{Path(file_path).name}",
                tofile=f"b/{Path(file_path).name}",
                n=3,
            )
        )
        if not diff:
            return "(sem alterações — a IA devolveu o mesmo conteúdo)"
        return "".join(diff)
