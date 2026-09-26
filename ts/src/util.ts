/** Helpers: the text of nodes, and metadata to and from plain values. */

import { walk } from "./walk.ts";
import type { MetaValue } from "./generated.ts";

const QUOTES: Record<string, [string, string]> = {
  SingleQuote: ["‘", "’"],
  DoubleQuote: ["“", "”"],
};

/**
 * The text of a node or list of nodes, without markup, as pandoc's
 * `stringify`: spaces and breaks become " ", quotes curly quotes, notes and
 * citations' data are dropped.
 */
export function stringify(value: unknown): string {
  if (Array.isArray(value)) return value.map(stringify).join("");
  if (typeof value !== "object" || value === null) return "";
  const node = value as { t?: string; [k: string]: unknown };
  switch (node.t) {
    case "Str":
    case "Code":
    case "Math":
    case "MetaString":
      return node.text as string;
    case "Space":
    case "SoftBreak":
    case "LineBreak":
      return " ";
    case "RawInline":
      return node.format === "html" && (node.text as string).startsWith("<br") ? " " : "";
    case "Note":
      return "";
    case "Cite":
      return stringify(node.content);
    case "Quoted": {
      const [l, r] = QUOTES[node.quoteType as string];
      return l + stringify(node.content) + r;
    }
    case "MetaBool":
      return node.value ? "true" : "false";
  }
  if (node.t === undefined && "blocks" in node) return stringify(node.blocks);
  // any other node: the text of its fields, in order
  let out = "";
  for (const [k, v] of Object.entries(node)) {
    if (k !== "t" && k !== "attr" && typeof v === "object") out += stringify(v);
  }
  return out;
}

/** Metadata as plain values: string, boolean, array, object. */
export function toPlain(value: MetaValue | Record<string, MetaValue>): unknown {
  if (!("t" in value) || typeof value.t !== "string") {
    return Object.fromEntries(Object.entries(value as Record<string, MetaValue>).map(([k, v]) => [k, toPlain(v)]));
  }
  const v = value as MetaValue;
  switch (v.t) {
    case "MetaMap":
      return toPlain(v.content);
    case "MetaList":
      return v.content.map(toPlain);
    case "MetaBool":
      return v.value;
    case "MetaString":
      return v.text;
    case "MetaInlines":
    case "MetaBlocks":
      return stringify(v.content);
  }
}

/** A plain value as metadata: string, boolean, number (as a string), array, object. */
export function fromPlain(value: unknown): MetaValue {
  if (typeof value === "string") return { t: "MetaString", text: value };
  if (typeof value === "number") return { t: "MetaString", text: String(value) };
  if (typeof value === "boolean") return { t: "MetaBool", value };
  if (Array.isArray(value)) return { t: "MetaList", content: value.map(fromPlain) };
  if (typeof value === "object" && value !== null) {
    if (typeof (value as { t?: unknown }).t === "string") return value as MetaValue;
    return {
      t: "MetaMap",
      content: Object.fromEntries(Object.entries(value).map(([k, v]) => [k, fromPlain(v)])),
    };
  }
  throw new TypeError(`no metadata form for ${String(value)}`);
}

export { walk };
