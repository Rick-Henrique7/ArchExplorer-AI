"""Left column: real file tree with click-to-select signal + action toolbar."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QModelIndex, Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFileSystemModel,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from app.services import FileManager, FileOperationError
from app.ui.icons import CustomIconProvider


class FileExplorerPanel(QWidget):
    """File tree rooted at ``root`` (default: current working directory).

    Uses a :class:`CustomIconProvider` so each entry shows a Material
    Design Icon appropriate to its file type, instead of the generic
    Windows file icons the default ``QFileIconProvider`` would yield.

    Emits:

    - :attr:`file_selected` (str) — absolute path of a clicked file
    - :attr:`root_changed` (str) — absolute path of the new root after
      Select Folder or set_root()

    The action toolbar (Change 005) provides:

    - **Select Folder** — opens a QFileDialog to pick any directory
    - **+Folder** — reveals an inline QLineEdit for the new folder name
    - **Refresh** — re-reads the filesystem model (F5)

    The actual content validation (extension, size, encoding) happens
    in :func:`app.ui.file_inspector.inspect_file` on the consumer side
    (typically :class:`app.ui.main_window.MainWindow`).
    """

    file_selected = Signal(str)         # absolute path
    root_changed = Signal(str)          # absolute path of new root

    def __init__(
        self,
        root: Path | None = None,
        file_manager: FileManager | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._file_manager = file_manager or FileManager()
        # The icon provider is held as an attribute so MainWindow can
        # update its color (and invalidate the cached QIcons) when the
        # theme changes.
        self._icon_provider = CustomIconProvider()
        self._build_ui(root or Path(os.getcwd()))

    def icon_provider(self) -> CustomIconProvider:
        """Return the icon provider (for theme-driven color updates)."""
        return self._icon_provider

    def apply_theme(self, theme: str) -> None:
        """Recolor icons to match ``theme`` and re-render the model.

        ``QFileSystemModel`` caches icons internally per file path, so
        just changing the provider's color is not enough — we also need
        to re-attach the provider to the model to force a re-fetch.
        """
        self._icon_provider.set_theme(theme)
        self._model.setIconProvider(self._icon_provider)

    def _build_ui(self, root: Path) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- Toolbar -------------------------------------------------------
        toolbar = QWidget(self)
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(4, 4, 4, 4)
        tb_layout.setSpacing(4)

        self._select_button = QPushButton("Selecionar Pasta", self)
        self._select_button.setToolTip("Escolher uma pasta de qualquer local do PC")
        self._select_button.clicked.connect(self._on_select_folder)
        tb_layout.addWidget(self._select_button)

        self._new_folder_button = QPushButton("+Pasta", self)
        self._new_folder_button.setToolTip("Criar uma nova subpasta no diretório raiz")
        self._new_folder_button.clicked.connect(self._on_new_folder)
        tb_layout.addWidget(self._new_folder_button)

        self._refresh_button = QPushButton("Atualizar", self)
        self._refresh_button.setToolTip("Recarregar a árvore (F5)")
        self._refresh_button.setShortcut("F5")
        self._refresh_button.clicked.connect(self._on_refresh)
        tb_layout.addWidget(self._refresh_button)

        tb_layout.addStretch(1)
        layout.addWidget(toolbar)

        # --- Inline new-folder input (hidden by default) -------------------
        self._new_folder_input_row = QWidget(self)
        nf_layout = QHBoxLayout(self._new_folder_input_row)
        nf_layout.setContentsMargins(4, 0, 4, 4)
        nf_layout.setSpacing(4)
        self._new_folder_input = QLineEdit(self._new_folder_input_row)
        self._new_folder_input.setPlaceholderText("Nome da nova pasta (Enter confirma, Esc cancela)")
        self._new_folder_input.returnPressed.connect(self._commit_new_folder)
        # Esc cancels — install a tiny event filter to catch KeyPress.
        self._new_folder_input.installEventFilter(self)
        nf_layout.addWidget(self._new_folder_input, stretch=1)
        layout.addWidget(self._new_folder_input_row)
        self._new_folder_input_row.setVisible(False)

        # --- Tree view ----------------------------------------------------
        self._model = QFileSystemModel(self)
        # CustomIconProvider replaces the default QFileIconProvider so the
        # tree shows MDI icons (.py, .md, .json, LICENSE, etc.) instead of
        # the OS-default yellow folder / blank page icons.
        self._model.setIconProvider(self._icon_provider)
        self._model.setRootPath(str(root))

        self._view = QTreeView(self)
        self._view.setModel(self._model)
        self._view.setRootIndex(self._model.index(str(root)))
        self._view.setHeaderHidden(True)
        # Only show the name column; hide size/type/modified for compactness.
        for col in range(1, 4):
            self._view.hideColumn(col)
        self._view.clicked.connect(self._on_clicked)

        layout.addWidget(self._view)

    # ----- Public API -------------------------------------------------------

    def root(self) -> Path:
        """Return the current root path of the tree."""
        return Path(self._model.rootPath())

    def set_root(self, new_root: str | Path) -> None:
        """Re-root the tree at ``new_root``.

        Updates the model, scrolls the view to the new root, and emits
        :attr:`root_changed`. The QFileSystemModel itself caches directory
        contents internally, so the existing nodes keep their expand state.
        """
        new_root_path = Path(new_root)
        if not new_root_path.exists() or not new_root_path.is_dir():
            return
        self._model.setRootPath(str(new_root_path))
        self._view.setRootIndex(self._model.index(str(new_root_path)))
        self.root_changed.emit(str(new_root_path.resolve()))

    def file_manager(self) -> FileManager:
        """Return the injected FileManager (test seam)."""
        return self._file_manager

    # ----- Event filter: Esc cancels inline new-folder input --------------

    def eventFilter(self, obj: QWidget, event: QEvent) -> bool:  # noqa: N802
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import QKeyEvent

        if (
            obj is self._new_folder_input
            and event.type() == QEvent.Type.KeyPress
        ):
            assert isinstance(event, QKeyEvent)
            if event.key() == Qt.Key.Key_Escape:
                self._cancel_new_folder()
                return True  # consume
        return super().eventFilter(obj, event)

    # ----- Internal handlers -----------------------------------------------

    def _on_clicked(self, index: QModelIndex) -> None:
        # Only emit for files; directories are handled by the tree itself.
        if not self._model.isDir(index):
            path = self._model.filePath(index)
            self.file_selected.emit(path)

    def _on_select_folder(self) -> None:
        """Open a native folder picker; re-root the tree on confirm."""
        chosen = QFileDialog.getExistingDirectory(
            self,
            "Selecionar pasta raiz",
            str(self.root()),
        )
        if chosen:
            self.set_root(chosen)

    def _on_new_folder(self) -> None:
        """Reveal the inline input row for a new folder name."""
        self._new_folder_input.clear()
        self._new_folder_input_row.setVisible(True)
        self._new_folder_input.setFocus()

    def _commit_new_folder(self) -> None:
        """Validate + create the new folder, then hide the input row."""
        name = self._new_folder_input.text().strip()
        if not name:
            self._cancel_new_folder()
            return
        try:
            self._file_manager.create_folder(str(self.root()), name)
        except FileOperationError as exc:
            # Surface the error by showing it as the tooltip of the input
            # for a moment; the MainWindow's show_error will also fire
            # once we wire it. For now, keep the input visible with a
            # red border via the dynamic property set below.
            self._new_folder_input.setProperty("error", True)
            self._new_folder_input.setToolTip(exc.message)
            self._new_folder_input.style().polish(self._new_folder_input)
            return
        # Success: refresh and hide.
        self._on_refresh()
        self._cancel_new_folder()

    def _cancel_new_folder(self) -> None:
        self._new_folder_input.clear()
        self._new_folder_input.setProperty("error", False)
        self._new_folder_input.setToolTip("")
        self._new_folder_input_row.setVisible(False)

    def _on_refresh(self) -> None:
        """Force the QFileSystemModel to re-read the filesystem.

        PySide6's QFileSystemModel does not expose ``refresh()`` (it is
        a private C++ method in PySide6), so we re-apply the root path
        to invalidate the cache and force a re-scan. The view's
        ``setRootIndex`` call is idempotent and a no-op when the index
        is unchanged.
        """
        root = str(self.root())
        self._model.setRootPath(root)
        self._view.setRootIndex(self._model.index(root))
