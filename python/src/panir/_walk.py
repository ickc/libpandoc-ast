"""Walking the AST: visiting every node, replacing, splicing, deleting.

Generic over the declarations, like ``_core``: a node's children are the
values of its fields whose type can hold nodes.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ._core import (
    ASTTypeError,
    Node,
    NodeList,
    _ClassSpec,
    _describe,
    _ListSpec,
    _MapSpec,
    _MaybeSpec,
    _Spec,
    _TupleSpec,
    format_path,
)
from .conversion import Conversion

__all__ = ["Context", "walk"]


class Context:
    """Where a node is, for a filter function that asks for it.

    ``parent`` is the node whose field holds this one (``field``), ``index``
    its position in that field's list (or key in its map, or ``None``).
    ``next`` and ``prev`` are its neighbours in that list. ``path`` is its
    position from the document, as in errors: ``blocks[3].content[1]``.

    ``conversion`` is the pandoc run the filter is part of (``format`` is its
    output format's name); ``libpandoc.read(text, ctx.conversion)`` parses a
    fragment as that run reads its input.
    """

    __slots__ = ("_frames", "container", "conversion", "doc", "field", "format", "index", "parent")

    def __init__(self, frames: tuple, doc: Any, conversion: Conversion) -> None:
        self._frames = frames
        self.doc, self.conversion, self.format = doc, conversion, conversion.format
        if frames:
            self.parent, self.field, self.container, self.index = frames[-1]
        else:
            self.parent = self.field = self.container = self.index = None

    @property
    def path(self) -> tuple:
        out: list = []
        for _, field, _, key in self._frames:
            if field is not None:
                out.append(field)
            if key is not None:
                out.extend(key if isinstance(key, tuple) else (key,))
        return tuple(out)

    @property
    def where(self) -> str:
        return format_path(self.path) or "the document"

    @property
    def ancestors(self) -> list[Node]:
        """The nodes above this one, the document first, the parent last."""
        seen: list[Node] = []
        for parent, *_ in self._frames:
            if not seen or seen[-1] is not parent:
                seen.append(parent)
        return seen

    def _sibling(self, step: int) -> Any:
        if not isinstance(self.container, list) or not isinstance(self.index, int):
            return None
        i = self.index + step
        return self.container[i] if 0 <= i < len(self.container) else None

    @property
    def next(self) -> Any:
        return self._sibling(1)

    @property
    def prev(self) -> Any:
        return self._sibling(-1)

    def __repr__(self) -> str:
        parent = type(self.parent).__name__ if self.parent is not None else None
        return f"<Context at {self.where}, parent {parent}>"


def _walk_fields(cls: type[Node]) -> list[tuple[str, _Spec]]:
    fields = cls.__dict__.get("_walk_fields_cache")
    if fields is None:
        fields = [(f, s) for f, s in cls._specs.items() if s.has_nodes]
        type.__setattr__(cls, "_walk_fields_cache", fields)
    return fields


Action = Callable[[Node, Context], Any]


class _Walker:
    def __init__(
        self,
        action: Action,
        top_down: bool,
        doc: Any,
        conversion: Conversion,
        wants: Callable[[type], bool],
    ) -> None:
        self.action, self.top_down = action, top_down
        self.doc, self.conversion, self.wants = doc, conversion, wants
        self.frames: list = []

    def call(self, node: Node) -> Any:
        return self.action(node, Context(tuple(self.frames), self.doc, self.conversion))

    # a node in a position that holds one node
    def one(self, node: Node, where: str) -> Node:
        if self.top_down:
            if self.wants(type(node)):
                node = self.single(self.call(node), node, where)
            self.children(node)
            return node
        self.children(node)
        if self.wants(type(node)):
            node = self.single(self.call(node), node, where)
        return node

    @staticmethod
    def single(result: Any, node: Node, where: str) -> Node:
        if result is None:
            return node
        if isinstance(result, Node):
            return result
        raise ASTTypeError(where, "one node (this position holds one)", _describe(result))

    # the nodes in a list: each may be replaced, deleted, or spliced
    def many(
        self, lst: list, spec: _ListSpec, parent: Node, field: str | None, outer: tuple
    ) -> None:
        frame = [parent, field, lst, None]
        self.frames.append(frame)
        try:
            i = 0
            while i < len(lst):
                frame[3] = outer + (i,) if outer else i
                node = lst[i]
                if not self.top_down:
                    self.children(node)
                if self.wants(type(node)):
                    result = self.call(node)
                    if result is not None:
                        if isinstance(result, Node):
                            result = [result]
                        elif isinstance(result, tuple):
                            result = list(result)
                        elif not isinstance(result, list):
                            raise ASTTypeError(
                                spec.label + f"[{i}]",
                                "a node, a list of nodes or None",
                                _describe(result),
                            )
                        lst[i : i + 1] = result  # checked by NodeList
                        if not self.top_down:
                            i += len(result)
                            continue
                        for _ in range(len(result)):
                            frame[3] = outer + (i,) if outer else i
                            self.children(lst[i])
                            i += 1
                        continue
                if self.top_down:
                    self.children(node)
                i += 1
        finally:
            self.frames.pop()

    def value(self, value: Any, spec: _Spec, parent: Node, field: str | None, key: tuple) -> Any:
        """Walk a field's value; returns it, or its replacement."""
        if isinstance(spec, _ClassSpec):
            self.frames.append([parent, field, None, key or None])
            try:
                return self.one(value, spec.label)
            finally:
                self.frames.pop()
        if isinstance(spec, _MaybeSpec):
            return None if value is None else self.value(value, spec.item, parent, field, key)
        if isinstance(spec, _ListSpec):
            if isinstance(spec.item, _ClassSpec):
                if type(value) is not NodeList:
                    value = spec.coerce(value)
                self.many(value, spec, parent, field, key)
            else:
                for i, x in enumerate(value):
                    new = self.value(x, spec.item, parent, field, key + (i,))
                    if new is not x:
                        list.__setitem__(value, i, new)
            return value
        if isinstance(spec, _MapSpec):
            for k in list(value):
                x = value[k]
                if isinstance(spec.value, _ClassSpec):
                    self.frames.append([parent, field, value, key + (k,)])
                    try:
                        if not self.top_down:
                            self.children(x)
                        result = self.call(x) if self.wants(type(x)) else None
                        if isinstance(result, list) and not result:
                            del value[k]
                            continue
                        x = self.single(result, x, f"{spec.label}[{k!r}]")
                        value[k] = x
                        if self.top_down:
                            self.children(x)
                    finally:
                        self.frames.pop()
                else:
                    new = self.value(x, spec.value, parent, field, key + (k,))
                    if new is not x:
                        dict.__setitem__(value, k, new)
            return value
        if isinstance(spec, _TupleSpec):
            items = list(value)
            changed = False
            for i, (x, s) in enumerate(zip(items, spec.items)):
                if s.has_nodes:
                    new = self.value(x, s, parent, field, key + (i,))
                    if new is not x:
                        items[i] = new
                        changed = True
            return spec.coerce(items) if changed else value
        return value

    def children(self, node: Node) -> None:
        for f, spec in _walk_fields(type(node)):
            old = getattr(node, f)
            new = self.value(old, spec, node, f, ())
            if new is not old:
                setattr(node, f, new)


def walk(
    node: Node,
    action: Action,
    *,
    top_down: bool = False,
    format: str | None = None,
    conversion: Conversion | None = None,
    doc: Any = None,
    wants: Callable[[type], bool] | None = None,
) -> Any:
    """Apply ``action(node, ctx)`` to ``node`` and every node in it.

    Bottom-up by default: a node's children before the node. ``action``
    returns ``None`` to keep the node (changed in place or not), a node to
    replace it, or, in a list, a list of nodes to splice in its place (``[]``
    deletes it). Top-down, children are those of the replacement.

    ``conversion`` (or just its output ``format``) is what ``ctx.conversion``
    tells the action.

    Returns ``node``, or what replaced it.
    """
    conv = conversion if conversion is not None else Conversion(format)
    w = _Walker(action, top_down, node if doc is None else doc, conv, wants or (lambda ty: True))
    return w.one(node, type(node).__name__)
