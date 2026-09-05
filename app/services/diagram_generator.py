"""Diagram generation — sanitize LLM output into valid Mermaid.js.

Exposes :class:`BaseDiagramRenderer` (Protocol) and :class:`MermaidRenderer`
(the only concrete implementation in Change 002). The renderer handles
three concerns:

1. **Sanitize** — extract Mermaid syntax from a noisy LLM response.
2. **Validate** — quick keyword / operator check before sending to the browser.
3. **Render to HTML** — produce a self-contained HTML document that loads
   Mermaid.js from a pinned CDN and embeds the diagram.
"""

from __future__ import annotations

import re
from typing import Final, Protocol

from app.services.exceptions import DiagramParsingError


# ---------------------------------------------------------------------------
# Renderer contract
# ---------------------------------------------------------------------------


class BaseDiagramRenderer(Protocol):
    """Structural interface for any diagram backend (Mermaid, PlantUML, etc.).

    Future renderers follow this contract; callers depend on the
    Protocol, not on a concrete class (OCP).
    """

    def sanitize(self, raw_response: str) -> str:
        ...

    def validate(self, diagram_text: str) -> bool:
        ...

    def render_to_html(self, diagram_text: str) -> str:
        ...


# ---------------------------------------------------------------------------
# Mermaid implementation
# ---------------------------------------------------------------------------


class MermaidRenderer:
    """Extract Mermaid.js syntax from LLM output and render it as HTML.

    See ``changes/002-services-layer/design.md`` §3.5 for the
    3-tier sanitize fallback rationale.
    """

    MERMAID_VERSION: Final[str] = "10.9.1"
    MERMAID_CDN: Final[str] = (
        f"https://cdn.jsdelivr.net/npm/mermaid@{MERMAID_VERSION}/dist/mermaid.min.js"
    )

    VALID_KEYWORDS: Final[tuple[str, ...]] = (
        "classDiagram",
        "sequenceDiagram",
        "flowchart",
        "graph",
        "stateDiagram",
        "stateDiagram-v2",
        "erDiagram",
        "gantt",
        "pie",
        "journey",
        "gitGraph",
    )

    _MERMAID_BLOCK_RE: Final[re.Pattern[str]] = re.compile(
        r"```mermaid\s*\n(.*?)```",
        re.DOTALL,
    )
    _GENERIC_BLOCK_RE: Final[re.Pattern[str]] = re.compile(
        r"```(\w+)?\s*\n(.*?)```",
        re.DOTALL,
    )
    _OPERATOR_HINTS: Final[tuple[str, ...]] = (
        "-->",
        "--|>",
        "->>",
        "---",
        "==>",
    )

    # ----- Sanitize ---------------------------------------------------------

    def sanitize(self, raw_response: str) -> str:
        """Extract Mermaid syntax from a (potentially noisy) LLM response.

        1. Look for a ``\\`\\`\\`mermaid ... \\`\\`\\``` fenced block.
        2. Else look for a generic fenced block whose language hint is
           ``mermaid`` or whose body starts with a Mermaid keyword.
        3. Else treat the whole text as Mermaid (caller is responsible
           for subsequent validation).
        4. :class:`DiagramParsingError` is raised **only** when the
           result is empty — the renderer never invents syntax.
        """
        if not raw_response or not raw_response.strip():
            raise DiagramParsingError("Empty response", raw=raw_response)

        # Tier 1: explicit mermaid fence.
        m = self._MERMAID_BLOCK_RE.search(raw_response)
        if m:
            return m.group(1).strip()

        # Tier 2: generic fence with language hint or keyword-starting body.
        for m in self._GENERIC_BLOCK_RE.finditer(raw_response):
            lang = (m.group(1) or "").lower()
            content = m.group(2).strip()
            if "mermaid" in lang:
                return content
            if any(content.startswith(kw) for kw in self.VALID_KEYWORDS):
                return content

        # Tier 3: assume the raw text already is Mermaid.
        text = raw_response.strip()
        if not text:
            raise DiagramParsingError("Empty response", raw=raw_response)
        return text

    # ----- Validate ---------------------------------------------------------

    def validate(self, diagram_text: str) -> bool:
        """Heuristic check: does this look like Mermaid?"""
        if not diagram_text or not diagram_text.strip():
            return False
        first_line = diagram_text.lstrip().splitlines()[0] if diagram_text.lstrip() else ""
        if any(first_line.startswith(kw) for kw in self.VALID_KEYWORDS):
            return True
        if any(op in diagram_text for op in self._OPERATOR_HINTS):
            return True
        return False

    # ----- Render -----------------------------------------------------------

    def render_to_html(self, diagram_text: str) -> str:
        """Produce a self-contained HTML page rendering the given diagram."""
        sanitized = self.sanitize(diagram_text)
        return (
            "<!DOCTYPE html>\n"
            '<html lang="en">\n'
            "<head>\n"
            '    <meta charset="utf-8">\n'
            "    <title>ArchExplorer Diagram</title>\n"
            f'    <script src="{self.MERMAID_CDN}"></script>\n'
            "    <script>\n"
            "        document.addEventListener('DOMContentLoaded', function () {\n"
            "            mermaid.initialize({ startOnLoad: true, securityLevel: 'loose' });\n"
            "        });\n"
            "    </script>\n"
            "    <style>\n"
            "        body { font-family: -apple-system, sans-serif; margin: 0; padding: 1rem; }\n"
            "    </style>\n"
            "</head>\n"
            "<body>\n"
            '    <div class="mermaid">\n'
            f"{sanitized}\n"
            "    </div>\n"
            "</body>\n"
            "</html>\n"
        )
