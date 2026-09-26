# libpandoc-ast (Rust)

pandoc's document AST, generated from pandoc-types: types that serde
encodes as pandoc's JSON, and a `VisitMut` trait to change documents.

```rust
use libpandoc_ast::{walk_inline, Inline, VisitMut};

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
    libpandoc_ast::filter(|doc, _format| doc.visit(&mut Upper));
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
- `from_str`/`to_string` for documents; `from_str` checks the
  `pandoc-api-version` and reports the path of JSON it can't read.

Status: a prototype. Decoding errors give the path down to the innermost
tagged value (serde buffers adjacently tagged enums), plus line and column.
