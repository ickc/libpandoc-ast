#!/usr/bin/env python3
"""Derive the language-neutral inputs of every binding from pandoc-types.

Reads what the Haskell tool wrote:

- ``schema/reified.json``: pandoc-types' declarations, as declared;
- ``corpus/arbitrary.jsonl``: random documents encoded by pandoc-types.

Writes:

- ``schema/pandoc-ast.json``: the schema every generator reads. It adds what
  the declarations don't say but every binding needs, decided once here so
  that bindings agree: field names, how each type is encoded in JSON,
  defaults, and which fields constructors take as varargs or flatten.
- ``corpus/invalid.jsonl``: documents that must be rejected, each with the
  path of the offending value.

It fails, rather than guesses, when pandoc-types changes in a way the rules
below don't cover, and when the corpus misses a constructor.

The JSON encoding, which pandoc-types defines with aeson:

- a sum type: ``{"t": Con}`` with no fields, ``{"t": Con, "c": x}`` with one,
  ``{"t": Con, "c": [x, y, ...]}`` with more; ``"encoding"`` is ``none``,
  ``value`` or ``array``. A sum whose constructors are all nullary is an
  ``enum``, still ``{"t": Con}``;
- a product (one constructor): an array of its fields, or an object keyed by
  the Haskell field names for a record (``"key"``), or for ``Pandoc`` itself
  ``{"pandoc-api-version": [...], "meta": ..., "blocks": ...}``;
- a newtype, or an alias of a non-tuple type: the underlying type (``alias``);
- a tuple alias listed in ALIAS_FIELDS: a product encoded as an array.

    python3 tools/derive.py
"""

from __future__ import annotations

import copy
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Constructor -> field names, where the field types don't determine them.
# Names follow pandoc's Lua API where it has one.
FIELD_NAMES: dict[str, list[str]] = {
    "Pandoc": ["meta", "blocks"],
    "Header": ["level", "attr", "content"],
    "TableBody": ["attr", "row_head_columns", "head", "body"],
    "ColWidth": ["width"],
    "MetaBool": ["value"],
    "MetaString": ["text"],
    "Caption": ["short", "content"],
    # as in pandoc's Lua API
    "Table": ["attr", "caption", "col_specs", "head", "bodies", "foot"],
}

# Tuple aliases that become products with these field names.
ALIAS_FIELDS: dict[str, list[str]] = {
    "Attr": ["identifier", "classes", "attributes"],
    "Target": ["url", "title"],
    "ListAttributes": ["start", "style", "delimiter"],
    "ColSpec": ["alignment", "width"],
}

# Defaults, as pandoc JSON, beyond the generic ones (empty list, empty map,
# null for Maybe, and a product whose fields all have defaults). The same
# as pandoc's Lua constructors'.
DEFAULTS: dict[str, object] = {
    "Attr.identifier": "",
    "Target.title": "",
    "ListAttributes.start": 1,
    "ListAttributes.style": {"t": "DefaultStyle"},
    "ListAttributes.delimiter": {"t": "DefaultDelim"},
    "ColSpec.alignment": {"t": "AlignDefault"},
    "ColSpec.width": {"t": "ColWidthDefault"},
    "Cell.alignment": {"t": "AlignDefault"},
    "Cell.row_span": 1,
    "Cell.col_span": 1,
    "TableBody.row_head_columns": 0,
    "Citation.mode": {"t": "NormalCitation"},
    "Citation.note_num": 0,
    "Citation.hash": 0,
}

CONTENT_TYPES = {"Inline", "Block", "MetaValue"}


def fail(msg: str) -> None:
    sys.exit(f"derive.py: {msg}")


def snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def plural(name: str) -> str:
    return name[:-1] + "ies" if name.endswith("y") else name + "s"


def derive_name(con: str, ty: dict) -> str:
    if "maybe" in ty:
        return derive_name(con, ty["maybe"])
    if "ref" in ty:
        return snake(ty["ref"])
    if "map" in ty:
        return "content"
    if "list" in ty:
        inner = ty["list"]
        while "list" in inner:
            inner = inner["list"]
        if "tuple" in inner or inner.get("ref") in CONTENT_TYPES:
            return "content"
        if "ref" in inner:
            return plural(snake(inner["ref"]))
    if ty.get("prim") == "string":
        return "text"
    fail(f"can't name a field of type {ty} in {con}; add it to FIELD_NAMES")
    raise AssertionError


