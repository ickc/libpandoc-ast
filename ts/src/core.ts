/**
 * The generic part of the AST: everything that isn't a declaration.
 *
 * `generated.ts` declares the types and holds the schema (`SCHEMA`); this
 * module interprets the schema, the same way for every type:
 *
 * - decodes and encodes pandoc's JSON, saying where it is wrong
 *   (`ASTDecodeError`);
 * - builds nodes from constructor arguments (`make`), filling defaults,
 *   and checks values put into them (`ASTTypeError`, `check`).
 *
 * Nothing here knows a pandoc type by name.
 */

import { SCHEMA } from "./generated.ts";

// -- the schema's shape ---------------------------------------------------------

export type TypeExpr =
  | { prim: "string" | "int" | "double" | "bool" }
  | { ref: string }
  | { list: TypeExpr }
  | { maybe: TypeExpr }
  | { map: [TypeExpr, TypeExpr] }
  | { tuple: TypeExpr[] };

export interface Field {
  name: string;
  key: string;
  type: TypeExpr;
  default?: unknown;
  flatten?: boolean;
}

export interface Constructor {
  name: string;
  encoding: string;
  fields: Field[];
  variadic?: string;
}

export type TypeDecl =
  | { name: string; kind: "sum"; constructors: Constructor[] }
  | { name: string; kind: "product"; encoding: string; fields: Field[]; variadic?: string }
  | { name: string; kind: "enum"; values: string[] }
  | { name: string; kind: "alias"; type: TypeExpr };

export interface Schema {
  "pandoc-api-version": number[];
  root: string;
  types: TypeDecl[];
}

// -- errors -------------------------------------------------------------------

export type Path = (string | number)[];

export function formatPath(path: Path): string {
  let out = "";
  for (const p of path) {
    if (typeof p === "number") out += `[${p}]`;
    else if (/^[A-Za-z_][A-Za-z0-9_]*$/.test(p) || !out) out += out ? `.${p}` : p;
    else out += `[${JSON.stringify(p)}]`;
  }
  return out;
}

/** A value that doesn't fit pandoc's AST: `where` it is, what was expected, what it got. */
export class ASTError extends Error {
  where: string;
  expected: string;
  got: string;
  constructor(where: string, expected: string, got: string) {
    super(where ? `${where}: expected ${expected}, got ${got}` : `expected ${expected}, got ${got}`);
    this.where = where;
    this.expected = expected;
    this.got = got;
  }
}

/** A value given to a constructor, or found by `check`, of the wrong type. */
export class ASTTypeError extends ASTError {
  override name = "ASTTypeError";
}

/** JSON that isn't a pandoc document (or node) of this API version. */
export class ASTDecodeError extends ASTError {
  override name = "ASTDecodeError";
  path: Path;
  constructor(path: Path, expected: string, got: string) {
    super(formatPath(path), expected, got);
    this.path = path;
  }
}

/** Thrown while decoding; the path is collected on the way up. */
class Bad {
  expected: string;
  got: string;
  path: Path = [];
  constructor(expected: string, got: string) {
    this.expected = expected;
    this.got = got;
  }
}

function article(word: string): string {
  return /^[AEIOU]/.test(word) ? "an" : "a";
}

function describe(v: unknown): string {
  if (v === null) return "null";
  if (v === undefined) return "undefined";
  if (typeof v === "object" && !Array.isArray(v) && typeof (v as { t?: unknown }).t === "string") {
    const t = (v as { t: string }).t;
    const owner = tables().tagOwner.get(t);
    if (owner) return `${t} (${article(owner)} ${owner})`;
    return `"t": ${JSON.stringify(t)} (no such constructor)`;
  }
  let text: string;
  try {
    text = JSON.stringify(v) ?? String(v);
  } catch {
    text = String(v);
  }
  return text.length > 60 ? `${text.slice(0, 57)}...` : text;
}

// -- tables built from the schema -------------------------------------------

interface Tables {
  types: Map<string, TypeDecl>;
  /** constructor name -> its sum type */
  tagOwner: Map<string, string>;
  /** constructor or product name -> its declaration */
  nodes: Map<string, { fields: Field[]; tag: boolean; encoding: string; owner: string }>;
}

let cache: Tables | undefined;

export function tables(): Tables {
  if (cache) return cache;
  const types = new Map<string, TypeDecl>();
  const tagOwner = new Map<string, string>();
  const nodes: Tables["nodes"] = new Map();
  for (const t of SCHEMA.types) {
    types.set(t.name, t);
    if (t.kind === "sum") {
      for (const c of t.constructors) {
        tagOwner.set(c.name, t.name);
        nodes.set(c.name, { fields: c.fields, tag: true, encoding: c.encoding, owner: t.name });
      }
    } else if (t.kind === "product") {
      nodes.set(t.name, { fields: t.fields, tag: false, encoding: t.encoding, owner: t.name });
    }
  }
  cache = { types, tagOwner, nodes };
  return cache;
}

