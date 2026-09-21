"""Tests for LpsInspectorPanel (Change 007 — Bloco D — task D11 extra)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.services import LpsComponent
from app.ui.lps_inspector_panel import LpsInspectorPanel
from app.ui.lps_node_item import LpsNodeItem


def _make_component() -> LpsComponent:
    return LpsComponent(
        id="c-1", name="OAuth", category="architecture",
        description="OAuth 2.0 provider",
        code_snippet="class OAuth: pass",
        svg_icon_path=None, jinja_template="services/fastapi_app.py.j2",
        metadata={"language": "python"},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def panel(qapp) -> LpsInspectorPanel:
    return LpsInspectorPanel()


def test_initial_state_is_empty(panel: LpsInspectorPanel) -> None:
    """No node → form disabled, labels show em-dashes."""
    assert panel._label_input.isEnabled() is False
    assert panel._variability_combo.isEnabled() is False
    assert panel._apply_btn.isEnabled() is False
    assert panel._delete_btn.isEnabled() is False


def test_show_node_populates_form(panel: LpsInspectorPanel, qapp) -> None:
    node = LpsNodeItem(node_id="n1", label="My DB", variability="MANDATORY",
                       component_id="c-1", x=10, y=20)
    panel.show_node(node, component=_make_component())
    assert panel._id_label.text() == "n1"
    assert panel._label_input.text() == "My DB"
    assert panel._variability_combo.currentText() == "MANDATORY"
    assert panel._component_id_label.text() == "c-1"
    # Component preview populated.
    assert "OAuth" in panel._comp_name.text()
    assert "fastapi_app" in panel._comp_template.text()
    assert "class OAuth" in panel._comp_snippet.toPlainText()
    # Form buttons enabled.
    assert panel._apply_btn.isEnabled() is True
    assert panel._delete_btn.isEnabled() is True


def test_show_node_without_component(panel: LpsInspectorPanel, qapp) -> None:
    node = LpsNodeItem(node_id="x", label="X", variability="OPTIONAL")
    panel.show_node(node)
    assert panel._comp_name.text() == "—"
    assert panel._comp_template.text() == "Template: —"


def test_clear_node_resets_form(panel: LpsInspectorPanel, qapp) -> None:
    node = LpsNodeItem(node_id="n1", label="X", variability="OPTIONAL")
    panel.show_node(node, component=_make_component())
    panel.clear_node()
    assert panel._label_input.text() == ""
    assert panel._variability_combo.currentIndex() == -1
    assert panel._apply_btn.isEnabled() is False


def test_apply_emits_node_edited_with_changes(panel: LpsInspectorPanel, qapp) -> None:
    node = LpsNodeItem(node_id="n1", label="Original", variability="OPTIONAL")
    panel.show_node(node)
    panel._label_input.setText("Edited label")
    panel._variability_combo.setCurrentText("MANDATORY")
    received: list = []
    panel.node_edited.connect(lambda nid, edits: received.append((nid, edits)))
    panel._on_apply()
    assert len(received) == 1
    nid, edits = received[0]
    assert nid == "n1"
    assert edits == {"label": "Edited label", "variability": "MANDATORY"}


def test_delete_emits_signal(panel: LpsInspectorPanel, qapp) -> None:
    node = LpsNodeItem(node_id="n-del", label="X")
    panel.show_node(node)
    received: list[str] = []
    panel.node_deleted.connect(received.append)
    panel._on_delete()
    assert received == ["n-del"]


def test_apply_without_node_is_noop(panel: LpsInspectorPanel, qapp) -> None:
    """Apply on an empty panel emits nothing."""
    received: list = []
    panel.node_edited.connect(lambda *a: received.append(a))
    panel._on_apply()
    assert received == []


def test_variability_combo_lists_all_4_options(panel: LpsInspectorPanel) -> None:
    items = [panel._variability_combo.itemText(i)
             for i in range(panel._variability_combo.count())]
    assert items == ["ROOT", "MANDATORY", "OPTIONAL", "ALTERNATIVE"]
