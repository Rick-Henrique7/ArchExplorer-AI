"""Tests for the MermaidRenderer service."""

from __future__ import annotations

import pytest

from app.services import DiagramParsingError, MermaidRenderer


# ---------------------------------------------------------------------------
# sanitize
# ---------------------------------------------------------------------------


def test_sanitize_extracts_mermaid_block_with_surrounding_text() -> None:
    r = MermaidRenderer()
    raw = "Here is the diagram:\n```mermaid\nclassDiagram\n  A --> B\n```\nDone."
    assert r.sanitize(raw) == "classDiagram\n  A --> B"


def test_sanitize_handles_block_without_leading_text() -> None:
    r = MermaidRenderer()
    raw = "```mermaid\nflowchart LR\n  A --> B\n```"
    assert r.sanitize(raw) == "flowchart LR\n  A --> B"


def test_sanitize_extracts_from_generic_block_with_mermaid_lang() -> None:
    r = MermaidRenderer()
    raw = "```mermaidjs\nsequenceDiagram\n  Alice->>Bob: hi\n```"
    assert r.sanitize(raw) == "sequenceDiagram\n  Alice->>Bob: hi"


def test_sanitize_extracts_from_generic_block_with_keyword_start() -> None:
    r = MermaidRenderer()
    raw = "```\nsequenceDiagram\n  Alice->>Bob: hi\n```"
    assert r.sanitize(raw) == "sequenceDiagram\n  Alice->>Bob: hi"


def test_sanitize_falls_back_to_raw_text_with_keyword() -> None:
    r = MermaidRenderer()
    raw = "classDiagram\n  class A\n  class B"
    assert r.sanitize(raw) == "classDiagram\n  class A\n  class B"


def test_sanitize_returns_raw_text_without_fences() -> None:
    r = MermaidRenderer()
    raw = "graph TD\n  A[Start] --> B[End]"
    assert r.sanitize(raw) == "graph TD\n  A[Start] --> B[End]"


def test_sanitize_strips_whitespace() -> None:
    r = MermaidRenderer()
    raw = "```mermaid\n\n  classDiagram\n    A --> B\n  \n```"
    assert r.sanitize(raw) == "classDiagram\n    A --> B"


def test_sanitize_takes_first_mermaid_block_when_multiple() -> None:
    r = MermaidRenderer()
    raw = (
        "First:\n```mermaid\nclassDiagram\n  A\n```\n"
        "Second:\n```mermaid\nsequenceDiagram\n  B\n```"
    )
    assert r.sanitize(raw) == "classDiagram\n  A"


@pytest.mark.parametrize("empty", ["", "   ", "\n\n\t  "])
def test_sanitize_raises_on_empty(empty: str) -> None:
    with pytest.raises(DiagramParsingError):
        MermaidRenderer().sanitize(empty)


def test_sanitize_preserves_original_in_exception_context() -> None:
    r = MermaidRenderer()
    with pytest.raises(DiagramParsingError) as exc_info:
        r.sanitize("")
    # The exception context carries the raw input for diagnostics.
    assert exc_info.value.context.get("raw") == ""


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "classDiagram\n  A --> B",
        "sequenceDiagram\n  A->>B: hi",
        "flowchart LR\n  A --> B",
        "graph TD\n  A --> B",
        "stateDiagram-v2\n  [*] --> A",
        "erDiagram\n  CUSTOMER ||--o{ ORDER : places",
    ],
)
def test_validate_recognizes_valid_keywords(text: str) -> None:
    assert MermaidRenderer().validate(text) is True


def test_validate_detects_arrow_operators() -> None:
    r = MermaidRenderer()
    assert r.validate("some text --> more text") is True
    assert r.validate("x --|> y") is True
    assert r.validate("a --- b") is True


@pytest.mark.parametrize("text", ["", "   ", "\n\n"])
def test_validate_rejects_empty(text: str) -> None:
    assert MermaidRenderer().validate(text) is False


def test_validate_rejects_unrelated_text() -> None:
    r = MermaidRenderer()
    assert r.validate("this is not a diagram") is False
    assert r.validate("Hello, world!") is False


# ---------------------------------------------------------------------------
# render_to_html
# ---------------------------------------------------------------------------


def test_render_to_html_includes_mermaid_cdn() -> None:
    html = MermaidRenderer().render_to_html("classDiagram\n  A --> B")
    assert "mermaid.min.js" in html
    assert MermaidRenderer.MERMAID_VERSION in html


def test_render_to_html_sanitizes_input() -> None:
    r = MermaidRenderer()
    raw = "Some text\n```mermaid\nclassDiagram\n  A\n```\nMore text"
    html = r.render_to_html(raw)
    assert "classDiagram" in html
    assert "Some text" not in html
    assert "More text" not in html
    assert "```" not in html


def test_render_to_html_raises_on_empty() -> None:
    r = MermaidRenderer()
    with pytest.raises(DiagramParsingError):
        r.render_to_html("")


def test_render_to_html_returns_full_html_document() -> None:
    html = MermaidRenderer().render_to_html("classDiagram\n  A")
    assert html.startswith("<!DOCTYPE html>")
    assert "<html" in html
    assert "<head>" in html
    assert "<body>" in html
    assert "</body>" in html
    assert "</html>" in html
    assert '<div class="mermaid">' in html


def test_render_to_html_initializes_mermaid_via_domcontentloaded() -> None:
    html = MermaidRenderer().render_to_html("classDiagram\n  A")
    assert "DOMContentLoaded" in html
    assert "mermaid.initialize" in html


# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------


def test_mermaid_version_is_pinned() -> None:
    assert MermaidRenderer.MERMAID_VERSION == "10.9.1"


def test_mermaid_cdn_uses_pinned_version() -> None:
    assert MermaidRenderer.MERMAID_VERSION in MermaidRenderer.MERMAID_CDN
    assert MermaidRenderer.MERMAID_CDN.startswith("https://")
    assert "cdn.jsdelivr.net" in MermaidRenderer.MERMAID_CDN
