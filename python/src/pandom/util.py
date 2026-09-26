"""Helpers: text of nodes, metadata to and from Python values."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ._core import Node, NodeList
from ._types import (
    Cite,
    Code,
    LineBreak,
    Math,
    MetaBlocks,
    MetaBool,
    MetaInlines,
    MetaList,
    MetaMap,
    MetaString,
    MetaValue,
    Note,
    Quoted,
    QuoteType,
    RawInline,
    SoftBreak,
    Space,
    Str,
)
from ._walk import _walk_fields

__all__ = ["from_python", "stringify", "to_python"]

_QUOTES = {QuoteType.SingleQuote: ("‘", "’"), QuoteType.DoubleQuote: ("“", "”")}


def stringify(value: Any) -> str:
    """The text of a node (or list of nodes), without markup.

    As pandoc's ``stringify``: spaces and breaks become " ", quotes become
    curly quotes, notes and citations' data are dropped, code and math keep
    their text.
    """
    out: list[str] = []
    _text(value, out)
    return "".join(out)


def _text(value: Any, out: list[str]) -> None:
    if isinstance(value, (list, tuple)):
        for x in value:
            _text(x, out)
        return
    if isinstance(value, dict):
        for x in value.values():
            _text(x, out)
        return
    if not isinstance(value, Node):
        return
    if isinstance(value, (Str, MetaString)):
        out.append(value.text)
    elif isinstance(value, (Space, SoftBreak, LineBreak)):
        out.append(" ")
    elif isinstance(value, (Code, Math)):
        out.append(value.text)
    elif isinstance(value, RawInline):
        if value.format == "html" and value.text.startswith("<br"):
            out.append(" ")
    elif isinstance(value, Note):
        pass
    elif isinstance(value, Cite):
        _text(value.content, out)
    elif isinstance(value, Quoted):
        left, right = _QUOTES[value.quote_type]
        out.append(left)
        _text(value.content, out)
        out.append(right)
    elif isinstance(value, MetaBool):
        out.append("true" if value.value else "false")
    else:
        for f, _ in _walk_fields(type(value)):
            _text(getattr(value, f), out)


def to_python(value: MetaValue | Mapping[str, MetaValue]) -> Any:
    """Metadata as plain Python: str, bool, list, dict.

    ``MetaInlines`` and ``MetaBlocks`` become their text (``stringify``).
    """
    if isinstance(value, Mapping):
        return {k: to_python(v) for k, v in value.items()}
    if isinstance(value, MetaMap):
        return {k: to_python(v) for k, v in value.content.items()}
    if isinstance(value, MetaList):
        return [to_python(v) for v in value.content]
    if isinstance(value, MetaBool):
        return value.value
    if isinstance(value, MetaString):
        return value.text
    if isinstance(value, (MetaInlines, MetaBlocks)):
        return stringify(value.content)
    raise TypeError(f"not metadata: {value!r}")


def from_python(value: Any) -> MetaValue | None:
    """A Python value as metadata, or None if it has no obvious form.

    str -> MetaString, bool -> MetaBool, list -> MetaList, dict -> MetaMap,
    int and float -> MetaString (YAML numbers read by pandoc are strings too).
    Setting metadata converts with this: ``doc.meta["draft"] = True``.
    """
    if isinstance(value, MetaValue):
        return value
    if isinstance(value, bool):
        return MetaBool(value)
    if isinstance(value, str):
        return MetaString(value)
    if isinstance(value, (int, float)):
        return MetaString(str(value))
    if isinstance(value, Mapping):
        return MetaMap({k: _meta(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)) and not isinstance(value, NodeList):
        return MetaList(*[_meta(v) for v in value])
    return None


def _meta(value: Any) -> Any:
    converted = from_python(value)
    return value if converted is None else converted


MetaValue._convert = staticmethod(from_python)  # type: ignore[attr-defined]