def field_names(con: dict) -> list[str]:
    fields = con["fields"]
    if fields and all(f["name"] for f in fields):
        prefix = con["name"][0].lower() + con["name"][1:]
        names = [snake(f["name"].removeprefix(prefix)) for f in fields]
    elif con["name"] in FIELD_NAMES:
        names = FIELD_NAMES[con["name"]]
        if len(names) != len(fields):
            fail(
                f"FIELD_NAMES[{con['name']!r}] has {len(names)} names, "
                f"the constructor {len(fields)} fields"
            )
    else:
        names = [derive_name(con["name"], f["type"]) for f in fields]
    if len(set(names)) != len(names):
        fail(f"{con['name']} has ambiguous field names {names}; add it to FIELD_NAMES")
    return names


class Deriver:
    def __init__(self, reified: dict) -> None:
        self.reified = reified
        self.decls = {t["name"]: t for t in reified["types"]}
        self.types: dict[str, dict] = {}

    def run(self) -> dict:
        for t in self.reified["types"]:
            self.types[t["name"]] = self.convert(t)
        for t in self.types.values():
            for con in self.constructors(t):
                self.annotate(t, con)
        unused = {k.split(".")[0] for k in DEFAULTS} - set(self.types)
        unused |= (set(FIELD_NAMES) | set(ALIAS_FIELDS)) - self.all_names()
        if unused:
            fail(f"tables name types or constructors pandoc-types no longer has: {unused}")
        return {
            "pandoc-api-version": self.reified["pandoc-api-version"],
            "root": self.reified["root"],
            "types": list(self.types.values()),
        }

    def all_names(self) -> set[str]:
        names = set(self.types)
        for t in self.types.values():
            names |= {c["name"] for c in self.constructors(t)}
        return names

    @staticmethod
    def constructors(t: dict) -> list[dict]:
        if t["kind"] == "sum":
            return t["constructors"]
        if t["kind"] == "product":
            return [t]
        return []

    def convert(self, t: dict) -> dict:
        name, kind = t["name"], t["kind"]
        if kind == "alias":
            ty = t["type"]
            if "tuple" in ty:
                if name not in ALIAS_FIELDS:
                    fail(f"tuple alias {name}: add its field names to ALIAS_FIELDS")
                names = ALIAS_FIELDS[name]
                if len(names) != len(ty["tuple"]):
                    fail(f"ALIAS_FIELDS[{name!r}] doesn't match {ty}")
                return {
                    "name": name,
                    "kind": "product",
                    "encoding": "array",
                    "fields": [{"name": n, "type": ft} for n, ft in zip(names, ty["tuple"])],
                }
            return {"name": name, "kind": "alias", "type": ty}
        cons = t["constructors"]
        if kind == "newtype":
            return {"name": name, "kind": "alias", "type": cons[0]["fields"][0]["type"]}
        if len(cons) > 1:
            if all(not c["fields"] for c in cons):
                return {"name": name, "kind": "enum", "values": [c["name"] for c in cons]}
            out = []
            for c in cons:
                if any(f["name"] for f in c["fields"]):
                    fail(
                        f"record constructor {c['name']} in sum {name}: aeson "
                        "encodes it as an object; add support for that"
                    )
                n = len(c["fields"])
                out.append(
                    {
                        "name": c["name"],
                        "encoding": "none" if n == 0 else "value" if n == 1 else "array",
                        "fields": self.fields(c),
                    }
                )
            return {"name": name, "kind": "sum", "constructors": out}
        con = cons[0]
        if con["name"] != name:
            fail(
                f"product {name} has constructor {con['name']}; bindings name "
                "products after their type"
            )
        if name == self.reified["root"]:
            encoding = "root"
        elif con["fields"] and all(f["name"] for f in con["fields"]):
            encoding = "object"
        elif len(con["fields"]) == 1:
            encoding = "value"
        else:
            encoding = "array"
        fields = self.fields(con)
        if encoding == "root":
            for f in fields:
                f["key"] = f["name"]
        return {"name": name, "kind": "product", "encoding": encoding, "fields": fields}

    @staticmethod
    def fields(con: dict) -> list[dict]:
        out = []
        for n, f in zip(field_names(con), con["fields"]):
            d = {"name": n, "type": f["type"]}
            if f["name"]:
                d["key"] = f["name"]
            out.append(d)
        return out

    def resolve(self, ty: dict) -> dict:
        while "ref" in ty and self.types[ty["ref"]]["kind"] == "alias":
            ty = self.types[ty["ref"]]["type"]
        return ty

    def default(self, owner: str, field: dict) -> tuple[bool, object]:
        key = f"{owner}.{field['name']}"
        if key in DEFAULTS:
            return True, DEFAULTS[key]
        return self.type_default(field["type"])

    def type_default(self, ty: dict) -> tuple[bool, object]:
        ty = self.resolve(ty)
        if "list" in ty:
            return True, []
        if "map" in ty:
            return True, {}
        if "maybe" in ty:
            return True, None
        if "ref" in ty:
            t = self.types[ty["ref"]]
            if t["kind"] == "product" and t["encoding"] == "array":
                vals = [self.default(t["name"], f) for f in t["fields"]]
                if all(ok for ok, _ in vals):
                    return True, [v for _, v in vals]
        return False, None

    def annotate(self, owner: dict, con: dict) -> None:
        for f in con["fields"]:
            ok, value = self.default(con["name"], f)
            if ok:
                f["default"] = value
        lists = [f["name"] for f in con["fields"] if "list" in self.resolve(f["type"])]
        if len(lists) == 1:
            con["variadic"] = lists[0]
        # Fields of these products can be given as keyword arguments of the
        # constructor instead, e.g. Header(..., identifier="x").
        names = {f["name"] for f in con["fields"]}
        for f in con["fields"]:
            ref = f["type"].get("ref")
            if ref in ALIAS_FIELDS and ref != owner["name"]:
                inner = {g["name"] for g in self.types[ref]["fields"]}
                if not inner & names and not any(
                    inner & set(ALIAS_FIELDS[g["type"].get("ref", "")])
                    for g in con["fields"]
                    if g is not f and g["type"].get("ref") in ALIAS_FIELDS
                ):
                    f["flatten"] = True
                    names |= inner


