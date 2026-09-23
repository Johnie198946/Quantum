"""Validation and hardening for model-generated, self-contained HTML tools."""

from __future__ import annotations

import re

MAX_HTML_BYTES = 512_000
_CSP = (
    "default-src 'none'; img-src data: blob:; style-src 'unsafe-inline'; "
    "script-src 'unsafe-inline'; font-src data:; media-src data: blob:; "
    "connect-src 'none'; form-action 'none'; frame-src 'none'; base-uri 'none'"
)
_FORBIDDEN = (
    (r"<(?:iframe|frame|object|embed|base)\b", "embedded or base content"),
    (r"<meta\b[^>]*http-equiv\s*=\s*['\"]?refresh", "meta refresh"),
    (r"\b(?:src|href|action)\s*=\s*['\"]\s*(?:https?:)?//", "external URL"),
    (r"\b(?:fetch|XMLHttpRequest|WebSocket|EventSource|sendBeacon)\s*\(", "network API"),
    (r"\bwindow\.open\s*\(", "new window navigation"),
    (r"\bdocument\.cookie\b", "cookie access"),
)


def secure_html_tool(content: str) -> str:
    """Return a CSP-confined HTML document or fail closed."""
    html = content.strip()
    html = re.sub(r"^```(?:html)?\s*|\s*```$", "", html, flags=re.I)
    if len(html.encode("utf-8")) > MAX_HTML_BYTES:
        raise ValueError("HTML tool exceeds 512 KB")
    if not re.search(r"<!doctype\s+html>", html, re.I):
        raise ValueError("HTML tool must start with <!doctype html>")
    if not re.search(r"<html\b", html, re.I) or not re.search(r"</html>\s*$", html, re.I):
        raise ValueError("HTML tool must be a complete document")
    if not re.search(r"<head\b[^>]*>", html, re.I) or not re.search(r"</head>", html, re.I):
        raise ValueError("HTML tool must include a head element")
    for pattern, label in _FORBIDDEN:
        if re.search(pattern, html, re.I):
            raise ValueError(f"HTML tool contains forbidden {label}")
    if not re.search(r"<meta\b[^>]*name\s*=\s*['\"]viewport['\"]", html, re.I):
        raise ValueError("HTML tool requires a responsive viewport")
    if not re.search(r"<title\b[^>]*>.*?</title>", html, re.I | re.S):
        raise ValueError("HTML tool requires a title")
    csp = f'<meta http-equiv="Content-Security-Policy" content="{_CSP}">'
    html, replacements = re.subn(
        r"<head\b([^>]*)>", rf"<head\1>\n{csp}", html, count=1, flags=re.I
    )
    if replacements != 1:
        raise ValueError("HTML tool could not be confined with CSP")
    return html
