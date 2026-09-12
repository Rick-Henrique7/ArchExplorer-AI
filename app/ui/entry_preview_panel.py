"""Right column for the catalog mode: render a single Entry (Change 006).

When the catalog is active, this panel replaces the AI visualizer's
"analyze a file" purpose with "show one saved solution". It reuses the
same :func:`app.ui.html_template.build_html_template` renderer so the
look-and-feel matches the AI analysis panel (markdown + Mermaid for any
diagrams in the description).

Public API:
- :meth:`show_entry` — render an :class:`Entry` (or its id + service)
- :meth:`clear` — return to the empty/idle state
- :meth:`current_entry` — the entry currently displayed (or ``None``)

Signals (forwarded to MainWindow):
- :attr:`insert_into_editor` — user clicked "Inserir no editor"
- :attr:`edit_entry` — user clicked "Editar"
- :attr:`delete_entry` — user clicked "Excluir"
"""

from __future__ import annotations

import datetime as _dt

from PySide6.QtCore import Signal
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from app.services import CatalogoService, Entry
from app.ui.html_template import build_html_template


def _format_date(value: _dt.datetime) -> str:
    """ISO date in YYYY-MM-DD for the metadata block."""
    return value.strftime("%Y-%m-%d")


def _render_entry_markdown(entry: Entry) -> str:
    """Build the markdown payload for ``entry`` (no theme concerns here).

    Title, metadata table, description (markdown), and a fenced code
    block for the snippet. The template renderer will wrap this in the
    proper HTML chrome.
    """
    parts: list[str] = []
    parts.append(f"# {entry.title}\n")

    # Metadata table (compact, two columns)
    rows: list[tuple[str, str]] = [
        ("Linguagem", entry.language or "—"),
        ("Categoria", entry.category or "—"),
    ]
    if entry.tags:
        rows.append(("Tags", ", ".join(f"`{t}`" for t in entry.tags)))
    if entry.origin_path:
        origin = entry.origin_path
        if entry.origin_line is not None:
            origin = f"{origin}:{entry.origin_line}"
        rows.append(("Origem", origin))
    rows.append(("Criado em", _format_date(entry.created_at)))
    rows.append(("Atualizado em", _format_date(entry.updated_at)))
    if entry.is_public:
        rows.append(("Visibilidade", "Pública"))

    md_table = "| Campo | Valor |\n|---|---|\n"
    for k, v in rows:
        # Escape pipes inside values so the table stays valid.
        safe_v = v.replace("|", "\\|")
        md_table += f"| {k} | {safe_v} |\n"
    parts.append(md_table)

    if entry.description:
        parts.append("\n## Descrição\n")
        parts.append(entry.description + "\n")

    parts.append("\n## Código\n")
    parts.append(f"```{entry.language or 'text'}\n{entry.code}\n```\n")

    return "\n".join(parts)


class EntryPreviewPanel(QWidget):
    """Single-entry preview shown in the right column when catalog mode is active.

    The panel is intentionally simple: a title header, the markdown
    render, and a small action toolbar. State is held in
    :attr:`_current_entry` so the panel can be queried later (the
    MainWindow uses it to know which entry's "Inserir no editor"
    should target).
    """

    insert_into_editor = Signal(int)   # entry id
    edit_entry = Signal(int)           # entry id
    delete_entry = Signal(int)         # entry id

    _EMPTY_MESSAGE = (
        "<p style='text-align:center; padding:2em; opacity:0.7;'>"
        "Selecione uma entrada na lista à esquerda para visualizar."
        "</p>"
    )

    def __init__(
        self,
        service: CatalogoService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._current_entry: Entry | None = None
        self._current_theme: str = "dark"
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- Action toolbar -----------------------------------------------
        toolbar = QToolBar(self)
        toolbar.setMovable(False)

        self._insert_button = QPushButton("Inserir no editor", self)
        self._insert_button.setToolTip(
            "Inserir o código desta entrada no editor aberto"
        )
        self._insert_button.clicked.connect(self._on_insert_clicked)
        toolbar.addWidget(self._insert_button)

        self._edit_button = QPushButton("Editar", self)
        self._edit_button.setToolTip("Editar esta entrada")
        self._edit_button.clicked.connect(self._on_edit_clicked)
        toolbar.addWidget(self._edit_button)

        self._delete_button = QPushButton("Excluir", self)
        self._delete_button.setToolTip("Excluir esta entrada")
        self._delete_button.clicked.connect(self._on_delete_clicked)
        toolbar.addWidget(self._delete_button)

        tb_container = QWidget(self)
        tb_layout = QHBoxLayout(tb_container)
        tb_layout.setContentsMargins(4, 4, 4, 4)
        tb_layout.addWidget(toolbar)
        tb_layout.addStretch(1)
        layout.addWidget(tb_container)

        # --- Title label --------------------------------------------------
        self._title_label = QLabel(self)
        self._title_label.setContentsMargins(8, 8, 8, 0)
        self._title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(self._title_label)

        # --- Markdown view ------------------------------------------------
        self._view = QWebEngineView(self)
        layout.addWidget(self._view, stretch=1)

        # Initial state: empty, buttons disabled.
        self._set_action_buttons_enabled(False)
        self._render_empty()

    # ----- Public API -------------------------------------------------------

    def set_theme(self, theme: str) -> None:
        """Update the markdown render theme; re-render the current entry."""
        self._current_theme = theme
        if self._current_entry is not None:
            self._render_entry(self._current_entry)

    def show_entry(self, entry: Entry) -> None:
        """Render ``entry`` and enable the action buttons."""
        self._current_entry = entry
        self._title_label.setText(entry.title)
        self._render_entry(entry)
        self._set_action_buttons_enabled(True)

    def show_entry_by_id(self, entry_id: int) -> bool:
        """Look up ``entry_id`` via the service and render it.

        Returns ``True`` if the entry was found, ``False`` otherwise.
        """
        if self._service is None:
            return False
        entry = self._service.get_entry(entry_id)
        if entry is None:
            return False
        self.show_entry(entry)
        return True

    def clear(self) -> None:
        """Forget the current entry and return to the empty state."""
        self._current_entry = None
        self._title_label.setText("")
        self._render_empty()
        self._set_action_buttons_enabled(False)

    def current_entry(self) -> Entry | None:
        """Return the entry currently displayed (or ``None``)."""
        return self._current_entry

    def service(self) -> CatalogoService | None:
        """Accessor for the injected service (test seam)."""
        return self._service

    # ----- Internal ---------------------------------------------------------

    def _render_entry(self, entry: Entry) -> None:
        markdown = _render_entry_markdown(entry)
        html = build_html_template(markdown, theme=self._current_theme)
        self._view.setHtml(html)

    def _render_empty(self) -> None:
        # Minimal HTML so the panel has a consistent look in the empty
        # state (matches the visualizer's idle styling).
        html = build_html_template(self._EMPTY_MESSAGE, theme=self._current_theme)
        self._view.setHtml(html)

    def _set_action_buttons_enabled(self, enabled: bool) -> None:
        self._insert_button.setEnabled(enabled)
        self._edit_button.setEnabled(enabled)
        self._delete_button.setEnabled(enabled)

    def _on_insert_clicked(self) -> None:
        if self._current_entry is not None:
            self.insert_into_editor.emit(self._current_entry.id)

    def _on_edit_clicked(self) -> None:
        if self._current_entry is not None:
            self.edit_entry.emit(self._current_entry.id)

    def _on_delete_clicked(self) -> None:
        if self._current_entry is not None:
            self.delete_entry.emit(self._current_entry.id)
