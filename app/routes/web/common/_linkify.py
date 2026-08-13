"""Safe rich-text helpers for user-authored content."""

from __future__ import annotations

import re

from markupsafe import Markup, escape

_URL_RE = re.compile(r"(?i)(?<![\w@])((?:https?://|www\.)[^\s<]+)")
_TRAILING_PUNCTUATION = ".,!?;:"


def _split_trailing_punctuation(url: str) -> tuple[str, str]:
    """Keep sentence punctuation outside a detected URL."""
    trimmed = url.rstrip(_TRAILING_PUNCTUATION)
    trailing = url[len(trimmed) :]
    while trimmed.endswith(")") and trimmed.count(")") > trimmed.count("("):
        trimmed = trimmed[:-1]
        trailing = ")" + trailing
    return trimmed, trailing


def linkify(text: str | None) -> Markup:
    """Escape text and convert HTTP(S) and ``www.`` URLs into safe links."""
    source = text or ""
    parts: list[Markup] = []
    position = 0
    for match in _URL_RE.finditer(source):
        url, trailing = _split_trailing_punctuation(match.group(1))
        if not url:
            continue
        href = url if url.startswith(("http://", "https://")) else f"https://{url}"
        parts.extend(
            (
                Markup(escape(source[position : match.start()])),
                Markup('<a href="')
                + escape(href)
                + Markup('" target="_blank" rel="noopener noreferrer" class="underline underline-offset-2 focus-visible:outline-offset-2">')
                + escape(url)
                + Markup("</a>"),
                Markup(escape(trailing)),
            )
        )
        position = match.end()
    parts.append(Markup(escape(source[position:])))
    return Markup("").join(parts)
