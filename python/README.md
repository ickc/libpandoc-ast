# pandom

pandoc's document AST in Python, generated from pandoc-types: checked types,
pandoc's JSON, and filters that run under `pandoc --filter` or in-process
with [libpandoc](https://github.com/ickc/libpandoc-python).

```python
from pandom import Filter, Header, Str

f = Filter()


@f.on(Header)
def demote(h: Header) -> None:
    h.level += 1


if __name__ == "__main__":
    f.main()  # pandoc --filter ./demote.py
```

## The AST

One class per pandoc constructor, a subclass of its type: `Para` and `Header`
are `Block`s, `Str` and `Emph` are `Inline`s. Fields have pandoc-types' names
and order, as in pandoc's Lua API: `Header(level, *content, attr=...)`.

```python
>>> from pandom import *
>>> h = Header(1, Str("Intro"), identifier="intro")
>>> h
Header(1, Str('Intro'), identifier='intro')
>>> h.attr
Attr('intro')
>>> match h:
...     case Header(1, _, [Str(text)]):
...         print(text)
Intro
```

- Constructors take the content as arguments (`Para(Str("a"), Space(),
  Str("b"))`), attributes by name (`identifier=`, `classes=`, `attributes=`,
  or `attr=` whole), a link's target by name (`url=`, `title=`).
- `repr` is constructor syntax that evaluates to an equal value.
- Enum-like types (`MathType`, `Alignment`, ...) are enums; their names are
  accepted too: `Math("InlineMath", "x")`.
- Metadata converts from plain values: `doc.meta["draft"] = True`.

## Checked where you make the mistake

Everything put into a node, a list or a map of the AST is checked, and the
error says where and what:

```python
>>> p = Para(Str("a"))
>>> p.content.append(Para())
ASTTypeError: Para.content[1]: expected Inline, got Para (a Block)
>>> p.content[0] = "a"
ASTTypeError: Para.content[0]: expected Inline, got str 'a' (did you mean Str('a')?)
```

Reading JSON reports the path of what's wrong:

```python
ASTDecodeError: blocks[0].content[1].text: expected a string, got 42
```

Type checkers read the same declarations: pyright reports `h.level = "2"`
and `Para(Header(1))`.

## Filters

A function per node type, which returns `None` to keep the node (changed in
place or not), a node to replace it, or a list to splice in its place (`[]`
deletes it). A second parameter, if the function has one, is the
node's `Context`: its `parent`, `index`, `next`/`prev` siblings, `path`, the
`doc`, and the output `format`.

```python
@f.on(Str)
def shout(s, ctx):
    if ctx.format == "html":
        return Strong(Str(s.text.upper()))
```

Each node gets the function for its class, or else for its closest base
class (`Inline`, `Block`, ...). The walk is bottom-up (`Filter(top_down=True)`
for the other way). An exception in a function is annotated with the
function and the node's path.

`f.main()` runs a filter under pandoc; `f(doc)` on a document; `run(doc,
[f, g])` several in turn. `walk(node, action)` is the walk underneath.

Also: `loads`/`dumps`/`load`/`dump` for pandoc's JSON, `stringify`,
`to_python`/`from_python` for metadata.
