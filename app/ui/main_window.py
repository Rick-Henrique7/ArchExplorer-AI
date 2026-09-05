"""Main window — three horizontal panels + menu bar + Change 005 wiring."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from PySide6.QtCore import QSettings, Qt, QThreadPool, Slot
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (
    QDialog,
    QMainWindow,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.services import FileManager
from app.ui.ai_edit_preview import AIEditPreviewDialog
from app.ui.analysis_worker import AIEditWorker, AnalysisWorker, ChatWorker
from app.ui.code_editor import CodeEditorPanel
from app.ui.file_explorer import FileExplorerPanel
from app.ui.file_inspector import inspect_file
from app.ui.theme import Theme, ThemeManager
from app.ui.visualizer import VisualizerPanel


# QSettings keys (single source of truth for the registry layout).
_SETTINGS_ROOT_DIR = "workspace/root_dir"


class MainWindow(QMainWindow):
    """ArchExplorer AI main window.

    Hosts three resizable panels in a horizontal ``QSplitter`` plus a
    menu bar with the View > Theme switcher.

    Dependency injection:
    - ``services`` (dict): expected key ``"ai_engine"``. Optional fallback.
    - ``theme_manager``: optional; if provided, the View menu is built
      and the current theme is applied to incoming markdown renders.
    - ``file_manager``: optional; if provided, the explorer and editor
      share the same instance. A new one is created otherwise.

    QSettings persistence (Change 005):
    - The explorer's root directory is saved on every change and
      restored on construction.

    New signal wiring (Change 005):
    - ``editor.save_failed`` -> ``visualizer.show_error``
    - ``editor.ai_edit_requested`` -> :class:`AIEditWorker` + preview dialog
    - ``visualizer.chat_requested`` -> :class:`ChatWorker` + add_chat_response
    - ``explorer.root_changed`` -> QSettings persistence
    """

    WINDOW_TITLE: str = "ArchExplorer AI"
    DEFAULT_SIZE: tuple[int, int] = (1100, 700)
    SPLITTER_STRETCH: tuple[int, int, int] = (25, 45, 30)

    def __init__(
        self,
        services: dict[str, Any] | None = None,
        theme_manager: ThemeManager | None = None,
        file_manager: FileManager | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._services: dict[str, Any] = services if services is not None else {}
        self._theme_manager = theme_manager
        self._file_manager = file_manager or FileManager()
        # Pending edit context (set by ai_edit_requested, consumed after
        # the worker finishes — we keep it on self because the worker's
        # finished signal carries only the new content, not the path).
        self._pending_edit_path: str | None = None
        self._pending_edit_original: str | None = None
        self._pending_edit_instruction: str | None = None
        self._build_ui()
        self._wire()
        if self._theme_manager is not None:
            self._build_menu()

    def _build_ui(self) -> None:
        self.setWindowTitle(self.WINDOW_TITLE)
        self.resize(*self.DEFAULT_SIZE)

        # Restore last-used root from QSettings, falling back to cwd.
        settings = QSettings()
        saved_root = settings.value(_SETTINGS_ROOT_DIR, "", type=str)
        if saved_root and Path(saved_root).is_dir():
            initial_root = Path(saved_root)
        else:
            initial_root = Path(os.getcwd())

        self._file_explorer = FileExplorerPanel(
            root=initial_root, file_manager=self._file_manager, parent=self
        )
        self._code_editor = CodeEditorPanel(
            file_manager=self._file_manager, parent=self
        )
        self._visualizer = VisualizerPanel(self)

        self._splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self._splitter.addWidget(self._file_explorer)
        self._splitter.addWidget(self._code_editor)
        self._splitter.addWidget(self._visualizer)
        for i, stretch in enumerate(self.SPLITTER_STRETCH):
            self._splitter.setStretchFactor(i, stretch)
        self._splitter.setChildrenCollapsible(False)

        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._splitter)
        self.setCentralWidget(central)

        # Tell the visualizer the active theme so its internal chat
        # renders use the right body colors.
        if self._theme_manager is not None:
            self._visualizer.set_theme(self._theme_manager.effective().value)

    def _wire(self) -> None:
        # File selection -> editor + visualizer file context + AI analysis.
        self._file_explorer.file_selected.connect(self._on_file_selected)
        # Root changes -> QSettings.
        self._file_explorer.root_changed.connect(self._on_root_changed)
        # Editor save / AI-edit flows.
        self._code_editor.save_failed.connect(self._on_editor_save_failed)
        self._code_editor.ai_edit_requested.connect(self._on_ai_edit_requested)
        # Visualizer chat -> background worker -> add_chat_response.
        self._visualizer.chat_requested.connect(self._on_chat_requested)

    def _build_menu(self) -> None:
        """Build the menu bar with the View > Theme switcher."""
        menubar = self.menuBar()
        view_menu = menubar.addMenu("&View")
        theme_menu = view_menu.addMenu("&Theme")

        # Exclusive group so only one theme is selected at a time.
        self._theme_action_group = QActionGroup(self)
        self._theme_action_group.setExclusive(True)

        self._theme_actions: dict[Theme, QAction] = {}
        for theme in (Theme.DARK, Theme.LIGHT, Theme.SYSTEM):
            action = QAction(theme.value.title(), self)
            action.setCheckable(True)
            action.setChecked(theme == self._theme_manager.current())
            action.triggered.connect(
                lambda _checked=False, t=theme: self._on_theme_changed(t)
            )
            self._theme_action_group.addAction(action)
            self._theme_actions[theme] = action
            theme_menu.addAction(action)

        view_menu.addSeparator()
        toggle_action = QAction("&Toggle Theme", self)
        toggle_action.setShortcut(QKeySequence("Ctrl+Shift+T"))
        toggle_action.triggered.connect(self._on_toggle_theme)
        view_menu.addAction(toggle_action)

    # ----- Theme handlers ---------------------------------------------------

    @Slot(Theme)
    def _on_theme_changed(self, theme: Theme) -> None:
        self._theme_manager.apply(theme)
        effective = self._theme_manager.effective().value
        self._visualizer.set_theme(effective)
        if self._visualizer.last_markdown is not None:
            self._visualizer.show_markdown(self._visualizer.last_markdown, theme=effective)
        for t, action in self._theme_actions.items():
            action.setChecked(t == self._theme_manager.current())

    @Slot()
    def _on_toggle_theme(self) -> None:
        self._theme_manager.cycle()
        effective = self._theme_manager.effective().value
        self._visualizer.set_theme(effective)
        for t, action in self._theme_actions.items():
            action.setChecked(t == self._theme_manager.current())
        if self._visualizer.last_markdown is not None:
            self._visualizer.show_markdown(self._visualizer.last_markdown, theme=effective)

    # ----- File selection ---------------------------------------------------

    @Slot(str)
    def _on_file_selected(self, path: str) -> None:
        """Handle a file click from the explorer.

        1. Validate the file (inspect_file) — bail early with an error if
           extension/size/encoding reject it.
        2. Update the code editor synchronously with the file content.
        3. Bind the file context on the visualizer (so chat prompts can
           reference it).
        4. Show a 'loading' placeholder in the visualizer.
        5. Dispatch an :class:`AnalysisWorker` to the QThreadPool.
        """
        theme = self._current_theme_name()
        result = inspect_file(path)
        if not result.ok:
            self._code_editor.clear()
            # Drop any stale file context.
            self._visualizer.set_file_context(None, None)
            self._visualizer.show_error(result.error_message, theme=theme)
            return

        # Synchronous UI update — editor always shows the file content
        # even if the AI call is still running. Pass the path + file_type
        # so Save / Edit-with-AI are enabled and the AI engine knows
        # the language.
        self._code_editor.set_content(
            result.content, path=path, file_type=result.file_type
        )
        self._visualizer.set_file_context(path, result.content)
        self._visualizer.show_loading(Path(path).name, theme=theme)

        engine = self._services.get("ai_engine")
        if engine is None:
            self._visualizer.show_error(
                "No AI engine configured (services['ai_engine'] missing).",
                theme=theme,
            )
            return

        worker = AnalysisWorker(
            ai_engine=engine,
            code_content=result.content,
            file_type=result.file_type,
            file_label=Path(path).name,
        )
        worker.signals.finished.connect(self._on_analysis_finished)
        worker.signals.failed.connect(self._visualizer.show_error)
        QThreadPool.globalInstance().start(worker)

    @Slot(str)
    def _on_analysis_finished(self, result: str) -> None:
        self._visualizer.show_markdown(result, theme=self._current_theme_name())

    # ----- Root change (QSettings) -----------------------------------------

    @Slot(str)
    def _on_root_changed(self, new_root: str) -> None:
        QSettings().setValue(_SETTINGS_ROOT_DIR, new_root)

    # ----- Editor flows -----------------------------------------------------

    @Slot(str)
    def _on_editor_save_failed(self, message: str) -> None:
        self._visualizer.show_error(f"Save failed: {message}", theme=self._current_theme_name())

    @Slot(str, str)
    def _on_ai_edit_requested(self, path: str, instruction: str) -> None:
        """Spawn an AIEditWorker; show a preview dialog on completion.

        We snapshot the *current* editor content (so the user can keep
        editing while the worker runs) and the original content for the
        diff view. If the user clicks Apply, the new content is written
        to disk and replaces the editor content.
        """
        engine = self._services.get("ai_engine")
        if engine is None:
            self._visualizer.show_error(
                "No AI engine configured (services['ai_engine'] missing).",
                theme=self._current_theme_name(),
            )
            return

        # Snapshot the editor state before we kick off the worker.
        self._pending_edit_path = path
        self._pending_edit_original = self._code_editor.current_content()
        self._pending_edit_instruction = instruction
        file_type = self._code_editor.current_file_type() or "text"

        # Show the loading state with the file name as the label.
        self._visualizer.show_loading(
            f"editing {Path(path).name}", theme=self._current_theme_name()
        )

        worker = AIEditWorker(
            ai_engine=engine,
            current_content=self._pending_edit_original,
            instruction=instruction,
            file_type=file_type,
            file_path=path,
        )
        worker.signals.finished.connect(self._on_ai_edit_finished)
        worker.signals.failed.connect(self._visualizer.show_error)
        QThreadPool.globalInstance().start(worker)

    @Slot(str)
    def _on_ai_edit_finished(self, new_content: str) -> None:
        path = self._pending_edit_path
        original = self._pending_edit_original or ""
        if path is None:
            self._visualizer.show_error(
                "Lost the file path before the AI edit finished.",
                theme=self._current_theme_name(),
            )
            return

        dlg = AIEditPreviewDialog(
            original_content=original,
            new_content=new_content,
            file_path=path,
            instruction=self._pending_edit_instruction or "(instrução não registrada)",
            parent=self,
        )
        accepted = dlg.exec() == QDialog.Accepted
        # Clear pending state immediately so concurrent edits don't get
        # confused.
        self._pending_edit_path = None
        self._pending_edit_original = None
        self._pending_edit_instruction = None

        if not accepted:
            # Show a friendly note in the visualizer.
            self._visualizer.show_idle(theme=self._current_theme_name())
            return

        try:
            self._file_manager.write_file(path, new_content)
        except Exception as exc:  # FileOperationError or OSError
            self._visualizer.show_error(
                f"Could not write edited file: {exc}",
                theme=self._current_theme_name(),
            )
            return

        # Replace the editor content with the applied edit. set_content
        # also clears the modified flag.
        self._code_editor.set_content(
            new_content,
            path=path,
            file_type=self._code_editor.current_file_type(),
        )
        self._visualizer.set_file_context(path, new_content)
        self._visualizer.show_markdown(
            f"**Edição aplicada.**\n\n```\n{new_content}\n```",
            theme=self._current_theme_name(),
        )

    # ----- Chat -------------------------------------------------------------

    @Slot(str)
    def _on_chat_requested(self, user_msg: str) -> None:
        engine = self._services.get("ai_engine")
        if engine is None:
            self._visualizer.show_error(
                "No AI engine configured (services['ai_engine'] missing).",
                theme=self._current_theme_name(),
            )
            return
        prompt = self._visualizer.build_chat_prompt(user_msg)
        worker = ChatWorker(ai_engine=engine, prompt=prompt, user_msg=user_msg)
        # Use a bound method (not a closure) so the slot survives across
        # the thread boundary. The user_msg is stashed on the worker
        # itself; the slot reads it back when it runs in the main thread.
        worker._user_msg = user_msg  # type: ignore[attr-defined]
        worker.signals.finished.connect(self._handle_chat_response)
        worker.signals.failed.connect(self._handle_chat_failure)
        QThreadPool.globalInstance().start(worker)

    @Slot(str)
    def _handle_chat_response(self, response: str) -> None:
        """Add the assistant reply to the most recent pending chat turn.

        PySide6 does not let us pass the user_msg through the signal
        payload (signals are typed and adding extra args is invasive),
        so the worker stashes it on itself and we recover it here from
        the thread pool's last-issued runnable. As a fallback we use the
        most recent pending turn in the visualizer — there is only ever
        one chat in flight at a time in this UI.
        """
        # Find the pending (no assistant) turn — they are added in order.
        for turn in reversed(self._visualizer.chat_history):
            if turn.assistant is None:
                turn.assistant = response
                break
        self._visualizer._render_chat_history()

    @Slot(str)
    def _handle_chat_failure(self, message: str) -> None:
        self._visualizer.show_error(message, theme=self._current_theme_name())

    # ----- Helpers ----------------------------------------------------------

    def _current_theme_name(self) -> str:
        if self._theme_manager is None:
            return "dark"
        return self._theme_manager.effective().value

    # ----- Public API used by tests and future controllers ------------------

    def panels(
        self,
    ) -> tuple[FileExplorerPanel, CodeEditorPanel, VisualizerPanel]:
        """Return the three panels in left-to-right order."""
        return (self._file_explorer, self._code_editor, self._visualizer)

    def splitter(self) -> QSplitter:
        """Return the horizontal splitter hosting the three panels."""
        return self._splitter

    def services(self) -> dict[str, Any]:
        """Return a copy of the injected services map."""
        return dict(self._services)

    def theme_manager(self) -> ThemeManager | None:
        """Return the injected ThemeManager (or None if not provided)."""
        return self._theme_manager

    def file_manager(self) -> FileManager:
        """Return the FileManager used by the editor and explorer."""
        return self._file_manager