# -- the corpus ------------------------------------------------------------


class Walker:
    """Visits pandoc JSON with its schema type and path in AST field names."""

    def __init__(self, schema: dict) -> None:
        self.types = {t["name"]: t for t in schema["types"]}
        self.seen: set[str] = set()

    def walk(self, j, ty: dict, path: list):
        yield j, ty, path
        if "prim" in ty:
            return
        if "list" in ty:
            for i, x in enumerate(j):
                yield from self.walk(x, ty["list"], path + [i])
        elif "maybe" in ty:
            if j is not None:
                yield from self.walk(j, ty["maybe"], path)
        elif "map" in ty:
            for k, x in j.items():
                yield from self.walk(x, ty["map"][1], path + [k])
        elif "tuple" in ty:
            for i, (x, t) in enumerate(zip(j, ty["tuple"])):
                yield from self.walk(x, t, path + [i])
        else:
            t = self.types[ty["ref"]]
            kind = t["kind"]
            if kind == "alias":
                yield from self.walk(j, t["type"], path)
            elif kind == "enum":
                self.seen.add(j["t"])
            elif kind == "sum":
                con = next(c for c in t["constructors"] if c["name"] == j["t"])
                self.seen.add(con["name"])
                yield from self.fields(con, con["encoding"], j.get("c"), path)
            else:
                self.seen.add(t["name"])
                yield from self.fields(t, t["encoding"], j, path)

    def fields(self, con: dict, encoding: str, c, path: list):
        fs = con["fields"]
        if encoding == "value":
            values = [c]
        elif encoding == "array":
            values = c
        else:  # object, root
            values = [c[f["key"]] for f in fs]
        for f, x in zip(fs, values):
            yield from self.walk(x, f["type"], path + [f["name"]])


