# panir (Rust)

pandoc's document AST, generated from pandoc-types: types that serde
encodes as pandoc's JSON, and a `VisitMut` trait to change documents.

```rust
use panir::{walk_inline, Inline, VisitMut};

struct Upper;

impl VisitMut for Upper {
    fn visit_inline(&mut self, x: &mut Inline) {
        walk_inline(self, x); // children first
        if let Inline::Str(s) = x {
            *s = s.to_uppercase();
        }
    }
}

fn main() {
    // pandoc --filter ./upper
    panir::filter(|doc, _format| doc.visit(&mut Upper));
}
```

- A sum type is an enum: a constructor without fields is a unit variant
  (`Inline::Space`), with one field it holds the value
  (`Inline::Str(String)`, `Block::Para(Vec<Inline>)`), with more a struct of
  the same name with named fields (`Block::Header(Header { level, attr,
  content })`).
- Products are structs (`Attr { identifier, classes, attributes }`), with
  `Default` where pandoc's Lua constructors have defaults.
- `VisitMut` has a method per type, and `visit_blocks`/`visit_inlines` for
  whole lists (to splice or remove). Each default visits the children
  through the `walk_*` function of the same name.
- Strings convert as in pandoc's Lua: `inlines("hello world")` is its words
  and spaces, `blocks("...")` `Plain` text, and `"x".into()` is a `Str`
  where one inline goes, `Plain` text where one block goes.
- `from_str`/`to_string` for documents; `from_str` checks the
  `pandoc-api-version` and reports the path of JSON it can't read.

Decoding errors give the exact path in the JSON, plus line and column:

```
meta.author.c[0].c[2].c[2].c: invalid type: integer `42`, expected a string at line 1 column 244
```

(serde's derived adjacently tagged enums lose the path inside `"c"`, so the
sum types' `Deserialize` is generated: it reads `"t"`, then decodes `"c"` in
place.)

Status: a prototype.
