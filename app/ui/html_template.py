"""Self-contained HTML page for rendering LLM markdown responses with Mermaid support.

The page loads three libraries from jsDelivr (all pinned to a specific version):

- ``marked@<ver>`` — markdown parser (https://marked.js.org)
- ``mermaid@10.9.1`` — Mermaid block renderer (already pinned in Change 002)
- ``github-markdown-css@<ver>`` — readable typography for the dark theme

The markdown text is HTML-escaped and embedded in a hidden ``<pre>`` element;
a small script reads it via ``.textContent`` (which decodes HTML entities back
to text), parses it with ``marked``, and replaces the content area. Mermaid
fenced code blocks (``\\`\\`\\`mermaid ... \\`\\`\\```) are intercepted by a
custom ``marked`` renderer and turned into ``<pre class="mermaid">`` elements
which Mermaid.js auto-renders on page load.

The function is pure (no Qt) and easily unit-testable as a string builder.
"""

from __future__ import annotations

from html import escape

# --- Pinned CDN URLs --------------------------------------------------------

MARKED_VERSION: str = "11.1.1"
MARKED_CDN: str = (
    f"https://cdn.jsdelivr.net/npm/marked@{MARKED_VERSION}/marked.min.js"
)

GITHUB_MARKDOWN_CSS_VERSION: str = "5.5.1"
GITHUB_MARKDOWN_CSS: str = (
    f"https://cdn.jsdelivr.net/npm/github-markdown-css"
    f"@{GITHUB_MARKDOWN_CSS_VERSION}/github-markdown-dark.min.css"
)

MERMAID_CDN: str = "https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"

# --- HTML template ----------------------------------------------------------
# Note: {{ and }} are escaped braces for str.format().

_HTML_TEMPLATE: str = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>ArchExplorer</title>
  <link rel="stylesheet" href="{github_markdown_css}">
  <script src="{marked_cdn}"></script>
  <script src="{mermaid_cdn}"></script>
  <style>
    body {{ box-sizing: border-box; margin: 0 auto; padding: 24px; max-width: 980px; }}
    .markdown-body {{ background: transparent; }}
  </style>
  <script>
    window.addEventListener('error', function(e) {{
      document.getElementById('content').innerHTML =
        '<h1>Failed to load dependencies</h1><p>' + e.message + '</p>';
    }});
  </script>
</head>
<body>
  <article class="markdown-body" id="content">Loading...</article>
  <pre id="raw-md" style="display:none">{raw_md}</pre>
  <script>
    (function() {{
      var md = document.getElementById('raw-md').textContent;
      var renderer = new marked.Renderer();
      var origCode = renderer.code.bind(renderer);
      renderer.code = function(code, lang) {{
        if ((lang || '').toLowerCase() === 'mermaid') {{
          return '<pre class="mermaid">' + code + '</pre>';
        }}
        return origCode(code, lang);
      }};
      marked.use({{ renderer: renderer }});
      document.getElementById('content').innerHTML = marked.parse(md);
      mermaid.initialize({{ startOnLoad: true, securityLevel: 'loose' }});
    }})();
  </script>
</body>
</html>
"""


def build_html_template(markdown_text: str) -> str:
    """Build a self-contained HTML page that renders markdown with Mermaid support.

    Parameters
    ----------
    markdown_text:
        Raw markdown response from the LLM. Will be HTML-escaped before
        embedding in the page to prevent XSS via markdown payloads.

    Returns
    -------
    A complete HTML document as a string, ready to be passed to
    ``QWebEngineView.setHtml()``.
    """
    escaped = escape(markdown_text)
    return _HTML_TEMPLATE.format(
        github_markdown_css=GITHUB_MARKDOWN_CSS,
        marked_cdn=MARKED_CDN,
        mermaid_cdn=MERMAID_CDN,
        raw_md=escaped,
    )
