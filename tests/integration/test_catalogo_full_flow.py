"""End-to-end tests for the catalog flow (Change 006 — Bloco J).

These exercise the wiring between MainWindow, LeftPanel, CatalogoPanel,
EntryEditorDialog and EntryPreviewPanel without needing a real AI
engine or a real Ollama instance.

Scenarios:
- Toggle left panel (Ctrl+1/2) swaps explorer <-> catalog and persists.
- Selecting an entry in the catalog renders it in the entry preview.
- +Nova opens the dialog, accept creates a new entry, list updates.
- Edit -> accept updates the entry, list refreshes.
- Delete (confirm + service) removes the entry, list refreshes.
- Insert into editor pastes code at cursor + bounces back to explorer.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QMessageBox

from app.services import CatalogoService, FileManager
from app.ui.left_panel import LeftPanelMode
from app.ui.main_window import MainWindow


@pytest.fixture
def settings(tmp_path):
    """Private INI file so QSettings doesn't pollute the registry."""
    return QSettings(str(tmp_path / "test.ini"), QSettings.Format.IniFormat)


@pytest.fixture
def catalog_service(tmp_path):
    return CatalogoService(db_path=tmp_path / "catalog.db")


@pytest.fixture
def window(qapp, settings, catalog_service) -> MainWindow:
    file_manager = FileManager()
    return MainWindow(
        services={"catalog_service": catalog_service},
        theme_manager=None,
        file_manager=file_manager,
    )


# ----- Mode toggle --------------------------------------------------------

def test_left_panel_starts_in_explorer_mode(window: MainWindow) -> None:
    """Default mode is the file tree (back-compat with Change 005)."""
    assert window.left_panel().current_mode() == LeftPanelMode.EXPLORER


def test_switch_to_catalog_via_left_panel(window: MainWindow) -> None:
    """Calling show_catalog() flips the panel and the right column."""
    window.left_panel().show_catalog()
    assert window.left_panel().current_mode() == LeftPanelMode.CATALOG
    # Right column: entry preview is now on top of the stack.
    assert window._right_stack.currentWidget() is window.entry_preview()


def test_switch_back_to_explorer_restores_visualizer(window: MainWindow) -> None:
    window.left_panel().show_catalog()
    window.left_panel().show_explorer()
    assert window._right_stack.currentWidget() is window._visualizer


def test_mode_persisted_in_qsettings(
    qapp, tmp_path, catalog_service, monkeypatch
) -> None:
    """Selecting catalog saves it to QSettings via the QSettings singleton."""
    captured: dict[str, str] = {}
    # Wrap QSettings().setValue so we can observe what was written.
    original_set = QSettings.setValue
    def spy_set(self, key, value):
        captured[key] = value
        return original_set(self, key, value)
    monkeypatch.setattr(QSettings, "setValue", spy_set)

    window = MainWindow(
        services={"catalog_service": catalog_service},
        file_manager=FileManager(),
    )
    window.left_panel().show_catalog()
    assert captured.get("workspace/left_panel_mode") == "catalog"


# ----- Selection -> preview ----------------------------------------------

def test_selecting_entry_renders_in_preview(window: MainWindow) -> None:
    entry = window._catalog_service.create_entry(
        title="LRU cache",
        code="class LRU: pass",
        language="python",
    )
    window._catalog_panel.refresh()
    # Simulate the selection: emit the signal as the panel would.
    window._catalog_panel.entry_selected.emit(entry.id)
    assert window.entry_preview().current_entry() is not None
    assert window.entry_preview().current_entry().id == entry.id


# ----- +Nova flow --------------------------------------------------------

def test_new_entry_dialog_creates_entry(
    window: MainWindow, catalog_service: CatalogoService, monkeypatch
) -> None:
    """Opening the dialog, filling it, and accepting creates an entry."""
    # Replace the dialog exec() so we don't open a real modal: pre-fill
    # and immediately accept via _on_accept.
    from app.ui import entry_editor_dialog as ed_mod

    captured: dict = {}

    def fake_exec(self):
        # Type the form directly.
        self._title_input.setText("Memoization")
        self._language_combo.setCurrentText("python")
        self._category_combo.setCurrentText("patterns")
        self._tags_input.setText("memo, decorator")
        self._code_input.setPlainText("def memo(f): pass")
        self._desc_input.setPlainText("Caches function results.")
        self._on_accept()
        return 1  # QDialog.Accepted

    monkeypatch.setattr(ed_mod.EntryEditorDialog, "exec", fake_exec)

    # Drive the signal.
    window._on_catalog_new_entry()

    entries = catalog_service.list_entries()
    assert len(entries) == 1
    assert entries[0].title == "Memoization"
    assert entries[0].tags == ("decorator", "memo")
    # Preview should be showing the new entry.
    assert window.entry_preview().current_entry() is not None
    assert window.entry_preview().current_entry().id == entries[0].id


def test_new_entry_cancelled_does_not_create(
    window: MainWindow, catalog_service: CatalogoService, monkeypatch
) -> None:
    from app.ui import entry_editor_dialog as ed_mod

    def fake_exec(self):
        return 0  # QDialog.Rejected

    monkeypatch.setattr(ed_mod.EntryEditorDialog, "exec", fake_exec)
    window._on_catalog_new_entry()
    assert catalog_service.list_entries() == []