export function resolve(ty: TypeExpr): TypeExpr {
  while ("ref" in ty) {
    const t = tables().types.get(ty.ref)!;
    if (t.kind !== "alias") break;
    ty = t.type;
  }
  return ty;
}

function typeName(ty: TypeExpr): string {
  ty = resolve(ty);
  if ("prim" in ty) {
    return { string: "a string", int: "an integer", double: "a number", bool: "a boolean" }[ty.prim];
  }
  if ("list" in ty) return `a list of ${typeName(ty.list)}`;
  if ("maybe" in ty) return `${typeName(ty.maybe)} or null`;
  if ("map" in ty) return `an object of ${typeName(ty.map[1])}`;
  if ("tuple" in ty) return `a list of ${ty.tuple.length}`;
  const t = tables().types.get(ty.ref)!;
  return t.kind === "sum" ? t.name : `${article(t.name)} ${t.name}`;
}

function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function withPath<T>(key: string | number, f: () => T): T {
  try {
    return f();
  } catch (e) {
    if (e instanceof Bad) e.path.push(key);
    throw e;
  }
}

// -- decoding -------------------------------------------------------------------

function decodePrim(prim: string, j: unknown): unknown {
  switch (prim) {
    case "string":
      if (typeof j === "string") return j;
      break;
    case "int":
      if (typeof j === "number" && Number.isInteger(j)) return j;
      break;
    case "double":
      if (typeof j === "number") return j;
      break;
    case "bool":
      if (typeof j === "boolean") return j;
      break;
  }
  throw new Bad(typeName({ prim } as TypeExpr), describe(j));
}

function decode(ty: TypeExpr, j: unknown): unknown {
  ty = resolve(ty);
  if ("prim" in ty) return decodePrim(ty.prim, j);
  if ("list" in ty) {
    if (!Array.isArray(j)) throw new Bad("a list", describe(j));
    const item = ty.list;
    return j.map((x, i) => withPath(i, () => decode(item, x)));
  }
  if ("maybe" in ty) return j === null ? null : decode(ty.maybe, j);
  if ("map" in ty) {
    if (!isObject(j)) throw new Bad("an object", describe(j));
    const out: Record<string, unknown> = {};
    for (const [k, x] of Object.entries(j)) out[k] = withPath(k, () => decode((ty as { map: [TypeExpr, TypeExpr] }).map[1], x));
    return out;
  }
  if ("tuple" in ty) {
    const items = ty.tuple;
    if (!Array.isArray(j) || j.length !== items.length) {
      throw new Bad(`a list of ${items.length}`, describe(j));
    }
    return items.map((t, i) => withPath(i, () => decode(t, j[i])));
  }
  const t = tables().types.get(ty.ref)!;
  if (t.kind === "enum") {
    if (isObject(j) && typeof j.t === "string" && t.values.includes(j.t)) return j.t;
    throw new Bad(`${article(t.name)} ${t.name}`, describe(j));
  }
  if (t.kind === "sum") {
    const c = isObject(j) && typeof j.t === "string" ? t.constructors.find((c) => c.name === j.t) : undefined;
    if (!c) throw new Bad(t.name, describe(j));
    const out: Record<string, unknown> = { t: c.name };
    const obj = j as Record<string, unknown>;
    if (c.encoding === "none") return out;
    if (!("c" in obj)) throw new Bad(`${c.name} with contents`, `${c.name} without`);
    decodeFields(c.name, c.fields, c.encoding, obj.c, out);
    return out;
  }
  if (t.kind === "product") {
    const out: Record<string, unknown> = {};
    if (t.encoding === "root") {
      if (!isObject(j)) throw new Bad(`an object (${t.name})`, describe(j));
      const v = j["pandoc-api-version"];
      const want = SCHEMA["pandoc-api-version"];
      if (!Array.isArray(v) || v[0] !== want[0] || v[1] !== want[1]) {
        const e = new Bad(`pandoc-api-version ${want[0]}.${want[1]}.*`, describe(v));
        e.path.push("pandoc-api-version");
        throw e;
      }
    }
    decodeFields(t.name, t.fields, t.encoding, j, out);
    return out;
  }
  throw new Error(`unknown type ${ty.ref}`);
}

