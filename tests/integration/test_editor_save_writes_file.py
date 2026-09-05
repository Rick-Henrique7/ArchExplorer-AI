"""Integration test: editor Save flow -> FileManager.write_file -> disk updated."""

from __future__ import annotations

import pytest

from app.services import FileManager
from app.ui.main_window import MainWindow


def test_editor_save_writes_file_to_disk(qapp, tmp_path) -> None:
    """End-to-end: file selected -> editor populated -> user edits -> save -> disk updated."""
    from PySide6.QtCore import QThreadPool
    from PySide6.QtWidgets import QApplication

    f = tmp_path / "x.py"
    f.write_text("old = 1\n", encoding="utf-8")

    # A mock engine that returns predictable content for analyze.
    from app.services import AIEngine, MockAIProvider
    engine = AIEngine(MockAIProvider({"Patterns": "## Patterns\n- None"}))

    window = MainWindow(services={"ai_engine": engine})
    # Open the file (this also binds the path on the editor + visualizer).
    window._file_explorer.file_selected.emit(str(f))
    QThreadPool.globalInstance().waitForDone(5000)
    QApplication.processEvents()
    assert window._code_editor.current_content() == "old = 1\n"

    # Simulate the user editing the content.
    window._code_editor.set_content("new = 2\n", path=str(f), file_type="python")
    window._code_editor._editor.setPlainText("new = 2\n")
    # Manually mark the document dirty (setPlainText alone doesn't flag it).
    window._code_editor._editor.document().setModified(True)
    assert window._code_editor.is_dirty() is True

    # Click Save.
    window._code_editor._on_save_clicked()

    # The file on disk now has the new content.
    assert f.read_text(encoding="utf-8") == "new = 2\n"
    # And the dirty flag is cleared.
    assert window._code_editor.is_dirty() is False


def test_editor_save_failure_surfaces_in_visualizer(qapp, tmp_path) -> None:
    """If FileManager.write_file raises, visualizer.show_error receives the message."""
    from PySide6.QtCore import QThreadPool
    from PySide6.QtWidgets import QApplication

    f = tmp_path / "x.py"
    f.write_text("old", encoding="utf-8")

    # Use a FileManager that always raises on write_file.
    class _BoomFM(FileManager):
        def write_file(self, path, content):  # type: ignore[override]
            from app.services import FileOperationError
            raise FileOperationError("disk full", path=path)

    window = MainWindow(services={"ai_engine": None}, file_manager=_BoomFM())
    window._file_explorer.file_selected.emit(str(f))
    QThreadPool.globalInstance().waitForDone(5000)
    QApplication.processEvents()

    # Force save — the broken FileManager will raise and the panel must
    # forward the message to the visualizer.
    window._code_editor._on_save_clicked()

    assert window._visualizer.last_error is not None
    assert "Falha ao salvar" in window._visualizer.last_error
    assert "disk full" in window._visualizer.last_error
