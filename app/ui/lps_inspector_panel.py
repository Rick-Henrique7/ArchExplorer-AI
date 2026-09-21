"""LpsInspectorPanel — form for editing the selected canvas node (Change 007).

Shows the fields of the currently selected :class:`LpsNodeItem`:

- Label (free text)
- Variability (combo: ROOT / MANDATORY / OPTIONAL / ALTERNATIVE)
- Component id (read-only — set when the node was dropped from the palette)

Plus a small "Componente referenciado" panel showing the
:class:`LpsComponent` that the node points at (read-only), so the
user can see the snippet/template path without leaving the canvas.

When the user changes the form, the panel emits
:attr:`node_edited` with the new values so MainWindow can update
the canvas (and persist).
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.services import LpsComponent
from app.ui.lps_node_item import LpsNodeItem


class LpsInspectorPanel(QWidget):
    """Right-column form for the currently selected node."""

    node_edited = Signal(str, dict)   # node_id, {field: value}
    node_deleted = Signal(str)        # node_id

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current_node: LpsNodeItem | None = None
        self._current_component: LpsComponent | None = None
        self._build_ui()
        self._show_empty_state()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        title = QLabel("Inspector", self)
        font = title.font()
        font.setBold(True)
        font.setPointSize(11)
        title.setFont(font)
        layout.addWidget(title)

        # --- Form ----------------------------------------------------------
        form_box = QGroupBox("Nó selecionado", self)
        form = QFormLayout(form_box)
        form.setContentsMargins(8, 8, 8, 8)

        self._id_label = QLabel("—", self)
        self._id_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow("ID:", self._id_label)

        self._label_input = QLineEdit(self)
        self._label_input.setPlaceholderText("Rótulo do nó")
        form.addRow("Rótulo:", self._label_input)

        self._variability_combo = QComboBox(self)
        for v in ("ROOT", "MANDATORY", "OPTIONAL", "ALTERNATIVE"):
            self._variability_combo.addItem(v)
        form.addRow("Variabilidade:", self._variability_combo)

        self._component_id_label = QLabel("—", self)
        form.addRow("Componente ID:", self._component_id_label)

        layout.addWidget(form_box)

        # --- Action row ---------------------------------------------------
        actions = QWidget(self)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        self._apply_btn = QPushButton("Aplicar", self)
        self._apply_btn.clicked.connect(self._on_apply)
        actions_layout.addWidget(self._apply_btn)
        self._delete_btn = QPushButton("Excluir", self)
        self._delete_btn.clicked.connect(self._on_delete)
        actions_layout.addWidget(self._delete_btn)
        actions_layout.addStretch(1)
        layout.addWidget(actions)

        # --- Component preview --------------------------------------------
        comp_box = QGroupBox("Componente referenciado", self)
        comp_layout = QVBoxLayout(comp_box)
        comp_layout.setContentsMargins(8, 8, 8, 8)
        self._comp_name = QLabel("—", comp_box)
        self._comp_name.setWordWrap(True)
        comp_layout.addWidget(self._comp_name)
        self._comp_template = QLabel("Template: —", comp_box)
        self._comp_template.setWordWrap(True)
        comp_layout.addWidget(self._comp_template)
        self._comp_snippet = QPlainTextEdit(comp_box)
        self._comp_snippet.setReadOnly(True)
        self._comp_snippet.setMaximumHeight(140)
        self._comp_snippet.setPlaceholderText("Sem snippet")
        comp_layout.addWidget(self._comp_snippet)
        layout.addWidget(comp_box, stretch=1)

        # Default: everything disabled until a node is selected.
        self._set_form_enabled(False)

    # ----- Public API -----------------------------------------------------

    def show_node(
        self,
        node: LpsNodeItem,
        *,
        component: LpsComponent | None = None,
    ) -> None:
        """Populate the form with the node's current values."""
        self._current_node = node
        self._current_component = component
        self._id_label.setText(node.node_id)
        self._label_input.setText(node.label)
        idx = self._variability_combo.findText(node.variability)
        if idx >= 0:
            self._variability_combo.setCurrentIndex(idx)
        comp_id = node.component_id or "—"
        self._component_id_label.setText(comp_id)
        if component is not None:
            self._comp_name.setText(f"{component.name} ({component.category})")
            self._comp_template.setText(
                f"Template: {component.jinja_template or '—'}"
            )
            self._comp_snippet.setPlainText(component.code_snippet or "")
        else:
            self._comp_name.setText("—")
            self._comp_template.setText("Template: —")
            self._comp_snippet.setPlainText("")
        self._set_form_enabled(True)

    def clear_node(self) -> None:
        """Reset the form to its empty state."""
        self._current_node = None
        self._current_component = None
        self._show_empty_state()

    # ----- Internal -------------------------------------------------------

    def _show_empty_state(self) -> None:
        self._id_label.setText("—")
        self._label_input.setText("")
        self._variability_combo.setCurrentIndex(-1)
        self._component_id_label.setText("—")
        self._comp_name.setText("—")
        self._comp_template.setText("Template: —")
        self._comp_snippet.setPlainText("")
        self._set_form_enabled(False)

    def _set_form_enabled(self, enabled: bool) -> None:
        self._label_input.setEnabled(enabled)
        self._variability_combo.setEnabled(enabled)
        self._apply_btn.setEnabled(enabled)
        self._delete_btn.setEnabled(enabled)

    def _on_apply(self) -> None:
        if self._current_node is None:
            return
        edits: dict[str, Any] = {
            "label": self._label_input.text().strip(),
            "variability": self._variability_combo.currentText(),
        }
        # Strip empties so the canvas only updates changed fields.
        edits = {k: v for k, v in edits.items() if v}
        self.node_edited.emit(self._current_node.node_id, edits)

    def _on_delete(self) -> None:
        if self._current_node is None:
            return
        self.node_deleted.emit(self._current_node.node_id)