function decodeFields(name: string, fields: Field[], encoding: string, c: unknown,
                      out: Record<string, unknown>): void {
  if (encoding === "value") {
    out[fields[0].name] = withPath(fields[0].name, () => decode(fields[0].type, c));
    return;
  }
  if (encoding === "array") {
    if (!Array.isArray(c) || c.length !== fields.length) {
      const got = Array.isArray(c) ? `${name} with ${c.length}` : describe(c);
      throw new Bad(`${name} with ${fields.length} fields`, got);
    }
    fields.forEach((f, i) => { out[f.name] = withPath(f.name, () => decode(f.type, c[i])); });
    return;
  }
  if (!isObject(c)) throw new Bad(`an object (${name})`, describe(c));
  for (const f of fields) {
    if (!(f.key in c)) throw new Bad(`${name} with ${JSON.stringify(f.key)}`, "one without");
    out[f.name] = withPath(f.name, () => decode(f.type, c[f.key]));
  }
}

/** A value of a type (default: a document) from pandoc's JSON, checked. */
export function fromJSON(j: unknown, type: string = SCHEMA.root): unknown {
  try {
    return decode({ ref: type }, j);
  } catch (e) {
    if (e instanceof Bad) throw new ASTDecodeError(e.path.reverse(), e.expected, e.got);
    throw e;
  }
}

// -- encoding and checking ------------------------------------------------------

function encode(ty: TypeExpr, v: unknown): unknown {
  ty = resolve(ty);
  if ("prim" in ty) return decodePrim(ty.prim, v);
  if ("list" in ty) {
    if (!Array.isArray(v)) throw new Bad("a list", describe(v));
    const item = ty.list;
    return v.map((x, i) => withPath(i, () => encode(item, x)));
  }
  if ("maybe" in ty) return v === null || v === undefined ? null : encode(ty.maybe, v);
  if ("map" in ty) {
    if (!isObject(v)) throw new Bad("an object", describe(v));
    const out: Record<string, unknown> = {};
    for (const [k, x] of Object.entries(v)) out[k] = withPath(k, () => encode((ty as { map: [TypeExpr, TypeExpr] }).map[1], x));
    return out;
  }
  if ("tuple" in ty) {
    const items = ty.tuple;
    if (!Array.isArray(v) || v.length !== items.length) throw new Bad(typeName(ty), describe(v));
    return items.map((t, i) => withPath(i, () => encode(t, v[i])));
  }
  const t = tables().types.get(ty.ref)!;
  if (t.kind === "enum") {
    if (typeof v === "string" && t.values.includes(v)) return { t: v };
    throw new Bad(`${article(t.name)} ${t.name}`, describe(v));
  }
  if (t.kind === "sum") {
    const c = isObject(v) && typeof v.t === "string" ? t.constructors.find((c) => c.name === v.t) : undefined;
    if (!c) throw new Bad(t.name, describe(v));
    if (c.encoding === "none") return { t: c.name };
    return { t: c.name, c: encodeFields(c.fields, c.encoding, v as Record<string, unknown>) };
  }
  if (t.kind === "product") {
    if (!isObject(v)) throw new Bad(`${article(t.name)} ${t.name}`, describe(v));
    const body = encodeFields(t.fields, t.encoding, v);
    if (t.encoding === "root") {
      return { "pandoc-api-version": [...SCHEMA["pandoc-api-version"]], ...(body as object) };
    }
    return body;
  }
  throw new Error(`unknown type ${ty.ref}`);
}

function encodeFields(fields: Field[], encoding: string, v: Record<string, unknown>): unknown {
  const values = fields.map((f) => withPath(f.name, () => encode(f.type, v[f.name])));
  if (encoding === "value") return values[0];
  if (encoding === "array") return values;
  const out: Record<string, unknown> = {};
  fields.forEach((f, i) => { out[f.key] = values[i]; });
  return out;
}

/** A value (default: a document) as pandoc's JSON; checks it on the way. */
export function toJSON(v: unknown, type: string = SCHEMA.root): unknown {
  try {
    return encode({ ref: type }, v);
  } catch (e) {
    if (e instanceof Bad) {
      throw new ASTTypeError(formatPath([type, ...e.path.reverse()]), e.expected, e.got);
    }
    throw e;
  }
}

/** Throw `ASTTypeError` if a value (default: a document) isn't well-typed. */
export function check(v: unknown, type: string = SCHEMA.root): void {
  toJSON(v, type);
}

// -- constructors ---------------------------------------------------------------

// -- strings, as pandoc's Lua converts them ----------------------------------

