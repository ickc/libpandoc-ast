# Panir.jl

pandoc's document AST for Julia, generated from pandoc-types: types,
pandoc's JSON, and filters as methods.

```julia
#!/usr/bin/env julia
# pandoc --filter ./upper.jl
using Panir

upper(s::Str) = Str(uppercase(s.text))
demote(h::Header) = (h.level += 1; nothing)

run_filter(upper)
```

- A sum type is an abstract type (`Inline`, `Block`, `MetaValue`), each
  constructor a mutable struct subtyping it (`Str <: Inline`); products are
  structs (`Attr`, `Cell`, `Pandoc`); enum-like types are `@enum`s
  (`InlineMath`).
- Julia checks field types itself: `push!(para.content, Para())` and
  `h.level = "2"` are errors.
- Constructors: every field positionally (`Header(1, Attr(), Inline[])`),
  or the content as arguments with the rest as keywords:
  `Header(1, Str("Hi"); identifier = "hi")`, `Link(Str("x"); url = "u")`.
- Strings convert as in pandoc's Lua: where a list of inlines goes, a string
  is its words and spaces (`Para("hello world")`, `h.content = "Intro"`);
  where one inline goes, a `Str` (`push!(p.content, "x")`, `Para("a", Emph("b"))`);
  where blocks go, `Plain` text. `inlines("...")` and `blocks("...")` build
  such lists.
- `walk!(f, doc)` calls `f(x, ctx)` or `f(x)` wherever `f` has a method for
  `x`, so the most specific method wins, by dispatch. Return `nothing` to
  keep a node, a node to replace it, or a vector to splice in its place.
  `ctx` is a `Context`: `parent`, `field`, `index`, `path`, `doc`, `format`.
- `Panir.parse`/`serialize` for pandoc's JSON; parsing reports where
  JSON is wrong (`ASTDecodeError`). `stringify` for text.

Status: a prototype.
