import { test } from "node:test";
import assert from "node:assert/strict";
import {
  applyFilter, ASTTypeError, Attr, BulletList, Cell, Code, Div, Emph, Header, Link, Math, Note,
  OrderedList, Pandoc, Para, Plain, Quoted, Space, Str, Table, fromPlain, parse, serialize,
  stringify, toPlain,
} from "../src/index.ts";
import type { Filter, Inline } from "../src/index.ts";

test("constructors fill defaults and flatten attributes", () => {
  assert.deepEqual(Header(1, [Str("Hi")], { identifier: "hi", classes: ["x"] }), {
    t: "Header", level: 1,
    attr: { identifier: "hi", classes: ["x"], attributes: [] },
    content: [{ t: "Str", text: "Hi" }],
  });
  assert.deepEqual(Div([], { attributes: { k: "v" } }).attr, Attr("", [], [["k", "v"]]));
  assert.equal(OrderedList([[Plain([Str("a")])]], { start: 3 }).listAttributes.start, 3);
  assert.deepEqual(OrderedList().listAttributes, { start: 1, style: "DefaultStyle", delimiter: "DefaultDelim" });
  assert.equal(Cell([Para()]).rowSpan, 1);
  assert.deepEqual(Table().bodies, []);
  assert.deepEqual(Link([Str("x")], { url: "u" }).target, { url: "u", title: "" });
});

test("constructors check their arguments, and say where", () => {
  const cases: [() => unknown, RegExp][] = [
    [() => Para([Para() as unknown as Inline]), /^Para\.content\[0\]: expected Inline, got Para \(a Block\)$/],
    [() => Header(1, "Hi" as unknown as Inline[]), /Header\.content: expected a list, got "Hi" \(a string; give a list of nodes\)/],
    [() => Math("Bogus" as "InlineMath", "x"), /Math\.mathType: expected a MathType, got "Bogus"/],
    [() => BulletList([[Str("x") as never]]), /BulletList\.content\[0\]\[0\]: expected Block, got Str \(an Inline\)/],
    [() => Header(1.5, []), /Header\.level: expected an integer, got 1\.5/],
  ];
  for (const [f, message] of cases) {
    assert.throws(f, (e: unknown) => e instanceof ASTTypeError && message.test(e.message));
  }
  assert.throws(() => Link([Str("x")]), /Link\(\) needs url \(or target\)/);
  assert.throws(() => Code("x", { attr: Attr(), identifier: "y" }), /give either attr or identifier, not both/);
  assert.throws(() => Code("x", { bogus: 1 } as never), /Code\(\) has no option bogus/);
});

function doc() {
  return Pandoc([
    Header(1, [Str("Title")]),
    Para([Str("a"), Space(), Emph([Str("b")]), Note([Para([Str("n")])])]),
    BulletList([[Plain([Str("x")])], [Plain([Str("y")])]]),
  ]);
}

test("filters modify, replace, splice and delete", () => {
  const f: Filter = {
    Header: (h) => { h.level += 1; },
    Str: (s) => {
      if (s.text === "a") return Str("A");
      if (s.text === "b") return [Str("b1"), Space(), Str("b2")];
      if (s.text === "x") return [];
    },
  };
  const d = applyFilter(doc(), f);
  assert.equal((d.blocks[0] as { level: number }).level, 2);
  assert.equal(stringify(d.blocks[1]), "A b1 b2");
  assert.deepEqual((d.blocks[2] as { content: unknown }).content, [[Plain()], [Plain([Str("y")])]]);
});

test("the constructor's function wins over its type's", () => {
  const seen: string[] = [];
  applyFilter(Pandoc([Para([Str("a"), Space()])]), {
    Inline: (x) => { seen.push(x.t); },
    Str: () => { seen.push("str"); },
  });
  assert.deepEqual(seen, ["str", "Space"]);
});

test("bottom-up and top-down", () => {
  for (const topDown of [false, true]) {
    const order: string[] = [];
    applyFilter(Pandoc([Para([Emph([Str("x")])])]), {
      topDown,
      Emph: () => { order.push("Emph"); },
      Str: () => { order.push("Str"); },
    });
    assert.deepEqual(order, topDown ? ["Emph", "Str"] : ["Str", "Emph"]);
  }
});

test("context", () => {
  let found: unknown;
  applyFilter(doc(), {
    Str: (s, ctx) => {
      if (s.text === "b") {
        found = { path: ctx.path, where: ctx.where, parent: (ctx.parent as { t: string }).t, index: ctx.index,
                  format: ctx.format, ancestors: ctx.ancestors.map((a) => (a as { t?: string }).t ?? "Pandoc") };
      }
    },
  }, "html");
  assert.deepEqual(found, {
    path: ["blocks", 1, "content", 2, "content", 0], where: "blocks[1].content[2].content[0]",
    parent: "Emph", index: 0, format: "html", ancestors: ["Pandoc", "Para", "Emph"],
  });
  const paths: string[] = [];
  applyFilter(doc(), { Str: (_s, ctx) => { paths.push(ctx.where); } });
  assert.ok(paths.includes("blocks[2].content[1][0].content[0]"), paths.join(" "));
});

test("errors in filter functions say where", () => {
  assert.throws(() => applyFilter(doc(), { Header: function broken() { throw new Error("boom"); } }),
                /boom\n {2}in filter function broken, on the Header at blocks\[0\]/);
});

test("JSON text round trip, and serialize checks", () => {
  const d = doc();
  assert.deepEqual(parse(serialize(d)), d);
  (d.blocks[1] as { content: unknown[] }).content.push(Para());
  assert.throws(() => serialize(d), /Pandoc\.blocks\[1\]\.content\[4\]: expected Inline, got Para \(a Block\)/);
});

test("stringify and metadata", () => {
  const p = Para([Str("a"), Space(), Quoted("DoubleQuote", [Str("q")]), Code("c"), Note([Para([Str("n")])])]);
  assert.equal(stringify(p), "a “q”c");
  const meta = fromPlain({ draft: true, tags: ["a"], n: 3 });
  assert.deepEqual(toPlain(meta), { draft: true, tags: ["a"], n: "3" });
});

test("structuredClone keeps documents intact (for workers)", () => {
  const d = doc();
  assert.deepEqual(structuredClone(d), d);
});
