#!/usr/bin/env python3
"""Generate python/src/pandom/_types.py from schema/pandoc-ast.json.

The output only declares: one class per constructor (a subclass of its sum
type's class) or product, fields as annotations, the JSON encoding as class
attributes, and a constructor. What classes do is in ``_core.py``, which
reads these declarations.

    python3 tools/gen_python.py
"""

from __future__ import annotations

import json
import keyword
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "python/src/pandom/_types.py"

PRIM = {"string": "str", "int": "int", "double": "float", "bool": "bool"}


def py_literal(value) -> str:
    """JSON as a Python literal."""
    return repr(json.loads(json.dumps(value)))


class Gen:
    def __init__(self, schema: dict) -> None:
        self.schema = schema
        self.types = {t["name"]: t for t in schema["types"]}
        # a sum type's class, where a constructor has the type's name
        self.cls_name = {}
        for t in schema["types"]:
            name = t["name"]
            clash = t["kind"] == "sum" and any(c["name"] == name for c in t["constructors"])
            self.cls_name[name] = name + "Base" if clash else name

    # -- types -------------------------------------------------------------

    def field_type(self, ty: dict) -> str:
        """The type of a field's value."""
        if "prim" in ty:
            return PRIM[ty["prim"]]
        if "ref" in ty:
            return self.cls_name[ty["ref"]]
        if "list" in ty:
            return f"list[{self.field_type(ty['list'])}]"
        if "maybe" in ty:
            return f"{self.field_type(ty['maybe'])} | None"
        if "map" in ty:
            return f"dict[{self.field_type(ty['map'][0])}, {self.field_type(ty['map'][1])}]"
        if "tuple" in ty:
            return f"tuple[{', '.join(self.field_type(t) for t in ty['tuple'])}]"
        raise ValueError(ty)

    def resolve(self, ty: dict) -> dict:
        while "ref" in ty and self.types[ty["ref"]]["kind"] == "alias":
            ty = self.types[ty["ref"]]["type"]
        return ty

    def param_type(self, ty: dict) -> str:
        """What a constructor accepts for a field: lists as any iterable."""
        r = self.resolve(ty)
        if "list" in r:
            inner = r["list"]
            if (
                "tuple" in inner
                and len(inner["tuple"]) == 2
                and all(t.get("prim") == "string" for t in inner["tuple"])
            ):
                return "Iterable[tuple[str, str]] | Mapping[str, str]"
            return f"Iterable[{self.param_type(inner)}]"
        if "map" in r:
            return f"Mapping[str, {self.param_type(r['map'][1])}]"
        if "maybe" in r:
            return f"{self.param_type(r['maybe'])} | None"
        if "tuple" in r:
            return f"tuple[{', '.join(self.param_type(t) for t in r['tuple'])}]"
        return self.field_type(ty)

    def default_literal(self, ty: dict, value) -> str:
        r = self.resolve(ty)
        if value is None or "map" in r:
            return "None"
        if "list" in r:
            if value:
                sys.exit(f"non-empty default list {value} isn't supported")
            return "()"
        if "ref" in r:
            t = self.types[r["ref"]]
            if t["kind"] == "enum":
                return f"{t['name']}.{value['t']}"
            return "None"  # a product: its own default
        return repr(value)

    # -- declarations --------------------------------------------------------

    def generate(self) -> str:
        api = self.schema["pandoc-api-version"]
        out = [HEADER.format(api=".".join(map(str, api)))]
        out.append(f"PANDOC_API_VERSION = {tuple(api)!r}\n\n\n")
        names: list[str] = []
        types = self.schema["types"]
        for t in types:
            if t["kind"] == "enum":
                out.append(self.enum(t))
                names.append(t["name"])
        for t in types:
            if t["kind"] == "sum":
                base = self.cls_name[t["name"]]
                out.append(
                    f"class {base}(Node):\n"
                    f'    """Any of pandoc\'s ``{t["name"]}`` constructors."""\n\n'
                    f"    __slots__ = ()\n"
                    f'    _kind = "sum"\n\n\n'
                )
                names.append(base)
                for c in t["constructors"]:
                    out.append(self.cls(c, base, None, t["name"]))
                    names.append(c["name"])
            elif t["kind"] == "product":
                out.append(self.cls(t, "Node", t["encoding"], None))
                names.append(t["name"])
        out.append("# pandoc-types' newtypes and type synonyms\n")
        for t in types:
            if t["kind"] == "alias":
                out.append(f"{t['name']}: TypeAlias = {self.field_type(t['type'])}\n")
                names.append(t["name"])
        out.append("\n__all__ = [\n")
        out.extend(f"    {n!r},\n" for n in ["PANDOC_API_VERSION", *names])
        out.append("]\n\n")
        out.append("finalize(globals(), PANDOC_API_VERSION)\n")
        return "".join(out)

    @staticmethod
    def enum(t: dict) -> str:
        lines = [f"class {t['name']}(Enum):", f'    """pandoc\'s ``{t["name"]}``."""', ""]
        lines += [f"    {v} = {v!r}" for v in t["values"]]
        return "\n".join(lines) + "\n\n\n"

    @staticmethod
    def pyname(n: str) -> str:
        return n + "_" if keyword.iskeyword(n) else n

    def cls(self, c: dict, base: str, product_encoding: str | None, sum_name: str | None) -> str:
        name = c["name"]
        fields = c["fields"]
        fnames = [self.pyname(f["name"]) for f in fields]
        doc = f"pandoc's ``{name}``, a {sum_name}." if sum_name else f"pandoc's ``{name}``."
        lines = [f"class {name}({base}):", f'    """{doc}"""', ""]
        slots = "(" + "".join(f"{n!r}, " for n in fnames).rstrip(" ") + ")"
        lines.append(f"    __slots__ = {slots}")
        lines.append("    __match_args__ = __slots__")
        if product_encoding:
            lines.append('    _kind = "product"')
            lines.append(f"    _encoding = {product_encoding!r}")
        else:
            lines.append(f"    _encoding = {c['encoding']!r}")
        keys = {self.pyname(f["name"]): f["key"] for f in fields if "key" in f}
        if keys:
            lines.append(f"    _keys = {keys!r}")
        if c.get("variadic"):
            lines.append(f"    _variadic = {self.pyname(c['variadic'])!r}")
        flatten = tuple(self.pyname(f["name"]) for f in fields if f.get("flatten"))
        if flatten:
            lines.append(f"    _flatten = {flatten!r}")
        defaults = {self.pyname(f["name"]): f["default"] for f in fields if "default" in f}
        if defaults:
            lines.append(f"    _defaults = {py_literal(defaults)}")
        init = self.init(c, fnames) if fields else []
        if self.positional and fields:
            lines.append(f"    _positional = {tuple(self.positional)!r}")
        lines.append("")
        for n, f in zip(fnames, fields):
            lines.append(f"    {n}: {self.field_type(f['type'])}")
        if fields:
            lines.append("")
            lines += init
        return "\n".join(lines) + "\n\n\n"

    def init(self, c: dict, fnames: list[str]) -> list[str]:
        """``__init__`` and ``_positional``, in pandoc-types' field order.

        Fields are positional, then the variadic field (if any) as *args,
        then keyword-only: a field with a default before *args, and any field
        after it, and a required field after one with a default. Flattened
        products are keyword-only, whole or by their fields' names.
        E.g. ``Header(level, *content, attr=, identifier=, ...)``.
        """
        fields = c["fields"]
        variadic = c.get("variadic")
        self.positional: list[str] = []
        params: list[str] = []
        star: str | None = None
        kwonly: list[str] = []
        values: list[str] = []
        flats: list[str] = []
        positional = True
        after_default = False
        for n, f in zip(fnames, fields):
            ptype = self.param_type(f["type"])
            values.append(f"{n!r}: {n}")
            if f["name"] == variadic:
                star = f"*{n}: {self.param_type(self.resolve(f['type'])['list'])}"
                positional = False
                continue
            if f.get("flatten"):
                prod = self.types[f["type"]["ref"]]
                parts = []
                kwonly.append(f"{n}: {ptype} | None = None")
                for g in prod["fields"]:
                    gn = self.pyname(g["name"])
                    gtype = self.param_type(g["type"])
                    if "default" in g:
                        kwonly.append(
                            f"{gn}: {gtype} = {self.default_literal(g['type'], g['default'])}"
                        )
                    else:
                        kwonly.append(f"{gn}: {gtype} | None = None")
                    parts.append(f"{gn!r}: {gn}")
                flats.append(
                    f"{n} = _flat({prod['name']}, {c['name']!r}, {n!r}, {n}, "
                    f"{{{', '.join(parts)}}})"
                )
                continue
            has_default = "default" in f
            if has_default:
                lit = self.default_literal(f["type"], f["default"])
                if lit == "None" and not ptype.endswith("| None"):
                    ptype += " | None"
                decl = f"{n}: {ptype} = {lit}"
            else:
                decl = f"{n}: {ptype}"
            # before *args, only required fields; and Python allows no
            # required parameter after one with a default
            if has_default and variadic or not has_default and after_default:
                positional = False
            if positional:
                params.append(decl)
                self.positional.append(n)
                after_default = after_default or has_default
            else:
                kwonly.append(decl)
        out = []
        sig = ["self", *params]
        if star:
            sig.append(star)
        elif kwonly:
            sig.append("*")
        sig += kwonly
        head = f"    def __init__({', '.join(sig)}) -> None:"
        if len(head) <= 88:
            out.append(head)
        else:
            out.append("    def __init__(")
            out += [f"        {s}," for s in sig]
            out.append("    ) -> None:")
        out += [f"        {line}" for line in flats]
        body = f"        _init(self, {{{', '.join(values)}}})"
        if len(body) <= 88:
            out.append(body)
        else:
            out.append("        _init(self, {")
            out += [f"            {v}," for v in values]
            out.append("        })")
        return out


HEADER = '''\
# GENERATED by tools/gen_python.py from schema/pandoc-ast.json
# (pandoc-api-version {api}). Do not edit; regenerate instead.
"""pandoc's AST types: declarations only.

One class per constructor, a subclass of its type's class (``Header`` of
``Block``), and one per product type (``Attr``, ``Citation``, ...). Fields are
in pandoc-types' order. How the classes behave is in ``_core``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import TypeAlias

from ._core import Enum, Node, finalize
from ._core import flat as _flat
from ._core import init as _init

'''


def main() -> None:
    schema = json.loads((ROOT / "schema/pandoc-ast.json").read_text())
    OUT.write_text(Gen(schema).generate())


if __name__ == "__main__":
    main()
