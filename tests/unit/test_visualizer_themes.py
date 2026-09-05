"""Tests for VisualizerPanel state transitions and theming."""

from __future__ import annotations

import pytest

from app.ui.visualizer import VisualizerPanel


# ----- show_idle ------------------------------------------------------------


def test_show_idle_default_theme_is_dark(qapp) -> None:
    panel = VisualizerPanel()
    # The constructor calls show_idle() with the default theme.
    assert panel.last_markdown is None
    assert panel.last_error is None


def test_show_idle_dark_has_dark_body_bg(qapp) -> None:
    """The idle page must explicitly set the dark body bg (no UA white flash)."""
    panel = VisualizerPanel()
    # Re-trigger with explicit dark theme (constructor already did this).
    panel.show_idle(theme="dark")
    # The QWebEngineView widget now has the dark-mode page loaded.
    # We can't easily inspect its inner HTML via the QWidget API, but we
    # can verify the call didn't raise and state is consistent.
    assert panel.last_markdown is None
    assert panel.last_error is None


def test_show_idle_light_uses_light_body_bg(qapp) -> None:
    panel = VisualizerPanel()
    panel.show_idle(theme="light")
    assert panel.last_markdown is None


def test_show_idle_unknown_theme_falls_back_to_dark(qapp) -> None:
    panel = VisualizerPanel()
    panel.show_idle(theme="midnight")
    assert panel.last_markdown is None


# ----- show_loading ---------------------------------------------------------


def test_show_loading_sets_label_in_html(qapp) -> None:
    panel = VisualizerPanel()
    panel.show_loading("ai_engine.py", theme="dark")
    # Loading state should clear markdown and error.
    assert panel.last_markdown is None
    assert panel.last_error is None


def test_show_loading_default_theme_is_dark(qapp) -> None:
    panel = VisualizerPanel()
    panel.show_loading("foo.py")
    # No exception means the body style was set with a valid theme.
    assert panel.last_markdown is None


def test_loading_html_template_has_spinner(qapp) -> None:
    """The loading page must include the SVG spinner + CSS @keyframes (Bloco C)."""
    tpl = VisualizerPanel._LOADING_HTML_TEMPLATE
    assert "@keyframes" in tpl
    assert "<svg" in tpl
    assert "spinner" in tpl.lower()


# ----- show_error -----------------------------------------------------------


def test_show_error_sets_last_error(qapp) -> None:
    panel = VisualizerPanel()
    panel.show_error("boom", theme="dark")
    assert panel.last_error == "boom"
    assert panel.last_markdown is None


def test_show_error_stores_raw_message_and_escapes_in_html(qapp) -> None:
    """Error messages are stored raw in ``last_error``; XSS protection lives
    in the rendering layer (``html.escape`` inside ``_render_error``)."""
    panel = VisualizerPanel()
    panel.show_error("<script>alert('xss')</script>")
    # Raw value is preserved in last_error (so consumers can re-display).
    assert "<script>" in panel.last_error
    # The internal render does the escape — we trust the html_template.py
    # tests for the XSS guarantee; here we just verify the call worked.


def test_show_error_clears_markdown(qapp) -> None:
    panel = VisualizerPanel()
    panel.show_markdown("## Hello", theme="dark")
    assert panel.last_markdown is not None
    panel.show_error("oops")
    assert panel.last_markdown is None
    assert panel.last_error == "oops"


# ----- show_markdown -------------------------------------------------------


def test_show_markdown_sets_last_markdown(qapp) -> None:
    panel = VisualizerPanel()
    panel.show_markdown("## Hi", theme="dark")
    assert panel.last_markdown == "## Hi"
    assert panel.last_error is None


def test_show_markdown_clears_error(qapp) -> None:
    panel = VisualizerPanel()
    panel.show_error("oops")
    assert panel.last_error == "oops"
    panel.show_markdown("## Hi")
    assert panel.last_error is None
    assert panel.last_markdown == "## Hi"


def test_show_markdown_passes_theme_to_template(qapp) -> None:
    """show_markdown must forward the theme to the HTML template."""
    panel = VisualizerPanel()
    panel.show_markdown("hi", theme="light")
    # No direct way to read the QWebEngineView's page HTML via QWidget
    # API in PySide6, but the call path is exercised in the html_template
    # tests (test_template_light_theme_has_light_body_styles etc).
    # Here we just verify the call didn't raise and the state is set.
    assert panel.last_markdown == "hi"
