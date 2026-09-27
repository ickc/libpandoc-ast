#!/usr/bin/env python3
"""Generate ts/src/generated.ts from schema/pandoc-ast.json.

Declarations only, as for Python: the types (for the type checker), the
schema itself (``SCHEMA``, which the generic runtime in ``core.ts``
interprets), and a constructor function per constructor and product.

Nodes are plain objects with named fields, discriminated by ``t``:
``{ t: "Header", level: 1, attr: {...}, content: [...] }``. Products have no
``t`` (``Attr``: ``{ identifier, classes, attributes }``); enum-like types are
string unions (``"InlineMath"``). Field names are the schema's, in
camelCase.

Constructors take the required fields, then the variadic field (as an
array), positionally, and the rest in an options object, flattened products
by their fields' names: ``Header(1, [Str("Hi")], { identifier: "hi" })``.

    python3 tools/gen_ts.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "ts/src/generated.ts"

PRIM = {"string": "string", "int": "number", "double": "number", "bool": "boolean"}


def camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(p.title() for p in rest)


class Gen:
    def __init__(self, schema: dict) -> None:
        self.schema = schema
        self.types = {t["name"]: t for t in schema["types"]}
        self.ts_name = {}
        for t in schema["types"]:
            name = t["name"]
            clash = t["kind"] == "sum" and any(c["name"] == name for c in t["constructors"])
            self.ts_name[name] = name + "Base" if clash else name

    def resolve(self, ty: dict) -> dict:
        while "ref" in ty and self.types[ty["ref"]]["kind"] == "alias":
            ty = self.types[ty["ref"]]["type"]
        return ty

    def ts(self, ty: dict) -> str:
        if "prim" in ty:
            return PRIM[ty["prim"]]
        if "ref" in ty:
            return self.ts_name[ty["ref"]]
        if "list" in ty:
            inner = self.ts(ty["list"])
            return f"({inner})[]" if "|" in inner else f"{inner}[]"
        if "maybe" in ty:
            return f"{self.ts(ty['maybe'])} | null"
        if "map" in ty:
            return f"Record<string, {self.ts(ty['map'][1])}>"
        if "tuple" in ty:
            return f"[{', '.join(self.ts(t) for t in ty['tuple'])}]"
        raise ValueError(ty)

    def param(self, ty: dict) -> str:
        """What a constructor accepts: attributes also as a record, and
        strings where inlines or blocks go, as pandoc's Lua converts them
        (the types Inlines and Blocks)."""
        r = self.resolve(ty)
        if (
            "list" in r
            and "tuple" in r["list"]
            and all(t.get("prim") == "string" for t in r["list"]["tuple"])
        ):
            return f"{self.ts(ty)} | Record<string, string>"
        if "list" in r:
            item = self.resolve(r["list"])
            if item.get("ref") in ("Inline", "Block"):
                return f"{item['ref']}s"
            if "list" in item or "tuple" in item:
                inner = self.param(r["list"])
                return f"({inner})[]" if "|" in inner else f"{inner}[]"
        if "tuple" in r:
            return f"[{', '.join(self.param(t) for t in r['tuple'])}]"
        return self.ts(ty)

    def camel_schema(self) -> dict:
        """The schema with camelCase field names (JSON keys unchanged)."""
        out = json.loads(json.dumps(self.schema))
        for t in out["types"]:
            for c in t.get("constructors", []) + ([t] if t["kind"] == "product" else []):
                for f in c.get("fields", []):
                    f["key"] = f.get("key", f["name"])
                    f["name"] = camel(f["name"])
                if "variadic" in c:
                    c["variadic"] = camel(c["variadic"])
        return out

    # -- declarations ---------------------------------------------------------

    def generate(self) -> str:
        api = self.schema["pandoc-api-version"]
        out = [HEADER.format(api=".".join(map(str, api)))]
        out.append(f"export const PANDOC_API_VERSION = {json.dumps(api)} as const;\n\n")
        constructors: list[tuple[str, str]] = []  # (name, ts type)
        for t in self.schema["types"]:
            kind, name = t["kind"], t["name"]
            if kind == "alias":
                out.append(f"export type {name} = {self.ts(t['type'])};\n\n")
            elif kind == "enum":
                values = " | ".join(json.dumps(v) for v in t["values"])
                out.append(f"export type {name} = {values};\n\n")
            elif kind == "sum":
                cons = [c["name"] for c in t["constructors"]]
                union = "".join(f"\n  | {c}" for c in cons)
                out.append(f"export type {self.ts_name[name]} ={union};\n\n")
                for c in t["constructors"]:
                    out.append(self.interface(c, tagged=True))
                    constructors.append((c["name"], c["name"]))
            else:
                out.append(self.interface(t, tagged=False))
                constructors.append((name, name))
        out.append(
            "/** Inlines as constructors take them: a string is its words and spaces,\n"
            " * and a string in the list a Str, as in pandoc's Lua. */\n"
            "export type Inlines = (Inline | string)[] | string;\n\n"
            "/** Blocks as constructors take them: a string is Plain text, as in\n"
            " * pandoc's Lua. */\n"
            "export type Blocks = (Block | string)[] | string;\n\n"
        )
        out.append("/** Every constructor and product, by name. */\n")
        out.append("export interface Nodes {\n")
        out.extend(f"  {n}: {ty};\n" for n, ty in constructors)
        out.append("}\n\n")
        sums = [t["name"] for t in self.schema["types"] if t["kind"] == "sum"]
        out.append("/** Each sum type, by name. */\n")
        out.append("export interface Sums {\n")
        out.extend(f"  {n}: {self.ts_name[n]};\n" for n in sums)
        out.append("}\n\n")
        schema = json.dumps(self.camel_schema(), separators=(",", ":"))
        out.append("/** The schema the runtime reads: schema/pandoc-ast.json, camelCase. */\n")
        out.append(f"export const SCHEMA: Schema = {schema};\n\n")
        for t in self.schema["types"]:
            if t["kind"] == "sum":
                for c in t["constructors"]:
                    out.append(self.constructor(c, product=False))
            elif t["kind"] == "product":
                out.append(self.constructor(t, product=True))
        return "".join(out)

    def interface(self, c: dict, tagged: bool) -> str:
        lines = [f"export interface {c['name']} {{"]
        if tagged:
            lines.append(f'  t: "{c["name"]}";')
        for f in c["fields"]:
            lines.append(f"  {camel(f['name'])}: {self.ts(f['type'])};")
        return "\n".join(lines) + "\n}\n\n"

    def constructor(self, c: dict, product: bool) -> str:
        name, fields = c["name"], c["fields"]
        variadic = c.get("variadic")
        array_product = product and c.get("encoding") == "array"
        positional: list[dict] = []
        options: list[dict] = []
        for f in fields:
            if f.get("flatten"):
                options.append(f)
            elif "default" not in f and f["name"] != variadic:
                positional.append(f)
        for f in fields:
            if f in positional or f.get("flatten"):
                continue
            if f["name"] == variadic or (array_product and not variadic) or len(fields) == 1:
                positional.append(f)
            else:
                options.append(f)
        # keep pandoc's order among the positional fields
        positional.sort(key=fields.index)
        params = []
        for f in positional:
            opt = "?" if "default" in f else ""
            params.append(f"{camel(f['name'])}{opt}: {self.param(f['type'])}")
        # all optional for the type checker: a flattened product's required
        # field (a link's url) may come whole instead (target); make() checks
        opt_fields = []
        for f in options:
            opt_fields.append(f"{camel(f['name'])}?: {self.param(f['type'])}")
            if f.get("flatten"):
                for g in self.types[f["type"]["ref"]]["fields"]:
                    opt_fields.append(f"{camel(g['name'])}?: {self.param(g['type'])}")
        if opt_fields:
            params.append(f"opts: {{ {'; '.join(opt_fields)} }} = {{}}")
        values = ", ".join(camel(f["name"]) for f in positional)
        opts_arg = "opts" if opt_fields else "{}"
        doc = f"/** pandoc's `{name}`. */\n"
        return (
            f"{doc}export function {name}({', '.join(params)}): {name} {{\n"
            f'  return make<{name}>("{name}", {{ {values} }}, {opts_arg});\n}}\n\n'
        )


HEADER = """\
// GENERATED by tools/gen_ts.py from schema/pandoc-ast.json
// (pandoc-api-version {api}). Do not edit; regenerate instead.

import {{ make }} from "./core.ts";
import type {{ Schema }} from "./core.ts";

"""


def main() -> None:
    schema = json.loads((ROOT / "schema/pandoc-ast.json").read_text())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(Gen(schema).generate())


if __name__ == "__main__":
    main()
