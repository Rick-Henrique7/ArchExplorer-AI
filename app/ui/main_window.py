"""Main window — three horizontal panels + menu bar + Change 005/006 wiring.

Change 006 introduces a fourth concept: the catalog. The left column
is now a :class:`LeftPanel` that stacks the file explorer and the
catalog; switching is done via ``View > Painel esquerdo > Projeto /
Catálogo`` (``Ctrl+1`` / ``Ctrl+2``).

Change 007 adds the LPS mode: ``View > Painel esquerdo > LPS``
(``Ctrl+3``) replaces the left column with the component palette,
the center column with the feature-model canvas, and the right
column with the node inspector.
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import Any

from PySide6.QtCore import QSettings, Qt, QThreadPool, Slot
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (
    QDialog,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.services import CatalogoService, FileManager
from app.ui.ai_edit_preview import AIEditPreviewDialog
from app.ui.analysis_worker import AIEditWorker, AnalysisWorker, ChatWorker
from app.ui.catalogo_panel import CatalogoPanel
from app.ui.code_editor import CodeEditorPanel
from app.ui.entry_editor_dialog import EntryEditorDialog
from app.ui.entry_preview_panel import EntryPreviewPanel
from app.ui.file_explorer import FileExplorerPanel
from app.ui.file_inspector import inspect_file
from app.ui.left_panel import LeftPanel, LeftPanelMode
from app.ui.theme import Theme, ThemeManager
from app.ui.visualizer import VisualizerPanel
from app.workers import LpsSolverWorker

# Module-level logger (avoid name collision with anything else).
_logger = logging.getLogger(__name__)


# QSettings keys (single source of truth for the registry layout).
_SETTINGS_ROOT_DIR = "workspace/root_dir"
_SETTINGS_LEFT_MODE = "workspace/left_panel_mode"
_SETTINGS_CATALOG_DB = "catalog/db_path"


def _content_hash(content: str) -> str:
    """Stable hash of file content for cache invalidation.

    SHA-1 is used (not MD5) because it's in the stdlib and the content
    is already in memory — we just need a fast, deterministic key.
    """
    return hashlib.sha1(content.encode("utf-8")).hexdigest()


class MainWindow(QMainWindow):
    """ArchExplorer AI main window.

    Hosts three resizable panels in a horizontal ``QSplitter`` plus a
    menu bar with View > Theme switcher and View > Painel esquerdo.

    Dependency injection:
    - ``services`` (dict): expected key ``"ai_engine"`` and (Change 006)
      ``"catalog_service"``. Either may be omitted for tests.
    - ``theme_manager``: optional; if provided, the View menu is built
      and the current theme is applied to incoming markdown renders.
    - ``file_manager``: optional; if provided, the explorer and editor
      share the same instance. A new one is created otherwise.

    QSettings persistence:
    - The explorer's root directory is saved on every change (Change 005).
    - The left-panel mode (explorer / catalog) is saved on every change
      (Change 006).
    - The catalog DB path is read from settings (Change 006 Bloco K).
    """

    WINDOW_TITLE: str = "ArchExplorer AI"
    DEFAULT_SIZE: tuple[int, int] = (1100, 700)
    SPLITTER_STRETCH: tuple[int, int, int] = (25, 45, 30)

    # Cache configuration: how many file analyses to keep in memory.
    _ANALYSIS_CACHE_MAX: int = 32

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
        # Analysis cache: file_path -> (content_hash, markdown). The
        # content_hash is the SHA-1 of the file's bytes; if the file
        # changes (or is saved with Ctrl+S), the hash won't match and
        # the cache entry is treated as a miss. LRU eviction at
        # _ANALYSIS_CACHE_MAX entries.
        self._analysis_cache: dict[str, tuple[str, str]] = {}
        # Track the currently open file (path, content, file_type) so the
        # manual Analisar button has the data to send.
        self._current_file: tuple[str, str, str] | None = None
        # Pending analysis (set by _on_analyze_requested, read by
        # _on_analysis_finished to write the result back into the cache).
        self._pending_analysis_path: str | None = None
        self._pending_analysis_hash: str | None = None
        self._build_ui()
        self._wire()
        if self._theme_manager is not None:
            self._build_menu()
        # If the catalog was the last mode, restore it now.
        if self._left_panel is not None and self._restored_mode is not None:
            self._left_panel.show_mode(self._restored_mode)
        # Set up the LPS autosave timer + canvas/inspector wiring.
        # Must happen AFTER the canvas view exists (we wired it in
        # _build_ui) but before the user can interact.
        self._setup_lps_autosave()
        _logger.info("MainWindow initialized (Change 007 LPS wiring active)")

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

        # Restore last-used left-panel mode (default: explorer).
        saved_mode_raw = settings.value(_SETTINGS_LEFT_MODE, "", type=str)
        try:
            initial_mode = LeftPanelMode(saved_mode_raw) if saved_mode_raw else LeftPanelMode.EXPLORER
        except ValueError:
            initial_mode = LeftPanelMode.EXPLORER
        self._restored_mode = initial_mode

        # Explorer + catalog stack inside a LeftPanel.
        self._file_explorer = FileExplorerPanel(
            root=initial_root, file_manager=self._file_manager, parent=self
        )
        catalog_service = self._services.get("catalog_service")
        if not isinstance(catalog_service, CatalogoService):
            # Fall back to the default location; tests inject their own.
            catalog_service = CatalogoService()
        self._catalog_service = catalog_service
        self._catalog_panel = CatalogoPanel(
            catalogo_service=catalog_service, parent=self
        )
        self._left_panel = LeftPanel(
            explorer=self._file_explorer,
            catalog=self._catalog_panel,
            initial_mode=initial_mode,
            parent=self,
        )

        self._code_editor = CodeEditorPanel(
            file_manager=self._file_manager, parent=self
        )
        self._visualizer = VisualizerPanel(self)
        self._entry_preview = EntryPreviewPanel(
            service=catalog_service, parent=self
        )

        # LPS mode widgets (Change 007 — Bloco E).
        from app.ui.lps_canvas_view import LpsCanvasView
        from app.ui.lps_inspector_panel import LpsInspectorPanel
        from app.ui.lps_palette_panel import LpsPalettePanel

        self._lps_palette = LpsPalettePanel(parent=self)
        # Seed the palette with whatever is already in the DB so the
        # user has something to drag on the first switch to LPS mode.
        # The full refresh happens after `_wire()` once signals are
        # connected. ``list_components`` lives on LpsService (the
        # catalog service has different tables).
        from app.services import LpsService
        self._lps_service = LpsService(db_path=catalog_service.db_path)
        self._lps_palette.set_components(
            self._lps_service.list_components(limit=200),
        )
        self._lps_canvas_view = LpsCanvasView(parent=self)
        self._lps_inspector = LpsInspectorPanel(parent=self)

        # Rebuild the LeftPanel with the palette as the 3rd child
        # (LPS mode). The earlier instance is replaced because we
        # already added it to the splitter; we don't want to have
        # two stacked widgets fighting for the same slot.
        self._left_panel.deleteLater()
        self._left_panel = LeftPanel(
            explorer=self._file_explorer,
            catalog=self._catalog_panel,
            palette=self._lps_palette,
            initial_mode=initial_mode,
            parent=self,
        )

        # Right column: stack of (visualizer, entry_preview, inspector).
        self._right_stack = QStackedWidget(self)
        self._visualizer_index = self._right_stack.addWidget(self._visualizer)
        self._entry_preview_index = self._right_stack.addWidget(self._entry_preview)
        self._lps_inspector_index = self._right_stack.addWidget(self._lps_inspector)
        # Default: visualizer (explorer mode).
        self._right_stack.setCurrentIndex(self._visualizer_index)

        # Center column: stack of (code_editor, lps_canvas).
        self._center_stack = QStackedWidget(self)
        self._code_editor_index = self._center_stack.addWidget(self._code_editor)
        self._lps_canvas_index = self._center_stack.addWidget(self._lps_canvas_view)
        self._center_stack.setCurrentIndex(self._code_editor_index)

        self._splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self._splitter.addWidget(self._left_panel)
        self._splitter.addWidget(self._center_stack)
        self._right_stack_container = QWidget(self)
        rs_layout = QVBoxLayout(self._right_stack_container)
        rs_layout.setContentsMargins(0, 0, 0, 0)
        rs_layout.addWidget(self._right_stack)
        self._splitter.addWidget(self._right_stack_container)
        for i, stretch in enumerate(self.SPLITTER_STRETCH):
            self._splitter.setStretchFactor(i, stretch)
        self._splitter.setChildrenCollapsible(False)

        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._splitter)
        self.setCentralWidget(central)

        # Tell the visualizer + preview the active theme so its internal
        # renders use the right body colors.
        if self._theme_manager is not None:
            effective_theme = self._theme_manager.effective().value
            self._visualizer.set_theme(effective_theme)
            self._entry_preview.set_theme(effective_theme)
            # Recolor the file tree icons to match the theme — without
            # this, MDI icons stay white in light mode and disappear.
            self._file_explorer.apply_theme(effective_theme)

    def _wire(self) -> None:
        # File selection -> editor + visualizer file context (NO auto
        # analysis — Change 005 + hotfix: user must click Analisar).
        self._file_explorer.file_selected.connect(self._on_file_selected)
        # Root changes -> QSettings.
        self._file_explorer.root_changed.connect(self._on_root_changed)
        # Editor save / AI-edit flows.
        self._code_editor.save_failed.connect(self._on_editor_save_failed)
        self._code_editor.ai_edit_requested.connect(self._on_ai_edit_requested)
        # Editor saved -> invalidate cache for that file (content changed).
        self._code_editor.file_saved.connect(self._on_file_saved)
        # Manual Analisar button -> cache check + worker.
        self._visualizer.analyze_requested.connect(self._on_analyze_requested)
        # Visualizer chat -> background worker -> add_chat_response.
        self._visualizer.chat_requested.connect(self._on_chat_requested)
        # Left panel mode change -> QSettings + right column swap.
        self._left_panel.mode_changed.connect(self._on_left_panel_mode_changed)
        # Catalog panel signals -> MainWindow.
        self._catalog_panel.entry_selected.connect(self._on_catalog_entry_selected)
        self._catalog_panel.new_entry_requested.connect(self._on_catalog_new_entry)
        self._catalog_panel.edit_entry_requested.connect(self._on_catalog_edit_entry)
        self._catalog_panel.delete_entry_requested.connect(self._on_catalog_delete_entry)
        self._catalog_panel.insert_into_editor_requested.connect(
            self._on_catalog_insert_into_editor
        )
        # Entry preview signals -> MainWindow.
        self._entry_preview.insert_into_editor.connect(
            self._on_catalog_insert_into_editor
        )
        self._entry_preview.edit_entry.connect(self._on_catalog_edit_entry)
        self._entry_preview.delete_entry.connect(self._on_catalog_delete_entry)

    def _build_menu(self) -> None:
        """Build the menu bar with View > Theme + View > Painel esquerdo."""
        menubar = self.menuBar()
        view_menu = menubar.addMenu("&View")

        # --- Painel esquerdo submenu -------------------------------------
        left_menu = view_menu.addMenu("&Painel esquerdo")
        self._left_action_group = QActionGroup(self)
        self._left_action_group.setExclusive(True)
        self._left_actions: dict[LeftPanelMode, QAction] = {}
        _SHORTCUTS = {
            LeftPanelMode.EXPLORER: "Ctrl+1",
            LeftPanelMode.CATALOG: "Ctrl+2",
            LeftPanelMode.LPS: "Ctrl+3",
        }
        _LABELS = {
            LeftPanelMode.EXPLORER: "&Projeto",
            LeftPanelMode.CATALOG: "Ca&tálogo",
            LeftPanelMode.LPS: "&LPS",
        }
        for mode in (LeftPanelMode.EXPLORER, LeftPanelMode.CATALOG, LeftPanelMode.LPS):
            action = QAction(_LABELS[mode], self)
            action.setCheckable(True)
            action.setChecked(mode == self._left_panel.current_mode())
            action.setShortcut(QKeySequence(_SHORTCUTS[mode]))
            action.triggered.connect(
                lambda _checked=False, m=mode: self._on_left_menu_triggered(m)
            )
            self._left_action_group.addAction(action)
            self._left_actions[mode] = action
            left_menu.addAction(action)

        view_menu.addSeparator()

        # --- Theme submenu ------------------------------------------------
        theme_menu = view_menu.addMenu("&Theme")
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
        self._entry_preview.set_theme(effective)
        # Recolor the file tree icons — without this they stay white in
        # light mode and become invisible against the white background.
        self._file_explorer.apply_theme(effective)
        if self._visualizer.last_markdown is not None:
            self._visualizer.show_markdown(self._visualizer.last_markdown, theme=effective)
        for t, action in self._theme_actions.items():
            action.setChecked(t == self._theme_manager.current())

    @Slot()
    def _on_toggle_theme(self) -> None:
        self._theme_manager.cycle()
        effective = self._theme_manager.effective().value
        self._visualizer.set_theme(effective)
        self._entry_preview.set_theme(effective)
        self._file_explorer.apply_theme(effective)
        for t, action in self._theme_actions.items():
            action.setChecked(t == self._theme_manager.current())
        if self._visualizer.last_markdown is not None:
            self._visualizer.show_markdown(self._visualizer.last_markdown, theme=effective)

    # ----- Left panel / View > Painel esquerdo ----------------------------

    @Slot(LeftPanelMode)
    def _on_left_menu_triggered(self, mode: LeftPanelMode) -> None:
        self._left_panel.show_mode(mode)

    @Slot(str)
    def _on_left_panel_mode_changed(self, mode_value: str) -> None:
        """Switch the right column + center column + persist."""
        try:
            mode = LeftPanelMode(mode_value)
        except ValueError:
            return
        # Right column: visualizer / entry_preview / lps_inspector.
        if mode == LeftPanelMode.EXPLORER:
            self._right_stack.setCurrentIndex(self._visualizer_index)
        elif mode == LeftPanelMode.CATALOG:
            self._right_stack.setCurrentIndex(self._entry_preview_index)
            # Whenever we land on the catalog, refresh the list so newly
            # added entries (via the +Nova dialog) are visible.
            self._catalog_panel.refresh()
        elif mode == LeftPanelMode.LPS:
            self._right_stack.setCurrentIndex(self._lps_inspector_index)
            # Center swaps: code editor out, canvas in.
            self._center_stack.setCurrentIndex(self._lps_canvas_index)
            # Refresh the LPS palette from the DB so newly added
            # components appear.
            self._refresh_lps_palette()
        # Center column: editor (in EXPLORER + CATALOG modes) or
        # canvas (in LPS mode).
        if mode == LeftPanelMode.LPS:
            self._center_stack.setCurrentIndex(self._lps_canvas_index)
        else:
            self._center_stack.setCurrentIndex(self._code_editor_index)
        QSettings().setValue(_SETTINGS_LEFT_MODE, mode_value)
        # Update menu check-state (the menu only exists when a
        # theme_manager was injected; use getattr defensively).
        for m, action in getattr(self, "_left_actions", {}).items():
            action.setChecked(m == mode)

    # ----- LPS helpers ----------------------------------------------------

    def _refresh_lps_palette(self) -> None:
        """Reload the LPS palette from the catalog DB."""
        try:
            components = self._lps_service.list_components(limit=200)
            self._lps_palette.set_components(components)
        except Exception as exc:  # noqa: BLE001 — defensive
            _logger.warning("failed to refresh lps palette: %s", exc)

    def _on_lps_validate(self) -> None:
        """Spawn an LpsSolverWorker; render the result in the inspector."""
        scene = self._lps_canvas_view.canvas_scene()
        payload = scene.to_json()
        # Build a FeatureModel in-memory for the solver (no DB write).
        feature_model = self._build_feature_model_from_payload(payload)
        # Default selection: ROOT + MANDATORY nodes.
        selection = list(feature_model.selected_node_ids())
        worker = LpsSolverWorker(
            feature_model=feature_model, selection=selection,
        )
        worker.signals.finished.connect(self._on_lps_validate_finished)
        worker.signals.failed.connect(self._on_lps_validate_failed)
        QThreadPool.globalInstance().start(worker)

    def _on_lps_validate_finished(self, result) -> None:
        """Show the validation result in the inspector."""
        from app.services.variability_solver import ValidationResult
        if not isinstance(result, ValidationResult):
            return
        # Pick the currently-selected node (if any) for the preview.
        selected = self._lps_inspector._current_node
        if selected is None:
            # No node selected — still update the inspector's header
            # so the user sees the validation status even without
            # picking a node.
            self._lps_inspector._comp_name.setText(
                f"Validação: {'OK' if result.is_valid else 'INVÁLIDA'}"
            )
            if not result.is_valid and result.conflicting:
                self._lps_inspector._comp_template.setText(
                    f"Conflito: {', '.join(result.conflicting)}"
                )
            return
        # Persist the validation status on the DB if we have a real
        # feature_model_id (skipped here — in-memory model).
        if result.is_valid:
            self._lps_inspector._comp_name.setText(
                f"Selecionado: {selected.label} ✓ válido"
            )
        else:
            self._lps_inspector._comp_name.setText(
                f"Selecionado: {selected.label} ✗ conflito"
            )
            self._lps_inspector._comp_template.setText(
                f"Conflito: {', '.join(result.conflicting)}"
            )

    def _on_lps_validate_failed(self, message: str) -> None:
        QMessageBox.warning(self, "Validação LPS", message)

    def _on_lps_generate(self) -> None:
        """Spawn an LpsGeneratorWorker; show a folder picker first."""
        from PySide6.QtWidgets import QFileDialog
        out_dir = QFileDialog.getExistingDirectory(
            self, "Selecionar diretório de saída",
            str(Path.home() / "Documents" / "ArchExplorer" / "products"),
        )
        if not out_dir:
            return
        scene = self._lps_canvas_view.canvas_scene()
        payload = scene.to_json()
        feature_model = self._build_feature_model_from_payload(payload)
        selection = list(feature_model.selected_node_ids())
        # Components by id for the generator.
        components_by_id = {
            c.id: c for c in self._lps_service.list_components(limit=500)
        }
        from app.services.template_engine import TemplateEngine
        from app.workers import LpsGeneratorWorker
        template_root = (
            Path(__file__).resolve().parent.parent / "templates" / "lps"
        )
        engine = TemplateEngine(template_root=template_root)
        worker = LpsGeneratorWorker(
            feature_model=feature_model,
            selection=selection,
            components_by_id=components_by_id,
            template_engine=engine,
            output_dir=Path(out_dir),
            service=self._lps_service,
        )
        worker.signals.finished.connect(self._on_lps_generate_finished)
        worker.signals.failed.connect(self._on_lps_generate_failed)
        QThreadPool.globalInstance().start(worker)

    def _on_lps_generate_finished(self, result) -> None:
        from app.workers import GeneratorResult
        if not isinstance(result, GeneratorResult):
            return
        msg = (
            f"Produto gerado em {result.output_dir} "
            f"({result.file_count} arquivos, {result.duration_ms} ms)"
        )
        if result.failed_files:
            msg += f"\nFalhas: {len(result.failed_files)}"
        QMessageBox.information(self, "Geração LPS", msg)

    def _on_lps_generate_failed(self, message: str) -> None:
        QMessageBox.warning(self, "Geração LPS", message)

    def _build_feature_model_from_payload(self, payload: dict) -> FeatureModel:
        """Reconstruct a FeatureModel from the scene's JSON payload.

        The canvas keeps node positions in ``metadata.x/y``; we pull
        those out and feed a tiny in-memory model to the worker.
        """
        from app.services.lps_models import (
            FeatureNode, FeatureEdge, FeatureGroup, FeatureModel,
        )
        nodes = tuple(
            FeatureNode.from_dict({**n, "metadata": {}})
            for n in payload.get("nodes", [])
        )
        edges = tuple(
            FeatureEdge.from_dict({**e, "metadata": {}})
            for e in payload.get("edges", [])
        )
        groups = tuple(
            FeatureGroup.from_dict(g) for g in payload.get("groups", [])
        )
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        # The scene's metadata.x/y is already in the node.metadata
        # dict via ``to_json``; we strip it back out so the SAT
        # solver doesn't choke on extra fields.
        nodes = tuple(
            FeatureNode(
                id=n.id, component_id=n.component_id,
                variability=n.variability, label=n.label,
                metadata={},  # positions live in the canvas, not the model
            )
            for n in nodes
        )
        return FeatureModel(
            id="scene-current", title="Scene",
            description=None, tree_structure_json="{}",
            nodes=nodes, edges=edges, groups=groups,
            validation_status="DRAFT",
            last_solved_at=None,
            created_at=now, updated_at=now,
        )

    def _setup_lps_autosave(self) -> None:
        """Auto-save the canvas tree to a draft feature model every 30s."""
        from PySide6.QtCore import QTimer
        self._lps_autosave_timer = QTimer(self)
        self._lps_autosave_timer.setInterval(30_000)  # 30s
        self._lps_autosave_timer.setSingleShot(False)
        # Only fire when the canvas emits tree_changed AND we're in LPS
        # mode. We connect to the scene directly.
        scene = self._lps_canvas_view.canvas_scene()
        scene.tree_changed.connect(self._lps_autosave_timer.start)
        self._lps_autosave_timer.timeout.connect(self._lps_autosave_tick)
        self._lps_autosave_timer.start()
        # Also wire the canvas's validate/generate buttons to our handlers.
        self._lps_canvas_view.validate_requested.connect(self._on_lps_validate)
        self._lps_canvas_view.generate_requested.connect(self._on_lps_generate)
        # Wire inspector edits to mutate the canvas in real time.
        scene.node_selected.connect(self._on_lps_canvas_node_selected)
        self._lps_inspector.node_edited.connect(self._on_lps_inspector_edited)
        self._lps_inspector.node_deleted.connect(self._on_lps_inspector_deleted)

    def _lps_autosave_tick(self) -> None:
        """Persist the current canvas as a draft feature model."""
        try:
            scene = self._lps_canvas_view.canvas_scene()
            payload = scene.to_json()
            if not payload.get("nodes"):
                return  # nothing to save
            # Upsert: try create_feature_model; if the id is already
            # used (because we re-load the same id), update_tree_structure.
            scene_id = "draft-scene"
            existing = self._lps_service.get_feature_model(scene_id)
            if existing is None:
                self._lps_service.create_feature_model(
                    id=scene_id,
                    title="Rascunho LPS (auto-save)",
                    tree_structure=payload,
                )
            else:
                self._lps_service.update_tree_structure(
                    scene_id, payload,
                )
        except Exception as exc:  # noqa: BLE001 — autosave must not crash UI
            _logger.warning("LPS autosave failed: %s", exc)

    def _on_lps_canvas_node_selected(self, node_id: str) -> None:
        """When the canvas selects a node, populate the inspector."""
        if not node_id:
            self._lps_inspector.clear_node()
            return
        scene = self._lps_canvas_view.canvas_scene()
        node = scene.get_node(node_id)
        if node is None:
            self._lps_inspector.clear_node()
            return
        # Look up the component (if any) for the side panel.
        component = None
        if node.component_id:
            component = self._lps_service.get_component(node.component_id)
        self._lps_inspector.show_node(node, component=component)

    def _on_lps_inspector_edited(self, node_id: str, edits: dict) -> None:
        """Apply inspector edits back to the canvas node."""
        scene = self._lps_canvas_view.canvas_scene()
        node = scene.get_node(node_id)
        if node is None:
            return
        if "label" in edits:
            node.label = edits["label"]
        if "variability" in edits:
            node.variability = edits["variability"]
        scene.refresh_all_edge_paths()
        scene.tree_changed.emit()

    def _on_lps_inspector_deleted(self, node_id: str) -> None:
        scene = self._lps_canvas_view.canvas_scene()
        scene.remove_node(node_id)

    # ----- File selection ---------------------------------------------------

    @Slot(str)
    def _on_file_selected(self, path: str) -> None:
        """Handle a file click from the explorer.

        Flow (no auto-analysis — Change 005 hotfix):

        1. Validate the file (inspect_file) — bail early on error.
        2. Update the code editor synchronously.
        3. Bind the file context on the visualizer (chat prompts).
        4. Update the visualizer's file label + enable Analisar.
        5. Cache hit? Render immediately. Otherwise show idle.
        """
        theme = self._current_theme_name()
        result = inspect_file(path)
        if not result.ok:
            self._code_editor.clear()
            self._visualizer.set_file_context(None, None)
            self._visualizer.set_current_file(None)
            self._visualizer.show_error(result.error_message, theme=theme)
            self._current_file = None
            return

        self._code_editor.set_content(
            result.content, path=path, file_type=result.file_type
        )
        self._visualizer.set_file_context(path, result.content)
        self._visualizer.set_current_file(path)
        self._current_file = (path, result.content, result.file_type)

        content_hash = _content_hash(result.content)
        cached = self._analysis_cache.get(path)
        if cached is not None and cached[0] == content_hash:
            self._visualizer.show_cached(cached[1], theme=theme)
            return

        self._visualizer.show_idle(theme=theme)

    @Slot()
    def _on_analyze_requested(self) -> None:
        """Handle the manual Analisar button."""
        if self._current_file is None:
            return
        path, content, file_type = self._current_file
        theme = self._current_theme_name()
        content_hash = _content_hash(content)
        cached = self._analysis_cache.get(path)
        if cached is not None and cached[0] == content_hash:
            self._visualizer.show_cached(cached[1], theme=theme)
            return

        engine = self._services.get("ai_engine")
        if engine is None:
            self._visualizer.show_error(
                "Motor de IA não configurado (services['ai_engine'] ausente).",
                theme=theme,
            )
            return

        self._visualizer.show_loading(Path(path).name, theme=theme)
        self._visualizer._set_analyze_busy(True)
        self._pending_analysis_path = path
        self._pending_analysis_hash = content_hash
        worker = AnalysisWorker(
            ai_engine=engine,
            code_content=content,
            file_type=file_type,
            file_label=Path(path).name,
        )
        worker.signals.finished.connect(self._on_analysis_finished)
        worker.signals.failed.connect(self._on_analysis_failed)
        QThreadPool.globalInstance().start(worker)

    @Slot(str)
    def _on_analysis_failed(self, message: str) -> None:
        self._visualizer._set_analyze_busy(False)
        self._visualizer.show_error(message, theme=self._current_theme_name())

    @Slot(str)
    def _on_analysis_finished(self, result: str) -> None:
        """Cache the result, then render it in the visualizer."""
        path = getattr(self, "_pending_analysis_path", None)
        content_hash = getattr(self, "_pending_analysis_hash", None)
        if path is not None and content_hash is not None:
            self._store_in_cache(path, content_hash, result)
        self._pending_analysis_path = None
        self._pending_analysis_hash = None
        self._visualizer._set_analyze_busy(False)
        self._visualizer.show_markdown(result, theme=self._current_theme_name())

    def _store_in_cache(self, path: str, content_hash: str, result: str) -> None:
        """LRU cache insert — drops the oldest entry past the cap."""
        self._analysis_cache.pop(path, None)
        self._analysis_cache[path] = (content_hash, result)
        while len(self._analysis_cache) > self._ANALYSIS_CACHE_MAX:
            oldest_path = next(iter(self._analysis_cache))
            self._analysis_cache.pop(oldest_path, None)

    @Slot(str)
    def _on_file_saved(self, path: str) -> None:
        """Invalidate the cache for a file the user just saved (Ctrl+S)."""
        self._analysis_cache.pop(path, None)

    # ----- Root change (QSettings) -----------------------------------------

    @Slot(str)
    def _on_root_changed(self, new_root: str) -> None:
        QSettings().setValue(_SETTINGS_ROOT_DIR, new_root)

    # ----- Editor flows -----------------------------------------------------

    @Slot(str)
    def _on_editor_save_failed(self, message: str) -> None:
        self._visualizer.show_error(f"Falha ao salvar: {message}", theme=self._current_theme_name())

    @Slot(str, str)
    def _on_ai_edit_requested(self, path: str, instruction: str) -> None:
        engine = self._services.get("ai_engine")
        if engine is None:
            self._visualizer.show_error(
                "No AI engine configured (services['ai_engine'] missing).",
                theme=self._current_theme_name(),
            )
            return

        self._pending_edit_path = path
        self._pending_edit_original = self._code_editor.current_content()
        self._pending_edit_instruction = instruction
        file_type = self._code_editor.current_file_type() or "text"

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
        self._pending_edit_path = None
        self._pending_edit_original = None
        self._pending_edit_instruction = None

        if not accepted:
            self._visualizer.show_idle(theme=self._current_theme_name())
            return

        try:
            self._file_manager.write_file(path, new_content)
        except Exception as exc:  # FileOperationError or OSError
            self._visualizer.show_error(
                f"Não foi possível gravar a edição: {exc}",
                theme=self._current_theme_name(),
            )
            return

        self._code_editor.set_content(
            new_content,
            path=path,
            file_type=self._code_editor.current_file_type(),
        )
        self._visualizer.set_file_context(path, new_content)
        self._analysis_cache.pop(path, None)
        self._current_file = (
            path, new_content, self._code_editor.current_file_type() or "text"
        )
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
        worker._user_msg = user_msg  # type: ignore[attr-defined]
        worker.signals.finished.connect(self._handle_chat_response)
        worker.signals.failed.connect(self._handle_chat_failure)
        QThreadPool.globalInstance().start(worker)

    @Slot(str)
    def _handle_chat_response(self, response: str) -> None:
        for turn in reversed(self._visualizer.chat_history):
            if turn.assistant is None:
                turn.assistant = response
                break
        self._visualizer._render_chat_history()

    @Slot(str)
    def _handle_chat_failure(self, message: str) -> None:
        self._visualizer.show_error(message, theme=self._current_theme_name())

    # ----- Catalog flows (Change 006) --------------------------------------

    @Slot(int)
    def _on_catalog_entry_selected(self, entry_id: int) -> None:
        """Render the selected entry in the right column."""
        self._entry_preview.show_entry_by_id(entry_id)

    @Slot()
    def _on_catalog_new_entry(self) -> None:
        """Open the EntryEditorDialog in CREATE mode."""
        dlg = EntryEditorDialog(mode=EntryEditorDialog.MODE_CREATE, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        draft = dlg.get_draft()
        if draft is None:
            return
        try:
            entry = self._catalog_service.create_entry(
                title=draft.title,
                code=draft.code,
                description=draft.description,
                language=draft.language,
                category=draft.category,
                tags=list(draft.tags),
                origin_path=draft.origin_path,
                origin_line=draft.origin_line,
                is_public=draft.is_public,
            )
        except Exception as exc:  # CatalogoError
            QMessageBox.warning(
                self, "Erro ao criar entrada", str(exc)
            )
            return
        # Refresh the list and surface the new entry in the preview.
        self._catalog_panel.refresh()
        self._entry_preview.show_entry(entry)

    @Slot(int)
    def _on_catalog_edit_entry(self, entry_id: int) -> None:
        """Open the EntryEditorDialog in EDIT mode and apply on accept."""
        entry = self._catalog_service.get_entry(entry_id)
        if entry is None:
            QMessageBox.warning(
                self, "Erro", f"Entrada {entry_id} não encontrada."
            )
            return
        dlg = EntryEditorDialog(
            mode=EntryEditorDialog.MODE_EDIT, entry=entry, parent=self
        )
        if dlg.exec() != QDialog.Accepted:
            return
        draft = dlg.get_draft()
        if draft is None:
            return
        try:
            updated = self._catalog_service.update_entry(
                entry_id,
                title=draft.title,
                code=draft.code,
                description=draft.description,
                language=draft.language,
                category=draft.category,
                tags=list(draft.tags),
                origin_path=draft.origin_path,
                origin_line=draft.origin_line,
                is_public=draft.is_public,
            )
        except Exception as exc:
            QMessageBox.warning(
                self, "Erro ao atualizar", str(exc)
            )
            return
        self._catalog_panel.refresh()
        self._entry_preview.show_entry(updated)

    @Slot(int)
    def _on_catalog_delete_entry(self, entry_id: int) -> None:
        """Confirm + delete the entry."""
        entry = self._catalog_service.get_entry(entry_id)
        title = entry.title if entry is not None else f"#{entry_id}"
        confirmed = QMessageBox.question(
            self,
            "Excluir entrada",
            f"Tem certeza que deseja excluir “{title}”? Esta ação é "
            "permanente e remove a entrada do banco local.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        try:
            self._catalog_service.delete_entry(entry_id)
        except Exception as exc:
            QMessageBox.warning(
                self, "Erro ao excluir", str(exc)
            )
            return
        self._catalog_panel.refresh()
        self._entry_preview.clear()

    @Slot(int)
    def _on_catalog_insert_into_editor(self, entry_id: int) -> None:
        """Insert the entry's code into the open editor + bounce to explorer."""
        entry = self._catalog_service.get_entry(entry_id)
        if entry is None:
            QMessageBox.warning(
                self, "Erro", f"Entrada {entry_id} não encontrada."
            )
            return
        # If no file is open, just inform the user (insert_text_at_cursor
        # returns False in that case, but we want a clearer message).
        if self._code_editor.current_path() is None:
            QMessageBox.information(
                self,
                "Nenhum arquivo aberto",
                "Abra um arquivo no Explorer antes de inserir um snippet.",
            )
            return
        self._code_editor.insert_text_at_cursor(entry.code)
        # Switch back to the explorer so the user can see what was
        # inserted (catalog mode hides the editor's content focus).
        self._left_panel.show_explorer()

    # ----- Helpers ----------------------------------------------------------

    def _current_theme_name(self) -> str:
        if self._theme_manager is None:
            return "dark"
        return self._theme_manager.effective().value

    # ----- Public API used by tests and future controllers ------------------

    def panels(
        self,
    ) -> tuple[FileExplorerPanel, CodeEditorPanel, VisualizerPanel]:
        """Return the three panels in left-to-right order.

        Kept for back-compat with tests that pre-date the LeftPanel
        refactor. The catalog panel and entry preview are reachable
        via :meth:`left_panel` / :meth:`entry_preview`.
        """
        return (self._file_explorer, self._code_editor, self._visualizer)

    def left_panel(self) -> LeftPanel:
        """Return the LeftPanel container (explorer + catalog stack)."""
        return self._left_panel

    def catalog_panel(self) -> CatalogoPanel:
        """Return the catalog list panel."""
        return self._catalog_panel

    def entry_preview(self) -> EntryPreviewPanel:
        """Return the entry preview panel."""
        return self._entry_preview

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
