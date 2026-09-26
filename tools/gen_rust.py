#!/usr/bin/env python3
"""Generate rust/src/generated.rs from schema/pandoc-ast.json.

Rust has no run-time reflection, so unlike Python's the generated code here
is more than declarations: it is what a derive would write. Types:

- a sum type is an enum, adjacently tagged (``#[serde(tag = "t", content =
  "c")]``), which is pandoc-types' encoding: a constructor without fields is a
  unit variant (``Inline::Space``), one with one field holds it
  (``Inline::Str(String)``), one with more holds a struct of the same name
  with named fields (``Block::Header(Header)``), encoded as an array;
- a product is a struct: encoded as an array (``Attr``), as an object with
  pandoc-types' keys (``Citation``), or as the document (``Pandoc``);
- an enum-like type is an internally tagged enum: ``{"t": "InlineMath"}``;
- an alias is a type alias.

And ``VisitMut``: a method per type, whose default visits the children, to
override for a filter (as syn's ``visit_mut``).

    python3 tools/gen_rust.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "rust/src/generated.rs"

PRIM = {"string": "String", "int": "i64", "double": "f64", "bool": "bool"}
KEYWORDS = {
    "type",
    "match",
    "ref",
    "mod",
    "move",
    "fn",
    "impl",
    "use",
    "where",
    "self",
    "loop",
    "box",
    "yield",
    "async",
    "await",
    "dyn",
    "abstract",
    "final",
    "override",
}


def snake(name: str) -> str:
    out = ""
    for i, ch in enumerate(name):
        if ch.isupper() and i and not name[i - 1].isupper():
            out += "_"
        out += ch.lower()
    return out


def ident(name: str) -> str:
    return f"r#{name}" if name in KEYWORDS else name


class Gen:
    def __init__(self, schema: dict) -> None:
        self.schema = schema
        self.types = {t["name"]: t for t in schema["types"]}
        self.out: list[str] = []

    def resolve(self, ty: dict) -> dict:
        while "ref" in ty and self.types[ty["ref"]]["kind"] == "alias":
            ty = self.types[ty["ref"]]["type"]
        return ty

    def rust(self, ty: dict) -> str:
        if "prim" in ty:
            return PRIM[ty["prim"]]
        if "ref" in ty:
            return ty["ref"]
        if "list" in ty:
            return f"Vec<{self.rust(ty['list'])}>"
        if "maybe" in ty:
            return f"Option<{self.rust(ty['maybe'])}>"
        if "map" in ty:
            return f"BTreeMap<{self.rust(ty['map'][0])}, {self.rust(ty['map'][1])}>"
        if "tuple" in ty:
            return f"({', '.join(self.rust(t) for t in ty['tuple'])})"
        raise ValueError(ty)

    def default_expr(self, ty: dict, value) -> str:
        r = self.resolve(ty)
        if value is None:
            return "None"
        if "list" in r:
            return "Vec::new()"
        if "map" in r:
            return "BTreeMap::new()"
        if "ref" in r:
            t = self.types[r["ref"]]
            if t["kind"] == "enum":
                return f"{t['name']}::{value['t']}"
            if t["kind"] == "sum":
                return f"{t['name']}::{value['t']}"
            return f"{t['name']}::default()"
        if r.get("prim") == "string":
            return "String::new()" if value == "" else f"{json.dumps(value)}.to_string()"
        return json.dumps(value)

    def has_default(self, t: dict) -> bool:
        return all("default" in f for f in t["fields"])

    # -- declarations -------------------------------------------------------

    def generate(self) -> str:
        api = self.schema["pandoc-api-version"]
        o = self.out
        o.append(HEADER.format(api=".".join(map(str, api))))
        o.append(
            f"/// The pandoc-types API version these types are for.\n"
            f"pub const PANDOC_API_VERSION: [i64; {len(api)}] = {api!r};\n\n"
        )
        for t in self.schema["types"]:
            getattr(self, t["kind"])(t)
        self.visitor()
        return "".join(o)

    def alias(self, t: dict) -> None:
        name, target = t["name"], self.rust(t["type"])
        self.out.append(f"/// pandoc's `{name}`.\npub type {name} = {target};\n\n")

    def enum(self, t: dict) -> None:
        o = self.out
        o.append(f"/// pandoc's `{t['name']}`.\n")
        o.append("#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]\n")
        o.append('#[serde(tag = "t")]\n')
        o.append(f"pub enum {t['name']} {{\n")
        o.extend(f"    {v},\n" for v in t["values"])
        o.append("}\n\n")

    def sum(self, t: dict) -> None:
        o = self.out
        structs = []
        o.append(f"/// pandoc's `{t['name']}`.\n")
        o.append("#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]\n")
        o.append('#[serde(tag = "t", content = "c")]\n')
        o.append(f"pub enum {t['name']} {{\n")
        for c in t["constructors"]:
            n = len(c["fields"])
            if n == 0:
                o.append(f"    {c['name']},\n")
            elif n == 1:
                o.append(f"    {c['name']}({self.rust(c['fields'][0]['type'])}),\n")
            else:
                o.append(f"    {c['name']}({c['name']}),\n")
                structs.append(c)
        o.append("}\n\n")
        for c in structs:
            if c["name"] in self.types:
                raise SystemExit(f"constructor {c['name']} clashes with a type name")
            self.struct(c, "array", f"pandoc's `{c['name']}`, a `{t['name']}`.")

    def product(self, t: dict) -> None:
        self.struct(t, t["encoding"], f"pandoc's `{t['name']}`.")

    def struct(self, t: dict, encoding: str, doc: str) -> None:
        o = self.out
        name = t["name"]
        fields = t["fields"]
        derive_serde = encoding in ("object", "root")
        derives = ["Debug", "Clone", "PartialEq"]
        if derive_serde:
            derives += ["Serialize", "Deserialize"]
        o.append(f"/// {doc}\n#[derive({', '.join(derives)})]\n")
        o.append(f"pub struct {name} {{\n")
        if encoding == "root":
            o.append(
                '    #[serde(rename = "pandoc-api-version")]\n    pub api_version: Vec<i64>,\n'
            )
        for f in fields:
            if "key" in f and f["key"] != f["name"]:
                o.append(f'    #[serde(rename = "{f["key"]}")]\n')
            o.append(f"    pub {ident(f['name'])}: {self.rust(f['type'])},\n")
        o.append("}\n\n")
        if self.has_default(t):
            o.append(
                f"impl Default for {name} {{\n    fn default() -> Self {{\n        {name} {{\n"
            )
            if encoding == "root":
                o.append("            api_version: PANDOC_API_VERSION.to_vec(),\n")
            for f in fields:
                value = self.default_expr(f["type"], f["default"])
                o.append(f"            {ident(f['name'])}: {value},\n")
            o.append("        }\n    }\n}\n\n")
        if encoding == "array":
            refs = ", ".join(f"&self.{ident(f['name'])}" for f in fields)
            types = ", ".join(self.rust(f["type"]) for f in fields)
            names = ", ".join(ident(f["name"]) for f in fields)
            o.append(
                f"impl Serialize for {name} {{\n"
                f"    fn serialize<S: Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {{\n"
                f"        ({refs}).serialize(s)\n    }}\n}}\n\n"
            )
            o.append(
                f"impl<'de> Deserialize<'de> for {name} {{\n"
                f"    fn deserialize<D: Deserializer<'de>>(d: D)"
                f" -> Result<Self, D::Error> {{\n"
                f"        let ({names}) = <({types})>::deserialize(d)?;\n"
                f"        Ok({name} {{ {names} }})\n    }}\n}}\n\n"
            )

    # -- the visitor ----------------------------------------------------------

    def node_types(self) -> list[dict]:
        return [t for t in self.schema["types"] if t["kind"] in ("sum", "product")]

    def holds_nodes(self, ty: dict) -> bool:
        ty = self.resolve(ty)
        if "prim" in ty:
            return False
        if "ref" in ty:
            return self.types[ty["ref"]]["kind"] in ("sum", "product")
        if "list" in ty:
            return self.holds_nodes(ty["list"])
        if "maybe" in ty:
            return self.holds_nodes(ty["maybe"])
        if "map" in ty:
            return self.holds_nodes(ty["map"][1])
        if "tuple" in ty:
            return any(self.holds_nodes(t) for t in ty["tuple"])
        return False

    def list_types(self) -> list[str]:
        """Sum types that appear in lists: they get a visit_<type>s method."""
        seen: list[str] = []

        def scan(ty: dict) -> None:
            ty = self.resolve(ty)
            if "list" in ty:
                inner = self.resolve(ty["list"])
                if (
                    "ref" in inner
                    and self.types[inner["ref"]]["kind"] == "sum"
                    and inner["ref"] not in seen
                ):
                    seen.append(inner["ref"])
                scan(ty["list"])
            for k in ("maybe",):
                if k in ty:
                    scan(ty[k])
            if "map" in ty:
                scan(ty["map"][1])
            if "tuple" in ty:
                for x in ty["tuple"]:
                    scan(x)

        for t in self.node_types():
            for c in t["constructors"] if t["kind"] == "sum" else [t]:
                for f in c["fields"]:
                    scan(f["type"])
        return seen

    def visit_expr(self, ty: dict, x: str, depth: int = 0) -> str | None:
        """A statement visiting ``x`` (a ``&mut`` place) of type ``ty``."""
        if not self.holds_nodes(ty):
            return None
        ty = self.resolve(ty)
        v = f"x{depth}"
        if "ref" in ty:
            return f"v.visit_{snake(ty['ref'])}({x});"
        if "list" in ty:
            inner = self.resolve(ty["list"])
            if "ref" in inner and inner["ref"] in self.lists:
                return f"v.visit_{snake(inner['ref'])}s({x});"
            body = self.visit_expr(ty["list"], v, depth + 1)
            return f"for {v} in ({x}).iter_mut() {{ {body} }}"
        if "maybe" in ty:
            body = self.visit_expr(ty["maybe"], v, depth + 1)
            return f"if let Some({v}) = ({x}).as_mut() {{ {body} }}"
        if "map" in ty:
            body = self.visit_expr(ty["map"][1], v, depth + 1)
            return f"for {v} in ({x}).values_mut() {{ {body} }}"
        if "tuple" in ty:
            parts = [
                self.visit_expr(t, f"&mut ({x}).{i}", depth + 1) for i, t in enumerate(ty["tuple"])
            ]
            return " ".join(p for p in parts if p)
        return None

    def visitor(self) -> None:
        o = self.out
        self.lists = self.list_types()
        o.append(VISITOR_DOC)
        o.append("pub trait VisitMut {\n")
        for t in self.node_types():
            n = snake(t["name"])
            o.append(
                f"    fn visit_{n}(&mut self, x: &mut {t['name']}) {{\n"
                f"        walk_{n}(self, x)\n    }}\n"
            )
        for name in self.lists:
            n = snake(name)
            o.append(
                f"    /// The {name}s of one list, e.g. to splice or remove some.\n"
                f"    fn visit_{n}s(&mut self, xs: &mut Vec<{name}>) {{\n"
                f"        walk_{n}s(self, xs)\n    }}\n"
            )
        o.append("}\n\n")
        for name in self.lists:
            n = snake(name)
            o.append(
                f"/// Visits each {name} of a list.\n"
                f"pub fn walk_{n}s<V: VisitMut + ?Sized>(v: &mut V, xs: &mut Vec<{name}>) {{\n"
                f"    for x in xs.iter_mut() {{\n        v.visit_{n}(x);\n    }}\n}}\n\n"
            )
        for t in self.node_types():
            n = snake(t["name"])
            o.append(
                f"/// Visits the children of a {t['name']}.\n"
                f"#[allow(unused_variables)]\n"
                f"pub fn walk_{n}<V: VisitMut + ?Sized>(v: &mut V, x: &mut {t['name']}) {{\n"
            )
            if t["kind"] == "product":
                for f in t["fields"]:
                    s = self.visit_expr(f["type"], f"&mut x.{ident(f['name'])}")
                    if s:
                        o.append(f"    {s}\n")
            else:
                arms = []
                for c in t["constructors"]:
                    fs = c["fields"]
                    if len(fs) == 1:
                        s = self.visit_expr(fs[0]["type"], "y")
                        if s:
                            arms.append(f"        {t['name']}::{c['name']}(y) => {{ {s} }}\n")
                    elif len(fs) > 1:
                        stmts = [
                            self.visit_expr(f["type"], f"&mut y.{ident(f['name'])}") for f in fs
                        ]
                        stmts = [s for s in stmts if s]
                        if stmts:
                            body = " ".join(stmts)
                            arms.append(f"        {t['name']}::{c['name']}(y) => {{ {body} }}\n")
                if arms:
                    o.append("    match x {\n")
                    o.extend(arms)
                    o.append("        _ => {}\n    }\n")
            o.append("}\n\n")


HEADER = """\
// GENERATED by tools/gen_rust.py from schema/pandoc-ast.json
// (pandoc-api-version {api}). Do not edit; regenerate instead.

//! pandoc's AST types, their JSON encoding, and `VisitMut`.

#![allow(clippy::all)]

use serde::{{Deserialize, Deserializer, Serialize, Serializer}};
use std::collections::BTreeMap;

"""

VISITOR_DOC = """\
/// A visitor over a document, changing it in place.
///
/// Each method's default visits the node's children (`walk_*`). Override
/// the ones for the nodes to change; call the `walk_*` function in an
/// override to visit the children too (before changing the node: bottom-up;
/// after: top-down).
///
/// ```
/// use libpandoc_ast::{Inline, VisitMut, walk_inline};
///
/// struct Upper;
/// impl VisitMut for Upper {
///     fn visit_inline(&mut self, x: &mut Inline) {
///         walk_inline(self, x);
///         if let Inline::Str(s) = x {
///             *s = s.to_uppercase();
///         }
///     }
/// }
/// ```
"""


def main() -> None:
    schema = json.loads((ROOT / "schema/pandoc-ast.json").read_text())
    OUT.write_text(Gen(schema).generate())


if __name__ == "__main__":
    main()