# ----- Edit flow ---------------------------------------------------------

def test_edit_entry_dialog_updates_entry(
    window: MainWindow, catalog_service: CatalogoService, monkeypatch
) -> None:
    from app.ui import entry_editor_dialog as ed_mod

    entry = catalog_service.create_entry(
        title="Old title",
        code="x = 1",
        language="python",
    )
    window._catalog_panel.refresh()

    def fake_exec(self):
        # Mutate the title.
        self._title_input.setText("New title")
        self._on_accept()
        return 1

    monkeypatch.setattr(ed_mod.EntryEditorDialog, "exec", fake_exec)
    window._on_catalog_edit_entry(entry.id)

    refreshed = catalog_service.get_entry(entry.id)
    assert refreshed is not None
    assert refreshed.title == "New title"


# ----- Delete flow -------------------------------------------------------

def test_delete_entry_confirmed_removes(
    window: MainWindow, catalog_service: CatalogoService, monkeypatch
) -> None:
    entry = catalog_service.create_entry(
        title="Doomed", code="x = 1", language="python"
    )
    window._catalog_panel.refresh()

    # Always click Yes on the confirmation dialog.
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *a, **k: QMessageBox.StandardButton.Yes,
    )
    window._on_catalog_delete_entry(entry.id)

    assert catalog_service.get_entry(entry.id) is None
    assert window.entry_preview().current_entry() is None


def test_delete_entry_declined_keeps(
    window: MainWindow, catalog_service: CatalogoService, monkeypatch
) -> None:
    entry = catalog_service.create_entry(
        title="Kept", code="x = 1", language="python"
    )
    window._catalog_panel.refresh()

    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *a, **k: QMessageBox.StandardButton.No,
    )
    window._on_catalog_delete_entry(entry.id)

    assert catalog_service.get_entry(entry.id) is not None


# ----- Insert into editor -----------------------------------------------

def test_insert_into_editor_appends_code_and_switches_mode(
    window: MainWindow, catalog_service: CatalogoService, tmp_path
) -> None:
    """Inserting a snippet pastes code at cursor and bounces to Explorer."""
    # Open a file in the editor.
    target = tmp_path / "scratch.py"
    target.write_text("# header\n", encoding="utf-8")
    window._code_editor.set_content(
        target.read_text(encoding="utf-8"),
        path=str(target),
        file_type="python",
    )
    # Start in catalog mode (so we can verify the bounce-back).
    window.left_panel().show_catalog()
    # Create an entry and click the insert button.
    entry = catalog_service.create_entry(
        title="Snippet",
        code="# pasted snippet\n",
        language="python",
    )
    window._catalog_panel.refresh()
    window._on_catalog_insert_into_editor(entry.id)
    # The editor now has the snippet appended.
    content = window._code_editor.current_content()
    assert "# pasted snippet" in content
    # And we bounced back to the explorer so the user sees the editor.
    assert window.left_panel().current_mode() == LeftPanelMode.EXPLORER


def test_insert_into_editor_without_open_file_shows_message(
    window: MainWindow, catalog_service: CatalogoService, monkeypatch
) -> None:
    """Without an open file, the user gets an informational message
    instead of a silent failure."""
    entry = catalog_service.create_entry(
        title="Snippet", code="x = 1", language="python"
    )
    captured: list[str] = []
    monkeypatch.setattr(
        QMessageBox, "information",
        lambda parent, title, msg: captured.append(msg) or QMessageBox.StandardButton.Ok,
    )
    # No file open.
    window._on_catalog_insert_into_editor(entry.id)
    assert len(captured) == 1
    assert "Abra um arquivo" in captured[0]


# ----- End-to-end: create -> search -> select -> delete ------------------

def test_full_lifecycle_create_search_select_delete(
    window: MainWindow, catalog_service: CatalogoService, monkeypatch
) -> None:
    """Realistic flow: create, search, select, delete."""
    from app.ui import entry_editor_dialog as ed_mod

    # 1. Create an entry.
    def fake_create(self):
        self._title_input.setText("LRU cache")
        self._language_combo.setCurrentText("python")
        self._category_combo.setCurrentText("patterns")
        self._tags_input.setText("cache, lru")
        self._code_input.setPlainText("class LRU: pass")
        self._desc_input.setPlainText("Least-recently-used.")
        self._on_accept()
        return 1
    monkeypatch.setattr(ed_mod.EntryEditorDialog, "exec", fake_create)
    window._on_catalog_new_entry()
    assert len(catalog_service.list_entries()) == 1

    # 2. Search for it via FTS5.
    results = catalog_service.search_entries("LRU")
    assert len(results) == 1

    # 3. Select it.
    entry_id = results[0].id
    window._catalog_panel.entry_selected.emit(entry_id)
    assert window.entry_preview().current_entry() is not None

    # 4. Delete it (Yes on confirm).
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *a, **k: QMessageBox.StandardButton.Yes,
    )
    window._on_catalog_delete_entry(entry_id)
    assert catalog_service.get_entry(entry_id) is None
    assert window.entry_preview().current_entry() is None
