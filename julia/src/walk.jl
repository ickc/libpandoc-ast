# Walking a document, and filters as functions with a method per node type.

"""
Where a node is, for a filter method that takes it: `parent` (the node whose
field holds it), `field`, `index` in that field's list (or key, in a map),
`container` (that list), `path` from the document, `doc`, `format`.
"""
struct Context
    parent::Any
    field::Union{Nothing, Symbol}
    container::Any
    index::Any
    path::Vector{Any}
    doc::Any
    format::Union{Nothing, String}
    topdown::Bool
    skip::Base.RefValue{Bool}
end

"The neighbour of a node in its list, or `nothing`."
function sibling(ctx::Context, step::Integer)
    ctx.container isa AbstractVector && ctx.index isa Integer || return nothing
    i = ctx.index + 1 + step
    1 <= i <= length(ctx.container) ? ctx.container[i] : nothing
end

"""
    skip_children!(ctx)

Don't walk the node's children, or its replacement's (Lua's `return el,
false`). Only with `traverse = :topdown`: otherwise the children were walked
first.
"""
function skip_children!(ctx::Context)
    ctx.topdown || throw(ArgumentError(
        "skip_children! needs traverse = :topdown (otherwise the children were walked first)"))
    ctx.skip[] = true
    nothing
end

Base.show(io::IO, ctx::Context) =
    print(io, "Context(at ", _format_path(ctx.path), ", parent ", typeof(ctx.parent), ")")

const _Frame = Tuple{Any, Symbol, Any, Any, Vector{Any}}  # parent, field, container, index, path

# Not parametric on the filter: the call into it is dynamic anyway (a method
# per node type), and one walker compiled once serves every filter.
mutable struct _Walker
    f::Any
    topdown::Bool
    doc::Any
    format::Union{Nothing, String}
    stack::Vector{_Frame}
    wants::Any   # which nodes this walk calls `f` on
    lists::Any   # which lists
end

function _context(w::_Walker)
    parent, field, container, index, path = isempty(w.stack) ? (nothing, :_, nothing, nothing, Any[]) : w.stack[end]
    Context(parent, isempty(w.stack) ? nothing : field, container, index, copy(path), w.doc, w.format,
            w.topdown, Ref(false))
end

# `f` on `x` (with the context if it has such a method); the result, and
# whether to skip the children
function _call(w::_Walker, x)
    w.wants(x) || return nothing, false
    ctx = _context(w)
    r = if applicable(w.f, x, ctx)
        w.f(x, ctx)
    elseif applicable(w.f, x)
        w.f(x)
    else
        nothing
    end
    r, ctx.skip[]
end

# Whether `f` has a method for `x` itself, not only one for anything: lists
# and the metadata are values any method would take.
function _specific(f, x)
    for args in (Tuple{typeof(x), Context}, Tuple{typeof(x)})
        hasmethod(f, args) || continue
        sig = Base.unwrap_unionall(which(f, args).sig)
        sig.parameters[2] === Any || return true
    end
    false
end

# `f` on a list or the metadata, if it has a method for it: the result, and
# whether to skip what is in it
function _call_whole(w::_Walker, x)
    _specific(w.f, x) || return nothing, false
    ctx = _context(w)
    r = applicable(w.f, x, ctx) ? w.f(x, ctx) : w.f(x)
    r, ctx.skip[]
end

function _one(w::_Walker, x::Node)
    if w.topdown
        r, skip = _call(w, x)
        r === nothing || (r isa Node ? (x = r) : throw(ArgumentError(
            "a filter returned $(typeof(r)) where one node belongs")))
        skip || _children(w, x)
        return x
    end
    _children(w, x)
    r, _ = _call(w, x)
    r === nothing && return x
    r isa Node || throw(ArgumentError("a filter returned $(typeof(r)) where one node belongs"))
    r
end

# The list function on `list`, replacing what is in it; whether to skip its elements.
function _whole(w::_Walker, list::Vector, parent, field, path)
    w.lists(list) || return false
    push!(w.stack, (parent, field, nothing, nothing, path))
    try
        r, skip = _call_whole(w, list)
        if r !== nothing && r !== list
            r isa AbstractVector || throw(ArgumentError(
                "a filter returned $(typeof(r)) for a list of $(eltype(list))s"))
            items = convert(Vector{eltype(list)}, collect(r))
            empty!(list)
            append!(list, items)
        end
        skip
    finally
        pop!(w.stack)
    end
