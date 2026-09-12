"""Personal catalog panel — search box, filters, and list view (Change 006).

The catalog is the user's "second brain" of solutions/patterns. This
panel is the entry point: a search box at the top, two filter combos
(category / language), a tag filter row, and a list view of the
matching entries.

Architecture
------------

- :class:`CatalogoPanel` — the QWidget shell with toolbar + filters +
  list view. Emits high-level signals (``entry_selected``, etc.) to
  the MainWindow.
- :class:`CatalogoListModel` — a small ``QAbstractListModel`` that
  holds the currently displayed :class:`Entry` list. Exposes three
  roles so the view can render title / language / tags without
  subclassing a delegate.
- Search debounce: 200ms via ``QTimer.singleShot`` so each keystroke
  doesn't fire an FTS5 query.
"""

from __future__ import annotations

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QTimer,
    Qt,
    Signal,
)
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QPushButton,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from app.services import CatalogoService, Entry


# Debounce window for the search box — small enough to feel snappy,
# large enough that an FTS5 query is not fired per keystroke.
_SEARCH_DEBOUNCE_MS = 200


class CatalogoListModel(QAbstractListModel):
    """List model for the catalog entries currently visible.

    Roles:
    - ``DisplayRole`` -> ``entry.title``
    - ``EntryRole``   -> the :class:`Entry` itself (for the view to
      pull language/tags/category without extra columns)
    - ``IdRole``      -> the integer ``entry.id`` (so the panel can
      emit ``entry_selected(entry_id)`` without re-indexing)
    """

    EntryRole = Qt.ItemDataRole.UserRole + 1
    IdRole = Qt.ItemDataRole.UserRole + 2

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._entries: list[Entry] = []

    def set_entries(self, entries: list[Entry]) -> None:
        """Replace the entire visible list."""
        self.beginResetModel()
        self._entries = list(entries)
        self.endResetModel()

    def entries(self) -> list[Entry]:
        """Return the currently held entries (read-only copy)."""
        return list(self._entries)

    def entry_at(self, row: int) -> Entry | None:
        if 0 <= row < len(self._entries):
            return self._entries[row]
        return None

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008, N802
        if parent.isValid():
            return 0
        return len(self._entries)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        entry = self._entries[index.row()]
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return entry.title
        if role == self.EntryRole:
            return entry
        if role == self.IdRole:
            return entry.id
        return None


