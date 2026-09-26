/**
 * pandoc's document AST, generated from pandoc-types.
 *
 * Nodes are plain objects with named fields, discriminated by `t`:
 * `{ t: "Header", level: 1, attr: {...}, content: [...] }`. `parse` and
 * `serialize` read and write pandoc's JSON; filters are objects of
 * functions by node type, as in pandoc's Lua filters.
 */

import { fromJSON, toJSON } from "./core.ts";
import type { Pandoc } from "./generated.ts";

export * from "./generated.ts";
export { ASTDecodeError, ASTError, ASTTypeError, check, formatPath, fromJSON, toJSON } from "./core.ts";
export type { Path } from "./core.ts";
export { applyFilter, Context, walk } from "./walk.ts";
export type { Filter, Result } from "./walk.ts";
export { fromPlain, stringify, toPlain } from "./util.ts";

/** A document from pandoc's JSON text, checked. */
export function parse(text: string): Pandoc {
  return fromJSON(JSON.parse(text)) as Pandoc;
}

/** A document as pandoc's JSON text. */
export function serialize(doc: Pandoc): string {
  return JSON.stringify(toJSON(doc));
}
