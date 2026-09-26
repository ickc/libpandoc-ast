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
end

"The neighbour of a node in its list, or `nothing`."
function sibling(ctx::Context, step::Integer)
    ctx.container isa AbstractVector && ctx.index isa Integer || return nothing
    i = ctx.index + 1 + step
    1 <= i <= length(ctx.container) ? ctx.container[i] : nothing
end

Base.show(io::IO, ctx::Context) =
    print(io, "Context(at ", _format_path(ctx.path), ", parent ", typeof(ctx.parent), ")")

mutable struct _Walker{F}
    f::F
    topdown::Bool
    doc::Any
    format::Union{Nothing, String}
    stack::Vector{Tuple{Any, Symbol, Any, Any, Vector{Any}}}  # parent, field, container, index, path
end

function _call(w::_Walker, x)
    parent, field, container, index, path = isempty(w.stack) ? (nothing, :_, nothing, nothing, Any[]) : w.stack[end]
    ctx = Context(parent, isempty(w.stack) ? nothing : field, container, index, copy(path), w.doc, w.format)
    if applicable(w.f, x, ctx)
        w.f(x, ctx)
    elseif applicable(w.f, x)
        w.f(x)
    else
        nothing
    end
end

function _one(w::_Walker, x::Node)
    if w.topdown
        r = _call(w, x)
        r === nothing || (r isa Node ? (x = r) : throw(ArgumentError(
            "a filter returned $(typeof(r)) where one node belongs")))
        _children(w, x)
        return x
    end
    _children(w, x)
    r = _call(w, x)
    r === nothing && return x
    r isa Node || throw(ArgumentError("a filter returned $(typeof(r)) where one node belongs"))
    r
end

function _many(w::_Walker, list::Vector{T}, parent, field, path) where {T <: Node}
    i = 1
    while i <= length(list)
        push!(w.stack, (parent, field, list, i - 1, Any[path..., i - 1]))
        try
            w.topdown || _children(w, list[i])
            r = _call(w, list[i])
            if r === nothing
                w.topdown && _children(w, list[i])
                i += 1
                continue
            end
            items = r isa Node ? T[r] : convert(Vector{T}, r)
            splice!(list, i, items)
            if w.topdown
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
        for k in collect(keys(x))
            z = _value(w, x[k], parent, field, Any[path..., k])
            z === x[k] || (x[k] = z)
        end
    elseif x isa Tuple
        ys = Any[_value(w, y, parent, field, Any[path..., i - 1]) for (i, y) in enumerate(x)]
        all(ys[i] === x[i] for i in eachindex(ys)) || return typeof(x)(Tuple(ys))
    end
    x
end

function _children(w::_Walker, x::T) where {T <: Node}
    for f in fieldnames(T)
        v = getfield(x, f)
        v isa Union{Node, Vector, Dict, Tuple} || continue
        z = _value(w, v, x, f, isempty(w.stack) ? Any[f] : Any[w.stack[end][5]..., f])
        z === v || setfield!(x, f, z)
    end
end

"""
    walk!(f, node; topdown = false, format = nothing)

Call `f(x, ctx)` (or `f(x)`) on `node` and every node in it, where `f` has
a method for `x`: define methods for the node types to change, and the
most specific one is called, as Julia dispatches. Bottom-up by default.
`f` returns `nothing` to keep the node (changed in place or not), a node to
replace it, or, in a list, a vector of nodes to splice in its place (empty:
delete). Returns `node` or its replacement.

```julia
demote(h::Header) = (h.level += 1; nothing)
shout(s::Str, ctx) = ctx.format == "html" ? Strong(Str(uppercase(s.text))) : nothing
walk!(demote, doc)
```
"""
function walk!(f, node::Node; topdown::Bool = false, format = nothing)
    w = _Walker(f, topdown, node, format === nothing ? nothing : String(format),
                Tuple{Any, Symbol, Any, Any, Vector{Any}}[])
    _one(w, node)
end

"""
    run_filter(f)

Run `f` (as in `walk!`) as a pandoc JSON filter: a document on stdin, to
stdout. pandoc's first argument, the output format, is `ctx.format`.
"""
function run_filter(f; topdown::Bool = false)
    doc = parse(read(stdin, String))
    doc = walk!(f, doc; topdown, format = isempty(ARGS) ? nothing : ARGS[1])
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
