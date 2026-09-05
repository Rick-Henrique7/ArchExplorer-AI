"""Tests for the HTML template builder (pure string output)."""

from __future__ import annotations

from app.ui.html_template import (
    GITHUB_MARKDOWN_CSS,
    GITHUB_MARKDOWN_CSS_VERSION,
    MARKED_CDN,
    MARKED_VERSION,
    MERMAID_CDN,
    build_html_template,
)


def test_template_dark_theme_has_dark_body_styles() -> None:
    """Dark theme must set body background + color explicitly (no UA default)."""
    html = build_html_template("hello", theme="dark")
    # Body must have an explicit dark background
    assert "background-color: #0d1117" in html
    # And an explicit light text color
    assert "color: #c9d1d9" in html


def test_template_light_theme_has_light_body_styles() -> None:
    """Light theme must set body background + color explicitly."""
    html = build_html_template("hello", theme="light")
    assert "background-color: #ffffff" in html
    assert "color: #24292f" in html


def test_template_dark_uses_dark_css_variant() -> None:
    html = build_html_template("hi", theme="dark")
    assert "github-markdown-dark" in html
    assert "github-markdown-light" not in html


def test_template_light_uses_light_css_variant() -> None:
    html = build_html_template("hi", theme="light")
    assert "github-markdown-light" in html
    assert "github-markdown-dark" not in html


def test_template_default_theme_is_dark() -> None:
    """Calling without theme arg defaults to dark for backward compatibility."""
    html = build_html_template("hi")
    assert "background-color: #0d1117" in html
    assert "github-markdown-dark" in html


def test_template_unknown_theme_falls_back_to_dark() -> None:
    """Unknown theme string falls back to dark (safe default)."""
    html = build_html_template("hi", theme="midnight-purple")
    assert "background-color: #0d1117" in html
    assert "github-markdown-dark" in html


def test_template_includes_marked_cdn() -> None:
    html = build_html_template("")
    assert "marked.min.js" in html
    assert MARKED_VERSION in html
    assert MARKED_CDN in html


def test_template_includes_mermaid_cdn() -> None:
    html = build_html_template("")
    assert "mermaid.min.js" in html
    assert "10.9.1" in html
    assert MERMAID_CDN in html


def test_template_includes_github_markdown_css() -> None:
    html = build_html_template("")
    assert "github-markdown" in html
    assert GITHUB_MARKDOWN_CSS in html
    assert GITHUB_MARKDOWN_CSS_VERSION in html


def test_template_contains_raw_md_pre() -> None:
    html = build_html_template("hello world")
    assert 'id="raw-md"' in html
    assert "display:none" in html


def test_template_escapes_html_in_markdown_xss() -> None:
    """Markdown with <script> must not produce executable script tags."""
    html = build_html_template("<script>alert('xss')</script>")
    # Raw <script> should not appear in the template (it's escaped).
    assert "<script>alert" not in html
    # The escaped form is present inside the <pre id="raw-md"> element.
    assert "&lt;script&gt;" in html


def test_template_escapes_ampersand() -> None:
    html = build_html_template("A & B")
    assert "A &amp; B" in html


def test_template_escapes_quotes() -> None:
    html = build_html_template('"hello" and \'world\'')
    assert "&quot;hello&quot;" in html


def test_template_returns_full_html_document() -> None:
    html = build_html_template("test")
    assert html.startswith("<!DOCTYPE html>")
    assert "<html" in html
    assert "</html>" in html
    assert "<body>" in html
    assert "</body>" in html


def test_template_includes_error_handler() -> None:
    html = build_html_template("")
    assert "Failed to load dependencies" in html
    assert "window.addEventListener('error'" in html


def test_template_handles_empty_markdown() -> None:
    html = build_html_template("")
    assert html  # non-empty
    assert "raw-md" in html


def test_template_intercepts_mermaid_blocks_via_custom_renderer() -> None:
    """The custom marked renderer must produce <pre class='mermaid'> for ```mermaid blocks."""
    html = build_html_template("")
    assert 'class="mermaid"' in html
    # The renderer intercepts via lang check
    assert "(lang || '').toLowerCase() === 'mermaid'" in html


def test_template_security_level_is_loose() -> None:
    """Mermaid securityLevel must be 'loose' so LLM-rendered HTML is allowed."""
    html = build_html_template("")
    assert "securityLevel: 'loose'" in html


def test_cdns_are_https() -> None:
    assert MARKED_CDN.startswith("https://")
    assert MERMAID_CDN.startswith("https://")
    assert GITHUB_MARKDOWN_CSS.startswith("https://")
