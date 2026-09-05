"""Integration test: editor AI-edit flow -> AIEditWorker -> preview -> apply."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication, QDialog

from app.services import AIEngine, MockAIProvider
from app.ui.main_window import MainWindow


_EDITED = 'def foo():\n    """New docstring."""\n    pass\n'


@pytest.fixture
def edit_engine() -> AIEngine:
    return AIEngine(MockAIProvider({"User instruction:": _EDITED}))


def _drain_threadpool() -> None:
    QThreadPool.globalInstance().waitForDone(5000)
    QApplication.processEvents()


def test_ai_edit_preview_apply_writes_file(qapp, tmp_path, edit_engine, monkeypatch) -> None:
    """Trigger ai_edit -> worker fills -> preview accepts -> file updated."""
    f = tmp_path / "x.py"
    f.write_text('def foo():\n    pass\n', encoding="utf-8")

    # Make the preview dialog auto-Accept (no real dialog popup).
    from app.ui import main_window as main_window_mod

    class _AutoAcceptDialog:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

        def exec(self) -> int:
            return int(QDialog.Accepted)

    monkeypatch.setattr(main_window_mod, "AIEditPreviewDialog", _AutoAcceptDialog)

    window = MainWindow(services={"ai_engine": edit_engine})
    window._file_explorer.file_selected.emit(str(f))
    _drain_threadpool()

    # Trigger the AI-edit flow with a fake instruction.
    window._code_editor.ai_edit_requested.emit(str(f), "add docstring")

    # Drain the worker.
    _drain_threadpool()

    # File should be updated with the new content.
    assert f.read_text(encoding="utf-8") == _EDITED
    # Editor should reflect the new content.
    assert window._code_editor.current_content() == _EDITED
    # And the file_type binding is preserved.
    assert window._code_editor.current_file_type() == "python"


def test_ai_edit_preview_cancel_leaves_file_untouched(
    qapp, tmp_path, edit_engine, monkeypatch
) -> None:
    """If the user cancels the preview, the file is NOT written."""
    f = tmp_path / "x.py"
    original = 'def foo():\n    pass\n'
    f.write_text(original, encoding="utf-8")

    from app.ui import main_window as main_window_mod

    class _AutoRejectDialog:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

        def exec(self) -> int:
            return int(QDialog.Rejected)

    monkeypatch.setattr(main_window_mod, "AIEditPreviewDialog", _AutoRejectDialog)

    window = MainWindow(services={"ai_engine": edit_engine})
    window._file_explorer.file_selected.emit(str(f))
    _drain_threadpool()

    window._code_editor.ai_edit_requested.emit(str(f), "add docstring")
    _drain_threadpool()

    # File untouched.
    assert f.read_text(encoding="utf-8") == original
    # Editor still shows the original.
    assert window._code_editor.current_content() == original
