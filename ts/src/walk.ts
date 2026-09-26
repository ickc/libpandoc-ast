/**
 * Walking a document, and filters: functions by node type, as in pandoc's
 * Lua filters.
 *
 *     const upper: Filter = {
 *       Str: (s) => { s.text = s.text.toUpperCase(); },
 *     };
 *     applyFilter(doc, upper);
 *
 * Generic over the schema, like `core.ts`.
 */

import { ASTTypeError, formatPath, resolve, tables } from "./core.ts";
import type { Path, TypeExpr } from "./core.ts";
import { SCHEMA } from "./generated.ts";
import type { Nodes, Pandoc, Sums } from "./generated.ts";

/** Where a node is: its parent, its place in it, the document, the output format. */
export class Context {
  /** The node whose field holds this one. */
  parent: unknown;
  /** That field's name. */
  field: string | undefined;
  /** The list holding this node, if in one, and its index there (or key, in a map). */
  container: unknown[] | Record<string, unknown> | undefined;
  index: number | string | undefined;
  doc: unknown;
  format: string | undefined;
  #path: Path;
  #ancestors: unknown[];

  constructor(frames: Frame[], doc: unknown, format: string | undefined) {
    const last = frames[frames.length - 1];
    this.parent = last?.parent;
    this.field = last?.field;
    this.container = last?.container;
    this.index = last?.index;
    this.doc = doc;
    this.format = format;
    this.#path = frames.flatMap((f) => [
      ...(f.field === undefined ? [] : [f.field]),
      ...f.outer,
      ...(f.index === undefined ? [] : [f.index]),
    ]);
    this.#ancestors = [];
    for (const f of frames) {
      if (this.#ancestors[this.#ancestors.length - 1] !== f.parent) this.#ancestors.push(f.parent);
    }
  }

  /** From the document, e.g. `["blocks", 3, "content", 1]`. */
  get path(): Path {
    return [...this.#path];
  }

  /** The path as text, e.g. `blocks[3].content[1]`. */
  get where(): string {
    return formatPath(this.#path) || "the document";
  }

  /** The nodes above this one, the document first. */
  get ancestors(): unknown[] {
    return [...this.#ancestors];
  }

  #sibling(step: number): unknown {
    if (!Array.isArray(this.container) || typeof this.index !== "number") return undefined;
    return this.container[this.index + step];
  }

  get next(): unknown {
    return this.#sibling(1);
  }

  get prev(): unknown {
    return this.#sibling(-1);
  }
}

interface Frame {
  parent: unknown;
  field: string | undefined;
  outer: (string | number)[];
  container: unknown[] | Record<string, unknown> | undefined;
  index: number | string | undefined;
}

/** What a filter function returns: nothing to keep the node, a node to replace it, a list to splice. */
export type Result<T> = void | undefined | null | T | T[];

type Fn<N, R> = (node: N, ctx: Context) => Result<R>;

/**
 * Functions by constructor (`Str`, `Header`), sum type (`Inline`, `Block`,
 * `MetaValue`) or product (`Attr`, `Cell`, `Pandoc`). A node gets the one
 * for its constructor, or else its type's.
 */
export type Filter = {
  [K in keyof Nodes]?: Fn<Nodes[K], OwnerOf<K>>;
} & {
  [K in keyof Sums]?: Fn<Sums[K], Sums[K]>;
} & {
  /** Visit a node before its children (default: after). */
  topDown?: boolean;
};

type OwnerOf<K extends keyof Nodes> = {
  [S in keyof Sums]: Nodes[K] extends Sums[S] ? Sums[S] : never;
}[keyof Sums] extends infer U ? ([U] extends [never] ? Nodes[K] : U) : never;

type Action = (node: unknown, ctx: Context, type: string) => unknown;

class Walker {
  frames: Frame[] = [];
  action: Action;
  topDown: boolean;
  doc: unknown;
  format: string | undefined;

  constructor(action: Action, topDown: boolean, doc: unknown, format: string | undefined) {
    this.action = action;
    this.topDown = topDown;
    this.doc = doc;
    this.format = format;
  }

  call(node: unknown, type: string): unknown {
    return this.action(node, new Context(this.frames, this.doc, this.format), type);
  }

  /** A node in a position holding one node; returns it or its replacement. */
  one(node: unknown, type: string, where: string): unknown {
    if (this.topDown) {
      node = single(this.call(node, type), node, where);
      this.children(node, type);
      return node;
    }
    this.children(node, type);
    return single(this.call(node, type), node, where);
  }

  /** The nodes of a list: each may be replaced, deleted or spliced. */
  many(list: unknown[], type: string, parent: unknown, field: string, outer: (string | number)[]): void {
    const frame: Frame = { parent, field, outer, container: list, index: 0 };
    this.frames.push(frame);
    try {
      let i = 0;
      while (i < list.length) {
        frame.index = i;
        if (!this.topDown) this.children(list[i], type);
        const r = this.call(list[i], type);
        if (r === undefined || r === null) {
          if (this.topDown) this.children(list[i], type);
          i++;
          continue;
        }
        const items = Array.isArray(r) ? r : [r];
        list.splice(i, 1, ...items);
        if (this.topDown) {
          for (let k = 0; k < items.length; k++) {
            frame.index = i + k;
            this.children(list[i + k], type);
          }
        }
        i += items.length;
      }
    } finally {
      this.frames.pop();
    }
  }

  /** Walk a field's value; returns it, or its replacement. */
  value(v: unknown, ty: TypeExpr, parent: unknown, field: string, outer: (string | number)[]): unknown {
    const r = resolve(ty);
    if ("prim" in r || v === null || v === undefined) return v;
    if ("ref" in r) {
      const t = tables().types.get(r.ref)!;
      if (t.kind === "enum") return v;
      this.frames.push({ parent, field, outer, container: undefined, index: undefined });
      try {
        return this.one(v, r.ref, `${field}${formatPath(outer)}`);
      } finally {
        this.frames.pop();
      }
    }
    if ("maybe" in r) return this.value(v, r.maybe, parent, field, outer);
    if ("list" in r) {
      const item = resolve(r.list);
      const list = v as unknown[];
      if ("ref" in item && tables().types.get(item.ref)!.kind !== "enum") {
        this.many(list, item.ref, parent, field, outer);
      } else if (!("prim" in item)) {
        list.forEach((x, i) => {
          const y = this.value(x, r.list, parent, field, [...outer, i]);
          if (y !== x) list[i] = y;
        });
      }
      return v;
    }
    if ("map" in r) {
      const obj = v as Record<string, unknown>;
      for (const k of Object.keys(obj)) {
        const y = this.value(obj[k], r.map[1], parent, field, [...outer, k]);
        if (y !== obj[k]) obj[k] = y;
      }
      return v;
    }
    const tuple = v as unknown[];
    r.tuple.forEach((t, i) => {
      const y = this.value(tuple[i], t, parent, field, [...outer, i]);
      if (y !== tuple[i]) tuple[i] = y;
    });
    return v;
  }

  children(node: unknown, type: string): void {
    const decl = tables().types.get(type)!;
    let fields;
    if (decl.kind === "sum") {
      const tag = (node as { t: string }).t;
      fields = tables().nodes.get(tag)?.fields ?? [];
    } else if (decl.kind === "product") {
      fields = decl.fields;
    } else {
      return;
    }
    const obj = node as Record<string, unknown>;
    for (const f of fields) {
      const y = this.value(obj[f.name], f.type, node, f.name, []);
      if (y !== obj[f.name]) obj[f.name] = y;
    }
  }
}

function single(r: unknown, node: unknown, where: string): unknown {
  if (r === undefined || r === null) return node;
  if (Array.isArray(r)) {
    throw new ASTTypeError(where, "one node (this position holds one)", "a list");
  }
  return r;
}

/**
 * Call `action(node, ctx, type)` on `node` and everything in it, bottom-up
 * (or `topDown`). `action` returns nothing to keep the node, a node to
 * replace it, or in a list, a list to splice in its place (`[]` deletes).
 * Returns `node` or its replacement. `type` is the schema type of `node`
 * (default: a document).
 */
export function walk(node: unknown, action: Action,
                     opts: { type?: string; topDown?: boolean; format?: string } = {}): unknown {
  const w = new Walker(action, opts.topDown ?? false, node, opts.format);
  const type = opts.type ?? SCHEMA.root;
  return w.one(node, type, type);
}

/** Apply a filter to a document, in place; returns it (or its replacement). */
export function applyFilter(doc: Pandoc, filter: Filter, format?: string): Pandoc {
  const fns = filter as Record<string, Fn<unknown, unknown> | undefined>;
  const action: Action = (node, ctx, type) => {
    const tag = (node as { t?: unknown }).t;
    const fn = (typeof tag === "string" ? fns[tag] : undefined) ?? fns[type];
    if (!fn) return undefined;
    try {
      return fn(node, ctx);
    } catch (e) {
      if (e instanceof Error && !(e as { noted?: boolean }).noted) {
        e.message += `\n  in filter function ${fn.name || "(anonymous)"}, on the ${typeof tag === "string" ? tag : type} at ${ctx.where}`;
        (e as { noted?: boolean }).noted = true;
      }
      throw e;
    }
  };
  return walk(doc, action, { topDown: filter.topDown, format }) as Pandoc;
}