/**
 * Words and spaces, as pandoc-types' `text` (and pandoc's Lua) split a
 * string: `Str` for each run of non-spaces, and for each run of spaces
 * `SoftBreak` if it has a newline, else `Space`.
 */
export function textInlines(s: string): unknown[] {
  const out: unknown[] = [];
  for (const [run] of s.matchAll(/[ \t\n\r]+|[^ \t\n\r]+/g)) {
    if (" \t\n\r".includes(run[0])) out.push({ t: /[\n\r]/.test(run) ? "SoftBreak" : "Space" });
    else out.push({ t: "Str", text: run });
  }
  return out;
}

/** The value with its strings converted as pandoc's Lua does: where a list
 * of inlines goes, a string is its words and spaces; where one inline goes,
 * a `Str`; where blocks go, `Plain` text. Anything else is left for
 * `encode` to check. */
function fromStrings(ty: TypeExpr, v: unknown): unknown {
  const r = resolve(ty);
  if (typeof v === "string" && "ref" in r) {
    if (r.ref === "Inline") return { t: "Str", text: v };
    if (r.ref === "Block") return { t: "Plain", content: textInlines(v) };
    return v;
  }
  if ("list" in r) {
    const item = resolve(r.list);
    if (typeof v === "string" && "ref" in item) {
      if (item.ref === "Inline") return textInlines(v);
      if (item.ref === "Block") return [{ t: "Plain", content: textInlines(v) }];
    }
    return Array.isArray(v) ? mapChanged(v, (x) => fromStrings(r.list, x)) : v;
  }
  if ("tuple" in r && Array.isArray(v)) {
    return mapChanged(v, (x, i) => (i < r.tuple.length ? fromStrings(r.tuple[i], x) : x));
  }
  return v;
}

/** xs mapped, or xs itself if nothing changed. */
function mapChanged(xs: unknown[], f: (x: unknown, i: number) => unknown): unknown[] {
  let out: unknown[] | undefined;
  xs.forEach((x, i) => {
    const y = f(x, i);
    if (y !== x && out === undefined) out = xs.slice(0, i);
    if (out !== undefined) out.push(y);
  });
  return out ?? xs;
}

function coerce(ty: TypeExpr, v: unknown, where: string): unknown {
  const r = resolve(ty);
  // attributes may be given as a record
  if ("list" in r && "tuple" in r.list && isObject(v)) v = Object.entries(v);
  v = fromStrings(ty, v);
  try {
    encode(ty, v);
  } catch (e) {
    if (e instanceof Bad) {
      let hint = "";
      if (typeof v === "string" && "list" in r && "ref" in r.list) hint = " (a string; give a list of nodes)";
      throw new ASTTypeError(where + formatPath(e.path.reverse()).replace(/^([^[])/, ".$1"),
                             e.expected, e.got + hint);
    }
    throw e;
  }
  return v;
}

/** Build a node from a generated constructor's arguments. */
export function make<T>(name: string, given: Record<string, unknown>,
                        opts: Record<string, unknown>): T {
  const node = tables().nodes.get(name)!;
  const out: Record<string, unknown> = node.tag ? { t: name } : {};
  const known = new Set<string>();
  for (const f of node.fields) {
    known.add(f.name);
    let v = f.name in given ? given[f.name] : opts[f.name];
    if (f.flatten) {
      const product = tables().nodes.get((f.type as { ref: string }).ref)!;
      const parts = product.fields.filter((g) => opts[g.name] !== undefined).map((g) => g.name);
      product.fields.forEach((g) => known.add(g.name));
      if (v !== undefined && parts.length) {
        throw new TypeError(`${name}(): give either ${f.name} or ${parts.join(", ")}, not both`);
      }
      if (v === undefined) {
        const missing = product.fields.filter((g) => !("default" in g) && opts[g.name] === undefined);
        if (missing.length) {
          throw new TypeError(`${name}() needs ${missing.map((g) => g.name).join(", ")} (or ${f.name})`);
        }
        const own = Object.fromEntries(product.fields.filter((g) => opts[g.name] !== undefined)
                                                     .map((g) => [g.name, opts[g.name]]));
        v = make<unknown>((f.type as { ref: string }).ref, {}, own);
      }
    }
    if (v === undefined) {
      if (!("default" in f)) throw new TypeError(`${name}() needs ${f.name}`);
      v = decode(f.type, f.default); // a fresh value each time
    }
    out[f.name] = coerce(f.type, v, `${name}.${f.name}`);
  }
  const unknown = Object.keys(opts).filter((k) => !known.has(k));
  if (unknown.length) {
    throw new TypeError(`${name}() has no option ${unknown.join(", ")}`);
  }
  return out as T;
}
