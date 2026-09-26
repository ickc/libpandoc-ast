# libpandoc-ast (TypeScript)

pandoc's document AST for TypeScript and JavaScript, in the browser or in
Node.js, generated from pandoc-types: types, pandoc's JSON, checks with
useful errors, and filters in the style of pandoc's Lua filters.

```ts
import { applyFilter, Header, parse, serialize, Str } from "libpandoc-ast";

const doc = parse(json); // pandoc's JSON, checked
applyFilter(doc, {
  Header: (h) => { h.level += 1; },
  Str: (s) => (s.text === "TODO" ? Str("DONE") : undefined),
});
serialize(doc);
```

As a pandoc filter (`pandoc --filter ./upper.mjs`):

```js
#!/usr/bin/env node
import { Str } from "libpandoc-ast";
import { runFilter } from "libpandoc-ast/node";

await runFilter({ Str: (s) => Str(s.text.toUpperCase()) });
```

## Nodes

Plain objects with named fields, discriminated by `t`, so `switch (x.t)`
narrows them, and `structuredClone` or `postMessage` carries them to a
worker:

```ts
{ t: "Header", level: 1, attr: { identifier: "hi", classes: [], attributes: [] },
  content: [{ t: "Str", text: "Hi" }] }
```

Field names are pandoc-types', in camelCase, as in pandoc's Lua API.
Products have no `t` (`Attr`, `Cell`, `Citation`, ...); enum-like types are
string unions (`"InlineMath"`).

Constructors take the required fields, then the content, then options:
`Header(1, [Str("Hi")], { identifier: "hi" })`, `Link([Str("x")], { url })`,
`Cell([Para([Str("a")])], { colSpan: 2 })`. They fill in defaults, and check
their arguments:

```
ASTTypeError: Para.content[0]: expected Inline, got Para (a Block)
```

`parse`/`fromJSON` report where JSON is wrong
(`blocks[0].content[1].text: expected a string, got 42`), and
`serialize`/`toJSON` check a document on the way out.

## Filters

An object of functions by constructor (`Str`, `Header`), type (`Inline`,
`Block`, `MetaValue`) or product (`Cell`, `Pandoc`); a node gets its
constructor's, or else its type's. A function returns nothing to keep the
node (changed in place or not), a node to replace it, or an array to splice
in its place (`[]` deletes it). Its second argument is the node's
`Context`: `parent`, `index`, `next`/`prev`, `path`, `doc`, `format`.
Bottom-up by default; `topDown: true` for the other way.

Also: `walk`, `stringify`, `toPlain`/`fromPlain` for metadata.

Status: a prototype.