end

function _many(w::_Walker, list::Vector{T}, parent, field, path) where {T <: Node}
    w.topdown && _whole(w, list, parent, field, path) && return
    i = 1
    while i <= length(list)
        push!(w.stack, (parent, field, list, i - 1, Any[path..., i - 1]))
        try
            w.topdown || _children(w, list[i])
            r, skip = _call(w, list[i])
            if r === nothing
                w.topdown && !skip && _children(w, list[i])
                i += 1
                continue
            end
            items = r isa Node ? T[r] : convert(Vector{T}, r)
            splice!(list, i, items)
            if w.topdown && !skip
                for k in 0:length(items) - 1
                    w.stack[end] = (parent, field, list, i - 1 + k, Any[path..., i - 1 + k])
                    _children(w, list[i + k])
                end
            end
            i += length(items)
        finally
            pop!(w.stack)
        end
    end
    w.topdown || _whole(w, list, parent, field, path)
    nothing
end

function _value(w::_Walker, x, parent, field, path)
    if x isa Node
        push!(w.stack, (parent, field, nothing, nothing, path))
        try
            return _one(w, x)
        finally
            pop!(w.stack)
        end
    elseif x isa Vector{<:Node}
        _many(w, x, parent, field, path)
    elseif x isa Vector
        for (i, y) in enumerate(x)
            z = _value(w, y, parent, field, Any[path..., i - 1])
            z === y || (x[i] = z)
        end
    elseif x isa Dict
        for k in sort!(collect(keys(x)))  # in key order, as pandoc's Map
            z = _value(w, x[k], parent, field, Any[path..., k])
            z === x[k] || (x[k] = z)
        end
    elseif x isa Tuple
        ys = Any[_value(w, y, parent, field, Any[path..., i - 1]) for (i, y) in enumerate(x)]
        all(ys[i] === x[i] for i in eachindex(ys)) || return typeof(x)(Tuple(ys))
    end
    x
end

function _children(w::_Walker, x::T; skip::Union{Nothing, Symbol} = nothing,
                   after::Union{Nothing, Symbol} = nothing, then = nothing) where {T <: Node}
    for f in fieldnames(T)
        f === skip && continue
        v = getfield(x, f)
        if v isa Union{Node, Vector, Dict, Tuple}
            z = _value(w, v, x, f, isempty(w.stack) ? Any[f] : Any[w.stack[end][5]..., f])
            z === v || setfield!(x, f, z)
        end
        f === after && then(x)
    end
end

# Whether `f` has a method for some node of type `T`.
_handles(f, T) = any(methods(f)) do m
    ps = Base.unwrap_unionall(m.sig).parameters
    length(ps) >= 2 && typeintersect(ps[2], T) !== Union{}
end

# Whether `f` has a method for a node that isn't an Inline, a Block or the document.
_handles_other(f) = any(methods(f)) do m
    ps = Base.unwrap_unionall(m.sig).parameters
    length(ps) >= 2 && typeintersect(ps[2], Node) !== Union{} && !(ps[2] <: Union{Inline, Block, Pandoc})
end

_isnot(T...) = x -> !any(t -> x isa t, T)

