"""Filters: functions on node types, run as a pandoc filter or in Python.

    from libpandoc_ast import Filter, Header

    f = Filter()

    @f.on(Header)
    def demote(h):
        h.level += 1

    if __name__ == "__main__":
        f.main()  # pandoc --filter ./demote.py

The same ``f`` also runs in Python: ``f(doc)`` on a ``Pandoc``, or
``libpandoc.convert(..., filters=[f])``.
"""

from __future__ import annotations

import inspect
import io
import json
import sys
from collections.abc import Callable, Iterable
from typing import Any, TypeVar

from ._core import Node, add_note
from ._types import Pandoc
from ._walk import Context, walk

__all__ = ["Filter", "run"]

F = TypeVar("F", bound=Callable[..., Any])


class Filter:
    """Functions to apply to nodes, by type.

    A function takes the node, and optionally a ``Context`` (where the node
    is, the document, the output format), and returns ``None`` to keep the
    node, a node to replace it, or a list of nodes to splice in its place
    (``[]`` deletes it).

    Each node gets the function registered for its class, or else for the
    closest base class (``Inline``, ``Block``, ...); ``Pandoc`` itself too,
    last. The walk is bottom-up (children first) unless ``top_down=True``.
    """

    def __init__(self, *, top_down: bool = False, name: str | None = None) -> None:
        self.top_down = top_down
        self.name = name
        self._handlers: dict[type, tuple[Callable[..., Any], bool]] = {}
        self._lookup: dict[type, tuple[Callable[..., Any], bool] | None] = {}

    def on(self, *types: type) -> Callable[[F], F]:
        """Register the decorated function for nodes of these types."""
        for ty in types:
            if not (isinstance(ty, type) and issubclass(ty, Node)):
                raise TypeError(f"Filter.on() takes AST classes, got {ty!r}")

        def register(fn: F) -> F:
            wants_ctx = _takes_context(fn)
            for ty in types:
                if ty in self._handlers:
                    raise ValueError(
                        f"{ty.__name__} already has a function in this "
                        f"filter ({self._handlers[ty][0].__name__}); "
                        "combine them, or use a second Filter"
                    )
                self._handlers[ty] = (fn, wants_ctx)
            self._lookup.clear()
            return fn

        return register

    def _handler(self, ty: type) -> tuple[Callable[..., Any], bool] | None:
        try:
            return self._lookup[ty]
        except KeyError:
            found = next((self._handlers[t] for t in ty.__mro__ if t in self._handlers), None)
            self._lookup[ty] = found
            return found

    def _action(self, node: Node, ctx: Context) -> Any:
        fn, wants_ctx = self._handler(type(node))  # type: ignore[misc]
        try:
            return fn(node, ctx) if wants_ctx else fn(node)
        except Exception as e:
            if not getattr(e, "_libpandoc_ast_noted", False):
                add_note(
                    e,
                    f"in filter function {fn.__qualname__}, on the "
                    f"{type(node).__name__} at {ctx.where}",
                )
                e._libpandoc_ast_noted = True  # type: ignore[attr-defined]
            raise

    def __call__(self, doc: Pandoc, format: str | None = None) -> Pandoc:
        """Apply the filter to a document (in place), and return it."""
        result = walk(
            doc,
            self._action,
            top_down=self.top_down,
            format=format,
            wants=lambda ty: self._handler(ty) is not None,
        )
        if not isinstance(result, Pandoc):
            raise TypeError(
                f"the function for Pandoc returned {type(result).__name__}, not a Pandoc"
            )
        return result

    def run_json(self, text: str | bytes, format: str | None = None) -> str:
        """Apply the filter to a document in pandoc's JSON."""
        doc = Pandoc.from_json(json.loads(text))
        return json.dumps(self(doc, format).to_json(), ensure_ascii=False, separators=(",", ":"))

    def main(self, argv: list[str] | None = None) -> None:
        """Run as a pandoc JSON filter: a document on stdin, to stdout.

        pandoc passes the output format as the first argument.
        """
        argv = sys.argv[1:] if argv is None else argv
        stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8")
        out = self.run_json(stdin.read(), argv[0] if argv else None)
        stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
        stdout.write(out)
        stdout.flush()
        stdout.detach()


def run(doc: Pandoc, filters: Iterable[Filter], format: str | None = None) -> Pandoc:
    """Apply filters in turn, as ``pandoc --filter a --filter b`` does."""
    for f in filters:
        doc = f(doc, format)
    return doc


def _takes_context(fn: Callable[..., Any]) -> bool:
    try:
        params = list(inspect.signature(fn).parameters.values())
    except (TypeError, ValueError):
        return False
    positional = [p for p in params if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
    if any(p.kind == p.VAR_POSITIONAL for p in params):
        return True
    if not 1 <= len(positional) <= 2:
        raise TypeError(
            f"a filter function takes the node, and optionally a Context; "
            f"{fn.__qualname__} takes {len(positional)} arguments"
        )
    return len(positional) == 2
