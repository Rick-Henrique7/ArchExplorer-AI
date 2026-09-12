"""Entry editor dialog — create or edit a catalog entry (Change 006).

Used both for creating new entries (from :attr:`CatalogoPanel.new_entry_requested`)
and for editing existing ones (from :attr:`edit_entry_requested`).
The mode is determined by which ``__init__`` overload is used.

Public API:
- :attr:`MODE_CREATE` / :attr:`MODE_EDIT` constants
- :meth:`get_draft` — returns an :class:`EntryDraft` populated from the
  form, or ``None`` if the user cancelled.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.services import Entry


# --- Constants -----------------------------------------------------------

# Common language options for the dropdown. ``text`` is always present.
_LANGUAGE_CHOICES = (
    "text", "python", "javascript", "typescript", "java", "kotlin",
    "csharp", "cpp", "c", "go", "rust", "ruby", "php", "swift",
    "shell", "sql", "yaml", "json", "html", "css", "markdown",
)

# Suggested category options (the combo is also editable so the user
# can type anything; this list just gives quick picks).
_CATEGORY_CHOICES = (
    "patterns", "algorithms", "data-structures", "utilities",
    "snippets", "configs", "tests", "docs",
)

_TITLE_MAX = 200
_CODE_MAX = 100_000
_DESC_MAX = 10_000
_CATEGORY_MAX = 50


@dataclass(frozen=True)
class EntryDraft:
    """Snapshot of what the user typed, ready to hand to the service."""

    title: str
    code: str
    description: str | None
    language: str
    category: str | None
    tags: tuple[str, ...]
    origin_path: str | None
    origin_line: int | None
    is_public: bool


class EntryEditorDialog(QDialog):
    """Form dialog for entering/editing an :class:`Entry`.

    Validation:
    - ``title`` is required and ≤ 200 chars (matches service contract).
    - ``code`` is required and ≤ 100,000 chars.
    - ``language`` is required.
    - ``origin_line`` must be ≥ 1 if provided.
    - Validation runs on accept; the dialog refuses to close if any
      required field is empty.

    The dialog does NOT call the service directly — it just collects
    a :class:`EntryDraft` and the MainWindow calls
    :meth:`CatalogoService.create_entry` / :meth:`update_entry`. This
    keeps the dialog trivially testable (no DB / QApplication needed).
    """

    MODE_CREATE = "create"
    MODE_EDIT = "edit"

    def __init__(
        self,
        mode: str = MODE_CREATE,
        entry: Entry | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._mode = mode
        self._original = entry
        self.setWindowTitle(
            "Nova entrada" if mode == self.MODE_CREATE else "Editar entrada"
        )
        self.setMinimumSize(640, 480)
        self._build_ui()
        if mode == self.MODE_EDIT and entry is not None:
            self._populate_from_entry(entry)
        self._wire()

    # ----- UI construction -------------------------------------------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)

        form = QFormLayout()
        form.setContentsMargins(8, 8, 8, 8)
        form.setSpacing(6)

        self._title_input = QLineEdit(self)
        self._title_input.setMaxLength(_TITLE_MAX)
        self._title_input.setPlaceholderText("Ex: LRU cache em Python")
        form.addRow("Título *", self._title_input)

        self._language_combo = QComboBox(self)
        self._language_combo.setEditable(True)
        for lang in _LANGUAGE_CHOICES:
            self._language_combo.addItem(lang)
        self._language_combo.setCurrentText("text")
        form.addRow("Linguagem *", self._language_combo)

        self._category_combo = QComboBox(self)
        self._category_combo.setEditable(True)
        for cat in _CATEGORY_CHOICES:
            self._category_combo.addItem(cat)
        form.addRow("Categoria", self._category_combo)

        self._tags_input = QLineEdit(self)
        self._tags_input.setPlaceholderText(
            "Separe tags por vírgula (ex: cache, lru, python)"
        )
        form.addRow("Tags", self._tags_input)

        # Origin path + line (small composite row)
        origin_row = QWidget(self)
        origin_layout = QHBoxLayout(origin_row)
        origin_layout.setContentsMargins(0, 0, 0, 0)
        origin_layout.setSpacing(4)
        self._origin_path_input = QLineEdit(origin_row)
        self._origin_path_input.setPlaceholderText("Caminho do arquivo de origem (opcional)")
        self._origin_line_input = QLineEdit(origin_row)
        self._origin_line_input.setPlaceholderText("Linha")
        self._origin_line_input.setFixedWidth(80)
        origin_layout.addWidget(self._origin_path_input, stretch=1)
        origin_layout.addWidget(self._origin_line_input)
        form.addRow("Origem", origin_row)

        self._public_checkbox = QCheckBox(
            "Tornar esta entrada pública (exportável em JSON sem PII)", self
        )
        form.addRow("", self._public_checkbox)

        outer.addLayout(form)

        # Description: tabbed (edit + read-only preview-as-text placeholder)
        self._desc_tabs = QTabWidget(self)
        self._desc_input = QPlainTextEdit(self)
        self._desc_input.setPlaceholderText(
            "Descreva o problema, a abordagem e por que essa solução funciona."
        )
        self._desc_input.setMaximumHeight(160)
        self._desc_tabs.addTab(self._desc_input, "Descrição")
        outer.addWidget(self._desc_tabs)

        # Code editor
        code_label = QLabel("Código *", self)
        outer.addWidget(code_label)
        self._code_input = QPlainTextEdit(self)
        self._code_input.setPlaceholderText("Cole ou digite o código aqui…")
        # Monospace for readability.
        from PySide6.QtGui import QFont
        font = QFont("Consolas, Menlo, monospace", 10)
        self._code_input.setFont(font)
        outer.addWidget(self._code_input, stretch=1)

        # Dialog buttons
        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Salvar")
        self._buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        outer.addWidget(self._buttons)

    def _wire(self) -> None:
        self._buttons.accepted.connect(self._on_accept)
        self._buttons.rejected.connect(self.reject)

    # ----- Mode edit helpers -----------------------------------------------

    def _populate_from_entry(self, entry: Entry) -> None:
        self._title_input.setText(entry.title)
        idx = self._language_combo.findText(entry.language)
        if idx >= 0:
            self._language_combo.setCurrentIndex(idx)
        else:
            self._language_combo.setCurrentText(entry.language)
        if entry.category:
            idx = self._category_combo.findText(entry.category)
            if idx >= 0:
                self._category_combo.setCurrentIndex(idx)
            else:
                self._category_combo.setCurrentText(entry.category)
        if entry.tags:
            self._tags_input.setText(", ".join(entry.tags))
        self._desc_input.setPlainText(entry.description or "")
        self._code_input.setPlainText(entry.code)
        if entry.origin_path:
            self._origin_path_input.setText(entry.origin_path)
        if entry.origin_line is not None:
            self._origin_line_input.setText(str(entry.origin_line))
        self._public_checkbox.setChecked(entry.is_public)

    # ----- Accept handling -------------------------------------------------

    def _on_accept(self) -> None:
        """Validate; if all required fields are present, accept()."""
        title = self._title_input.text().strip()
        code = self._code_input.toPlainText()
        language = self._language_combo.currentText().strip()
        category = self._category_combo.currentText().strip() or None
        # ``toPlainText()`` is "" when the field is empty but truthy
        # when it contains whitespace — normalize whitespace-only to None.
        description_raw = self._desc_input.toPlainText()
        description = description_raw if description_raw.strip() else None
        origin_path = self._origin_path_input.text().strip() or None
        origin_line_raw = self._origin_line_input.text().strip()

        errors: list[str] = []
        if not title:
            errors.append("Título é obrigatório.")
        elif len(title) > _TITLE_MAX:
            errors.append(f"Título excede {_TITLE_MAX} caracteres.")
        if not code.strip():
            errors.append("Código é obrigatório.")
        elif len(code) > _CODE_MAX:
            errors.append(f"Código excede {_CODE_MAX} caracteres.")
        if not language:
            errors.append("Linguagem é obrigatória.")
        elif len(language) > 30:
            errors.append("Linguagem deve ter até 30 caracteres.")
        if category and len(category) > _CATEGORY_MAX:
            errors.append(f"Categoria deve ter até {_CATEGORY_MAX} caracteres.")
        if description and len(description) > _DESC_MAX:
            errors.append(f"Descrição excede {_DESC_MAX} caracteres.")

        origin_line: int | None = None
        if origin_line_raw:
            try:
                origin_line = int(origin_line_raw)
                if origin_line < 1:
                    errors.append("Linha de origem deve ser ≥ 1.")
            except ValueError:
                errors.append("Linha de origem deve ser um número inteiro.")

        if errors:
            # Show the first error in a quick non-modal label; tests
            # inspect ``_validation_error`` instead.
            self._validation_error = errors[0]
            return

        # Parse tags: split on commas, strip, drop empties. The service
        # will run the full normalize (lowercase, dedup, max 20).
        raw_tags = [t.strip() for t in self._tags_input.text().split(",")]
        raw_tags = [t for t in raw_tags if t]
        from app.services import normalize_tags
        tags = normalize_tags(raw_tags)

        self._draft = EntryDraft(
            title=title,
            code=code,
            description=description,
            language=language,
            category=category,
            tags=tags,
            origin_path=origin_path,
            origin_line=origin_line,
            is_public=self._public_checkbox.isChecked(),
        )
        self.accept()

    # ----- Public API ------------------------------------------------------

    def get_draft(self) -> EntryDraft | None:
        """Return the draft captured by accept(), or ``None`` if cancelled."""
        return getattr(self, "_draft", None)

    @property
    def validation_error(self) -> str | None:
        """Return the most recent validation error message (for tests)."""
        return getattr(self, "_validation_error", None)

    @property
    def mode(self) -> str:
        return self._mode