"""
    walk!(f, node; traverse = :typewise, format = nothing)

Call `f(x, ctx)` (or `f(x)`) on `node` and every node in it, where `f` has
a method for `x`: define methods for the node types to change, and the
most specific one is called, as Julia dispatches. `f` returns `nothing` to
keep the node (changed in place or not), a node to replace it, or, in a
list, a vector of nodes to splice in its place (empty: delete). As in
pandoc's Lua filters, a method for `Vector{Inline}` or `Vector{Block}` is
called on every list of them, and one for `Panir.Meta` on the metadata
(methods for anything don't count; `Meta` alone is `Base.Meta` outside
`Panir`); each returns a replacement, or `nothing`.

`traverse` is the order:
- `:typewise` (the default, as pandoc's Lua filters and Haskell's `walk`):
  one walk per kind, each bottom-up: every `Inline`, then every list of
  inlines, then every `Block`, then every list of blocks, then the other
  nodes, then the metadata, then `Pandoc`.
- `:topdown` (Lua's other order, and pandocfilters'): `Pandoc`, the
  metadata, then from the root down, a list before its elements and a node
  before its children, which are walked in its replacement too, unless the
  method calls `skip_children!(ctx)`.
- `:bottomup` (panflute's): one walk, each node after its children, a list
  after its elements, the metadata after what is in it, `Pandoc` last.

Returns `node` or its replacement.

```julia
demote(h::Header) = (h.level += 1; nothing)
shout(s::Str, ctx) = ctx.format == "html" ? Strong(Str(uppercase(s.text))) : nothing
walk!(demote, doc)
```
"""
function walk!(f, node::Node; traverse::Symbol = :typewise, format = nothing)
    traverse in (:typewise, :topdown, :bottomup) || throw(ArgumentError(
        "traverse: expected :typewise, :topdown or :bottomup, got $(repr(traverse))"))
    fmt = format === nothing ? nothing : String(format)
    topdown = traverse === :topdown
    walker(wants, lists) = _Walker(f, topdown, node, fmt, _Frame[], wants, lists)
    anylist = _ -> true
    nolist = _ -> false
    node isa Pandoc || return traverse === :typewise ?
        foldl((x, (wants, lists)) -> _one(walker(wants, lists), x), _passes(f); init = node) :
        _one(walker(_ -> true, anylist), node)
    doc = node
    function root(d)
        r, skip = _call(walker(_ -> true, nolist), d)
        r === nothing && return d, skip
        r isa Pandoc || throw(ArgumentError("a filter returned $(typeof(r)) for the Pandoc"))
        r, skip
    end
    function meta(d)
        w = walker(_ -> true, nolist)
        push!(w.stack, (d, :meta, nothing, nothing, Any[:meta]))
        r, skip = _call_whole(w, d.meta)
        r === nothing || (d.meta = r)
        skip
    end
    if topdown
        doc, skip = root(doc)
        skip && return doc
        skipmeta = meta(doc)
        _children(walker(_isnot(Pandoc), anylist), doc; skip = skipmeta ? :meta : nothing)
        return doc
    end
    if traverse === :bottomup
        _children(walker(_isnot(Pandoc), anylist), doc; after = :meta, then = meta)
        return first(root(doc))
    end
    for (wants, lists) in _passes(f)
        _children(walker(wants, lists), doc)
    end
    meta(doc)
    first(root(doc))
end

# The typewise walks `f` needs: which nodes, and which lists, each calls it on.
function _passes(f)
    none = _ -> false
    passes = [
        (x -> x isa Inline, none, _handles(f, Inline)),
        (none, x -> x isa Vector{Inline}, _handles(f, Vector{Inline})),
        (x -> x isa Block, none, _handles(f, Block)),
        (none, x -> x isa Vector{Block}, _handles(f, Vector{Block})),
        (_isnot(Inline, Block, Pandoc), none, _handles_other(f)),
    ]
    [(wants, lists) for (wants, lists, needed) in passes if needed]
end

"""
    run_filter(f; traverse = :typewise)

Run `f` (as in `walk!`) as a pandoc JSON filter: a document on stdin, to
stdout. pandoc's first argument, the output format, is `ctx.format`.
"""
function run_filter(f; traverse::Symbol = :typewise)
    doc = parse(read(stdin, String))
    doc = walk!(f, doc; traverse, format = isempty(ARGS) ? nothing : ARGS[1])
    write(stdout, serialize(doc))
    nothing
end

const _QUOTES = Dict(SingleQuote => ("‘", "’"), DoubleQuote => ("“", "”"))

"""
The text of a node or nodes, without markup, as pandoc's `stringify`.
"""
stringify(x) = (io = IOBuffer(); _text(io, x); String(take!(io)))

_text(io, x::AbstractVector) = foreach(y -> _text(io, y), x)
_text(io, x::Tuple) = foreach(y -> _text(io, y), x)
_text(io, x::AbstractDict) = foreach(y -> _text(io, y), values(x))
_text(io, x) = nothing
_text(io, x::Union{Str, Code, Math, MetaString}) = print(io, x.text)
_text(io, ::Union{Space, SoftBreak, LineBreak}) = print(io, " ")
_text(io, x::RawInline) = x.format == "html" && startswith(x.text, "<br") && print(io, " ")
_text(io, ::Note) = nothing
_text(io, x::Cite) = _text(io, x.content)
_text(io, x::MetaBool) = print(io, x.value ? "true" : "false")
function _text(io, x::Quoted)
    l, r = _QUOTES[x.quote_type]
    print(io, l); _text(io, x.content); print(io, r)
end
function _text(io, x::T) where {T <: Node}
    for f in fieldnames(T)
        f === :attr || _text(io, getfield(x, f))
    end
end