def invalid_cases(schema: dict, docs: list[dict]) -> list[dict]:
    """Documents that must be rejected, each with where and why.

    Each case changes one value, in place, in a copy of a valid document.
    The value is found by walking the document with the schema, so its path
    is known.
    """
    rng = random.Random(0)
    cases: list[dict] = []

    def candidates(doc, pred):
        w = Walker(schema)
        return [(j, ty, p) for j, ty, p in w.walk(doc, {"ref": "Pandoc"}, []) if pred(j, ty)]

    def add(name: str, why: str, mutate, pred, at: tuple = ()) -> None:
        for doc in docs:
            doc = copy.deepcopy(doc)
            found = candidates(doc, pred)
            if found:
                j, ty, path = rng.choice(found)
                mutate(j)
                cases.append({"name": name, "why": why, "path": path + list(at), "document": doc})
                return
        fail(f"no document has a place for the invalid case {name}")

    def is_ref(name):
        return lambda j, ty: ty.get("ref") == name

    def replace(new):
        def m(j):
            j.clear()
            j.update(copy.deepcopy(new))

        return m

    add(
        "block-in-inlines",
        "a Block where an Inline belongs",
        replace({"t": "HorizontalRule"}),
        is_ref("Inline"),
    )
    add(
        "inline-in-blocks",
        "an Inline where a Block belongs",
        replace({"t": "Space"}),
        is_ref("Block"),
    )
    add(
        "unknown-inline",
        "no Inline constructor is called Bogus",
        replace({"t": "Bogus"}),
        is_ref("Inline"),
    )
    add(
        "unknown-enum-value",
        "no MathType is called Bogus",
        replace({"t": "Bogus"}),
        is_ref("MathType"),
    )

    def str_to_int(j):
        j["c"] = 42

    add(
        "int-for-string",
        "Str holds a string",
        str_to_int,
        lambda j, ty: ty.get("ref") == "Inline" and j["t"] == "Str",
        at=("text",),
    )

    def drop_last(j):
        j["c"].pop()

    add(
        "missing-field",
        "Header has three fields",
        drop_last,
        lambda j, ty: ty.get("ref") == "Block" and j["t"] == "Header",
    )

    def extra_field(j):
        j["c"].append([])

    add(
        "extra-field",
        "Div has two fields",
        extra_field,
        lambda j, ty: ty.get("ref") == "Block" and j["t"] == "Div",
    )

    def no_contents(j):
        del j["c"]

    add(
        "missing-contents",
        "Para has contents",
        no_contents,
        lambda j, ty: ty.get("ref") == "Block" and j["t"] == "Para",
    )

    def not_a_list(j):
        j["c"] = {"t": "Str", "c": "x"}

    add(
        "inline-for-inlines",
        "Emph holds a list of Inline, not one",
        not_a_list,
        lambda j, ty: ty.get("ref") == "Inline" and j["t"] == "Emph",
        at=("content",),
    )

    def attr_short(j):
        j["c"][0] = ["", []]

    add(
        "short-attr",
        "Attr has three elements",
        attr_short,
        lambda j, ty: ty.get("ref") == "Block" and j["t"] == "Div",
        at=("attr",),
    )

    def bad_attr_pair(j):
        j["c"][0][2] = [["k"]]

    add(
        "attribute-not-a-pair",
        "attributes are key-value pairs",
        bad_attr_pair,
        lambda j, ty: ty.get("ref") == "Inline" and j["t"] == "Span",
        at=(
            "attr",
            "attributes",
            0,
        ),
    )

    def bool_for_int(j):
        j["c"][0] = True

    add(
        "bool-for-int",
        "a Header level is an integer",
        bool_for_int,
        lambda j, ty: ty.get("ref") == "Block" and j["t"] == "Header",
        at=("level",),
    )

    def float_for_int(j):
        j["c"][0] = 1.5

    add(
        "float-for-int",
        "a Header level is an integer",
        float_for_int,
        lambda j, ty: ty.get("ref") == "Block" and j["t"] == "Header",
        at=("level",),
    )

    def missing_key(j):
        del j["citationMode"]

    add("citation-missing-key", "a Citation has a citationMode", missing_key, is_ref("Citation"))

    def meta_not_value(j):
        j["t"] = "MetaNumber"

    add(
        "unknown-meta-value",
        "no MetaValue is called MetaNumber",
        meta_not_value,
        is_ref("MetaValue"),
    )

    def string_for_list(j):
        j["c"] = "text"

    add(
        "string-for-inlines",
        "Para holds a list of Inline, not a string",
        string_for_list,
        lambda j, ty: ty.get("ref") == "Block" and j["t"] == "Para",
        at=("content",),
    )

    def null_for_string(j):
        j["c"][1] = None

    add(
        "null-for-string",
        "CodeBlock's text isn't optional",
        null_for_string,
        lambda j, ty: ty.get("ref") == "Block" and j["t"] == "CodeBlock",
        at=("text",),
    )

    # the document itself
    doc = copy.deepcopy(docs[0])
    doc["pandoc-api-version"] = [1, 22]
    cases.append(
        {
            "name": "api-version",
            "why": "pandoc-api-version 1.22 isn't 1.23",
            "path": ["pandoc-api-version"],
            "document": doc,
        }
    )
    doc = copy.deepcopy(docs[0])
    del doc["blocks"]
    cases.append({"name": "no-blocks", "why": "a document has blocks", "path": [], "document": doc})
    return cases


def main() -> None:
    reified = json.loads((ROOT / "schema/reified.json").read_text())
    schema = Deriver(reified).run()
    (ROOT / "schema/pandoc-ast.json").write_text(json.dumps(schema, indent=1) + "\n")

    docs = [
        json.loads(line)
        for line in (ROOT / "corpus/arbitrary.jsonl").read_text(encoding="utf-8").split("\n")
        if line
    ]
    w = Walker(schema)
    for doc in docs:
        for _ in w.walk(doc, {"ref": schema["root"]}, []):
            pass
    everything = set()
    for t in schema["types"]:
        if t["kind"] == "enum":
            everything |= set(t["values"])
        elif t["kind"] == "sum":
            everything |= {c["name"] for c in t["constructors"]}
        elif t["kind"] == "product" and t["encoding"] != "array":
            everything.add(t["name"])
    if everything - w.seen:
        fail(f"corpus/arbitrary.jsonl never uses {sorted(everything - w.seen)}")

    cases = invalid_cases(schema, docs)
    (ROOT / "corpus/invalid.jsonl").write_text("".join(json.dumps(c) + "\n" for c in cases))


if __name__ == "__main__":
    main()
