"""
pandoc's document AST, generated from pandoc-types: types, pandoc's JSON,
walking and filters.

```julia
using LibPandocAST
doc = LibPandocAST.parse(json)                 # checked
upper(s::Str, ctx) = Str(uppercase(s.text))    # a method per node type
walk!(upper, doc)
LibPandocAST.serialize(doc)
```
"""
module LibPandocAST

import JSON

"Any node of pandoc's AST: a constructor (`Str`, `Para`, ...) or a product (`Attr`, ...)."
abstract type Node end

include("generated.jl")
include("core.jl")
include("walk.jl")

export Node, ASTDecodeError, Context, walk!, run_filter, stringify

end
