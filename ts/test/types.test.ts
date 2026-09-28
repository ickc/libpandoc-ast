// The types: what TypeScript accepts and rejects. The `@ts-expect-error`
// lines must be errors (tsc -p tsconfig.test.json fails on an unused one),
// and the rest must compile. At run time, constructors throw, and
// serialize checks what filters made.

import { test } from "node:test";
import assert from "node:assert/strict";
import {
  applyFilter, ASTTypeError, Emph, Header, Para, parse, serialize, Str,
} from "../src/index.ts";
import type { Block, Filter, Inline, Pandoc } from "../src/index.ts";

const doc = (): Pandoc => parse(serialize({
  "pandoc-api-version": [1, 23, 1], meta: {}, blocks: [Header(1, [Str("a")]), Para([Emph([Str("b")])])],
} as Pandoc));

test("constructors take their fields' types", () => {
  // @ts-expect-error: a level is a number
  assert.throws(() => Header("1", [Str("a")]), ASTTypeError);
  // @ts-expect-error: a paragraph holds inlines
  assert.throws(() => Para([Para([])]), ASTTypeError);
  // @ts-expect-error: a Str's text is a string
  assert.throws(() => Str(1), ASTTypeError);
});

test("fields are typed", () => {
  const h = Header(1, [Str("a")]);
  // @ts-expect-error: a level is a number
  h.level = "2";
  // @ts-expect-error: no such field
  assert.equal(h.text, undefined);
  // @ts-expect-error: inlines only
  h.content.push(Para([]));
});

test("switch on t narrows", () => {
  const texts: string[] = [];
  const all = (xs: Inline[]) => xs.forEach((x) => {
    switch (x.t) {
      case "Str": texts.push(x.text); break;          // a Str has text
      case "Emph": all(x.content); break;             // an Emph has content
      // @ts-expect-error: not an inline
      case "Para": break;
    }
  });
  all([Str("a"), Emph([Str("b")])]);
  assert.deepEqual(texts, ["a", "b"]);
});

test("filter functions are typed by node", () => {
  const f: Filter = {
    Str: (s) => Str(s.text.toUpperCase()),  // s is a Str
    Header: (h) => { h.level += 1; },       // h is a Header
    // @ts-expect-error: a Str has no level
    Code: (c) => { c.level = 1; },
  };
  applyFilter(doc(), f);
  const g: Filter = {
    // @ts-expect-error: an inline's function returns inlines, not blocks
    Str: () => Para([]),
  };
  // at run time, serialize checks what filters made
  assert.throws(() => serialize(applyFilter(doc(), g)), ASTTypeError);
  // @ts-expect-error: only the three orders
  const h: Filter = { traverse: "sideways" };
  assert.throws(() => applyFilter(doc(), h), /traverse/);
  const k: Filter = {
    // @ts-expect-error: a list of inlines' function returns inlines
    Inlines: (xs) => [Para(xs)],
    Blocks: (xs: Block[]) => xs.slice(0, 1),
  };
  assert.throws(() => serialize(applyFilter(doc(), k)), ASTTypeError);
});
