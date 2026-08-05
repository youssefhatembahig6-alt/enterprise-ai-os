"""Deterministic document rendering (spec FR-032, FR-012a, research R4).

Three controls make output byte-identical on every platform:

* text is joined with explicit ``\\n`` and encoded to UTF-8 here, so nothing is ever
  written through Python's text mode — which on Windows would translate to CRLF and
  silently change every file's bytes;
* no byte-order mark, and no generation timestamp anywhere in a document body;
* decimals are quantised before formatting, and no locale-sensitive formatting API
  is used, so number rendering cannot vary by host.

Templates are plain Python string builders rather than Jinja files. For content this
regular, a template engine adds a dependency whose whitespace handling becomes one
more thing that has to be pinned for determinism.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal

__all__ = ["Document", "encode", "render"]


class Document:
    """Accumulates lines and encodes them deterministically."""

    __slots__ = ("_lines",)

    def __init__(self) -> None:
        self._lines: list[str] = []

    def heading(self, text: str, level: int = 1) -> Document:
        self._lines.append(f"{'#' * level} {text}")
        self._lines.append("")
        return self

    def para(self, text: str) -> Document:
        self._lines.append(text.strip())
        self._lines.append("")
        return self

    def bullet(self, text: str) -> Document:
        self._lines.append(f"- {text.strip()}")
        return self

    def bullets(self, items: list[str]) -> Document:
        for item in items:
            self.bullet(item)
        self._lines.append("")
        return self

    def field(self, label: str, value: object) -> Document:
        self._lines.append(f"**{label}:** {_format(value)}")
        return self

    def blank(self) -> Document:
        self._lines.append("")
        return self

    def rule(self) -> Document:
        self._lines.append("---")
        self._lines.append("")
        return self

    def text(self) -> str:
        # Collapse trailing blanks so a document's tail cannot vary with how it was
        # assembled, then guarantee exactly one final newline.
        lines = list(self._lines)
        while lines and lines[-1] == "":
            lines.pop()
        return "\n".join(lines) + "\n"

    def encode(self) -> bytes:
        return encode(self.text())


def _format(value: object) -> str:
    if isinstance(value, Decimal):
        return f"{value.quantize(Decimal('0.01')):f}"
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def encode(text: str) -> bytes:
    """UTF-8, LF, no BOM — the only way documents are written to bytes."""
    normalised = text.replace("\r\n", "\n").replace("\r", "\n")
    return normalised.encode("utf-8")


def render(document: Document) -> tuple[bytes, str, int]:
    """Return ``(content, sha256, byte_size)`` for a finished document."""
    content = document.encode()
    return content, hashlib.sha256(content).hexdigest(), len(content)