class CatalogoPanel(QWidget):
    """Search + filter + list view for the personal catalog.

    Signals (consumed by :class:`MainWindow`):
    - :attr:`entry_selected` — emitted with the entry id when the user
      picks one in the list (single click or current-item change).
    - :attr:`insert_into_editor_requested` — emitted when the user
      clicks "Inserir no editor" on a selected entry.
    - :attr:`new_entry_requested` — emitted when the user clicks
      "+Nova" (MainWindow opens :class:`EntryEditorDialog`).
    - :attr:`edit_entry_requested` — emitted when the user clicks
      "Editar" on a selected entry.
    - :attr:`delete_entry_requested` — emitted when the user clicks
      "Excluir" on a selected entry.

    Public API used by the MainWindow:
    - :meth:`refresh` — re-runs the current query and rebuilds the list.
    - :meth:`service` — accessor for the injected service.
    """

    entry_selected = Signal(int)                  # entry id
    insert_into_editor_requested = Signal(int)    # entry id
    new_entry_requested = Signal()
    edit_entry_requested = Signal(int)            # entry id
    delete_entry_requested = Signal(int)          # entry id

    # Filter combo sentinel for "all"
    _ALL_SENTINEL = "Todas"

    def __init__(
        self,
        catalogo_service: CatalogoService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = catalogo_service
        self._current_query: str = ""
        self._current_category: str | None = None
        self._current_language: str | None = None
        self._current_tag: str | None = None
        self._build_ui()
        self._wire()
        # Populate the filter combos from whatever data the service has
        # already, then do an initial refresh.
        self._refresh_filters()
        self.refresh()

    def _build_ui(self) -> None:
        """Construct toolbar + search row + filters + list view."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- Toolbar (action buttons) -----------------------------------
        toolbar = QToolBar(self)
        toolbar.setMovable(False)

        self._new_button = QPushButton("+Nova", self)
        self._new_button.setToolTip("Criar uma nova entrada no catálogo")
        self._new_button.clicked.connect(self.new_entry_requested.emit)
        toolbar.addWidget(self._new_button)

        self._edit_button = QPushButton("Editar", self)
        self._edit_button.setToolTip("Editar a entrada selecionada")
        self._edit_button.clicked.connect(self._on_edit_clicked)
        toolbar.addWidget(self._edit_button)

        self._delete_button = QPushButton("Excluir", self)
        self._delete_button.setToolTip("Excluir a entrada selecionada")
        self._delete_button.clicked.connect(self._on_delete_clicked)
        toolbar.addWidget(self._delete_button)

        self._insert_button = QPushButton("Inserir no editor", self)
        self._insert_button.setToolTip(
            "Inserir o código da entrada selecionada no editor aberto"
        )
        self._insert_button.clicked.connect(self._on_insert_clicked)
        toolbar.addWidget(self._insert_button)

        tb_container = QWidget(self)
        tb_layout = QHBoxLayout(tb_container)
        tb_layout.setContentsMargins(4, 4, 4, 4)
        tb_layout.addWidget(toolbar)
        tb_layout.addStretch(1)
        layout.addWidget(tb_container)

        # --- Search + filter row ----------------------------------------
        controls = QWidget(self)
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(4, 4, 4, 4)
        controls_layout.setSpacing(4)

        self._search_input = QLineEdit(controls)
        self._search_input.setPlaceholderText(
            "Buscar por título, descrição ou código…"
        )
        self._search_input.setClearButtonEnabled(True)
        controls_layout.addWidget(self._search_input, stretch=2)

        self._category_combo = QComboBox(controls)
        self._category_combo.setToolTip("Filtrar por categoria")
        self._category_combo.addItem(self._ALL_SENTINEL)
        controls_layout.addWidget(self._category_combo, stretch=1)

        self._language_combo = QComboBox(controls)
        self._language_combo.setToolTip("Filtrar por linguagem")
        self._language_combo.addItem(self._ALL_SENTINEL)
        controls_layout.addWidget(self._language_combo, stretch=1)
        layout.addWidget(controls)

        # --- List view ---------------------------------------------------
        self._model = CatalogoListModel(self)
        self._list = QListView(self)
        self._list.setModel(self._model)
        self._list.setSelectionMode(QListView.SelectionMode.SingleSelection)
        self._list.setEditTriggers(QListView.EditTrigger.NoEditTriggers)
        # No auto-emit on click; the panel emits only when the
        # *selection* actually changes (so the user can browse without
        # the preview flickering on every mouse move).
        self._list.setMinimumHeight(120)
        layout.addWidget(self._list, stretch=1)

        # --- Status bar (counts) ----------------------------------------
        self._status = QLabel(self)
        self._status.setContentsMargins(4, 2, 4, 2)
        layout.addWidget(self._status)

        # Initial button state: disabled until a file is bound.
        self._update_action_buttons()

    def _wire(self) -> None:
        # Search input -> debounced refresh.
        self._search_input.textChanged.connect(self._on_search_text_changed)
        self._search_debounce = QTimer(self)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(_SEARCH_DEBOUNCE_MS)
        self._search_debounce.timeout.connect(self.refresh)

        # Filter combos -> immediate refresh (no debounce; these are
        # discrete clicks, not a stream of keystrokes).
        self._category_combo.currentIndexChanged.connect(self._on_filter_changed)
        self._language_combo.currentIndexChanged.connect(self._on_filter_changed)

        # Selection change -> emit entry_selected.
        sel_model = self._list.selectionModel()
        assert sel_model is not None
        sel_model.currentRowChanged.connect(self._on_selection_changed)

    # ----- Public API -------------------------------------------------------

    def service(self) -> CatalogoService | None:
        """Return the injected service (or ``None`` if not provided)."""
        return self._service

    def set_service(self, service: CatalogoService) -> None:
        """Replace the service and refresh (used when tests inject after ctor)."""
        self._service = service
        self._refresh_filters()
        self.refresh()

    def selected_entry_id(self) -> int | None:
        """Return the currently selected entry id (or ``None``)."""
        idx = self._list.currentIndex()
        if not idx.isValid():
            return None
        entry = self._model.entry_at(idx.row())
        return entry.id if entry is not None else None

    def refresh(self) -> None:
        """Run the current filters + query and rebuild the list."""
        if self._service is None:
            self._model.set_entries([])
            self._update_status(0)
            return
        # When the query is empty, list_entries handles it correctly;
        # when non-empty, the FTS path takes over.
        query = self._current_query.strip()
        if query:
            entries = self._service.search_entries(query)
        else:
            entries = self._service.list_entries(
                category=self._current_category,
                language=self._current_language,
            )
        self._model.set_entries(entries)
        self._update_status(len(entries))
        # Selection is now stale; clear it so the preview hides.
        self._list.clearSelection()
        self._list.setCurrentIndex(QModelIndex())
        self._update_action_buttons()

    def current_query(self) -> str:
        return self._current_query

    def current_category(self) -> str | None:
        return self._current_category

    def current_language(self) -> str | None:
        return self._current_language

    # ----- Internal handlers -----------------------------------------------

    def _on_search_text_changed(self, text: str) -> None:
        self._current_query = text
        # Restart the debounce timer on every keystroke.
        self._search_debounce.start()

    def _on_filter_changed(self, _index: int) -> None:
        self._current_category = self._combo_value(self._category_combo)
        self._current_language = self._combo_value(self._language_combo)
        self.refresh()

    def _on_selection_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        if not current.isValid():
            self._update_action_buttons()
            return
        entry = self._model.entry_at(current.row())
        if entry is not None:
            self.entry_selected.emit(entry.id)
        self._update_action_buttons()

    def _on_edit_clicked(self) -> None:
        entry_id = self.selected_entry_id()
        if entry_id is not None:
            self.edit_entry_requested.emit(entry_id)

    def _on_delete_clicked(self) -> None:
        entry_id = self.selected_entry_id()
        if entry_id is not None:
            self.delete_entry_requested.emit(entry_id)

    def _on_insert_clicked(self) -> None:
        entry_id = self.selected_entry_id()
        if entry_id is not None:
            self.insert_into_editor_requested.emit(entry_id)

    def _refresh_filters(self) -> None:
        """Repopulate category/language combos from the service."""
        # Preserve current selection if it still exists.
        prev_cat = self._current_category
        prev_lang = self._current_language

        self._category_combo.blockSignals(True)
        self._language_combo.blockSignals(True)
        try:
            self._category_combo.clear()
            self._category_combo.addItem(self._ALL_SENTINEL)
            self._language_combo.clear()
            self._language_combo.addItem(self._ALL_SENTINEL)
            if self._service is not None:
                for cat in self._service.list_categories():
                    self._category_combo.addItem(cat)
                for lang in self._service.list_languages():
                    self._language_combo.addItem(lang)
            # Re-select previous values (or sentinel).
            self._select_combo(self._category_combo, prev_cat)
            self._select_combo(self._language_combo, prev_lang)
        finally:
            self._category_combo.blockSignals(False)
            self._language_combo.blockSignals(False)

    def _select_combo(self, combo: QComboBox, value: str | None) -> None:
        if value is None:
            combo.setCurrentIndex(0)
            return
        idx = combo.findText(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        else:
            combo.setCurrentIndex(0)

    def _combo_value(self, combo: QComboBox) -> str | None:
        text = combo.currentText()
        if not text or text == self._ALL_SENTINEL:
            return None
        return text

    def _update_action_buttons(self) -> None:
        has_selection = self.selected_entry_id() is not None
        self._edit_button.setEnabled(has_selection)
        self._delete_button.setEnabled(has_selection)
        self._insert_button.setEnabled(has_selection)

    def _update_status(self, count: int) -> None:
        if count == 0:
            self._status.setText("Nenhuma entrada")
        elif count == 1:
            self._status.setText("1 entrada")
        else:
            self._status.setText(f"{count} entradas")
