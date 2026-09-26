# The generic part: everything that isn't a declaration (generated.jl).
# JSON by reflection on the declared field types; nothing here names a
# pandoc type.

"""
JSON that isn't a pandoc document (or node) of this API version. `path` is
where, in field names and indices, e.g. `["blocks", 0, "content", 3]`.
"""
struct ASTDecodeError <: Exception
    path::Vector{Any}
    expected::String
    got::String
end

function _format_path(path)
    out = ""
    for p in path
        if p isa Integer
            out *= "[$p]"
        elseif occursin(r"^[A-Za-z_][A-Za-z0-9_]*$", string(p)) || isempty(out)
            out *= isempty(out) ? string(p) : ".$p"
        else
            out *= "[$(repr(string(p)))]"
        end
    end
    out
end

function Base.showerror(io::IO, e::ASTDecodeError)
    where = _format_path(e.path)
    print(io, isempty(where) ? "" : "$where: ", "expected $(e.expected), got $(e.got)")
end

# raised while decoding; the path is collected on the way up
mutable struct _Bad <: Exception
    expected::String
    got::Any
    got_text::Union{Nothing, String}  # in place of describing `got`
    path::Vector{Any}
end
_Bad(expected, got, got_text = nothing) = _Bad(expected, got, got_text, Any[])

function _at(f, key)
    try
        f()
    catch e
        e isa _Bad && push!(e.path, key)
        rethrow()
    end
end

const _TAGS = Dict{String, Tuple{DataType, Type}}()  # constructor name => (struct, sum)

function _tags()
    if isempty(_TAGS)
        for S in _SUMS, C in _constructors(S)
            _TAGS[string(nameof(C))] = (C, S)
        end
    end
    _TAGS
end

_sumname(S) = replace(string(nameof(S)), r"Base$" => "")

function _describe(j)
    if j isa AbstractDict && get(j, "t", nothing) isa AbstractString
        t = j["t"]
        haskey(_tags(), t) || return "\"t\": $(repr(t)) (no such constructor)"
        s = _sumname(_tags()[t][2])
        return "$t ($(s[1] in "AEIOU" ? "an" : "a") $s)"
    end
    j === nothing && return "null"
    text = sprint(JSON.print, j)
    length(text) > 60 ? text[1:prevind(text, 58)] * "..." : text
end

_article(s) = (s[1] in "AEIOU" ? "an " : "a ") * s

_typename(::Type{String}) = "a string"
_typename(::Type{Int}) = "an integer"
_typename(::Type{Float64}) = "a number"
_typename(::Type{Bool}) = "a boolean"
_typename(::Type{<:Vector}) = "a list"
_typename(::Type{<:Dict}) = "an object"
_typename(T::Type{<:Tuple}) = "a list of $(fieldcount(T))"
_typename(T::Type) = T in _SUMS ? _sumname(T) : _article(string(nameof(T)))

# -- decoding ---------------------------------------------------------------------

_decode(::Type{String}, j) = j isa AbstractString ? String(j) : throw(_Bad("a string", j))
_decode(::Type{Int}, j) = j isa Integer && !(j isa Bool) ? Int(j) : throw(_Bad("an integer", j))
_decode(::Type{Float64}, j) = j isa Real && !(j isa Bool) ? Float64(j) : throw(_Bad("a number", j))
_decode(::Type{Bool}, j) = j isa Bool ? j : throw(_Bad("a boolean", j))

function _decode(::Type{Vector{T}}, j) where {T}
    j isa AbstractVector || throw(_Bad("a list", j))
    T[_at(() -> _decode(T, x), i - 1) for (i, x) in enumerate(j)]
end

function _decode(::Type{Dict{String, T}}, j) where {T}
    j isa AbstractDict || throw(_Bad("an object", j))
    Dict{String, T}(String(k) => _at(() -> _decode(T, x), String(k)) for (k, x) in j)
end

function _decode(::Type{Union{Nothing, T}}, j) where {T}
    j === nothing ? nothing : _decode(T, j)
end

function _decode(T::Type{<:Tuple}, j)
    n = fieldcount(T)
    j isa AbstractVector && length(j) == n || throw(_Bad("a list of $n", j))
    Tuple(_at(() -> _decode(fieldtype(T, i), j[i]), i - 1) for i in 1:n)
end

function _decode(T::Type{<:Enum}, j)
    if j isa AbstractDict && get(j, "t", nothing) isa AbstractString
        for v in instances(T)
            string(v) == j["t"] && return v
        end
    end
    throw(_Bad(_article(string(nameof(T))), j))
end

function _decode(T::Type{<:Node}, j)
    if isabstracttype(T)  # a sum type: the constructor from "t"
        t = j isa AbstractDict ? get(j, "t", nothing) : nothing
        entry = t isa AbstractString ? get(_tags(), t, nothing) : nothing
        (entry === nothing || entry[2] !== T) && throw(_Bad(_typename(T), j))
        C = entry[1]
        enc = _encoding(C)
        enc === :none && return C()
        haskey(j, "c") || throw(_Bad("$C with contents", j, "$C without"))
        return _decode_fields(C, enc, j["c"])
    end
    enc = _encoding(T)
    if enc === :root
        j isa AbstractDict || throw(_Bad("an object (Pandoc)", j))
        v = get(j, "pandoc-api-version", nothing)
        want = PANDOC_API_VERSION
        if !(v isa AbstractVector && length(v) >= 2 && v[1] == want[1] && v[2] == want[2])
            e = _Bad("pandoc-api-version $(want[1]).$(want[2]).*", v)
            push!(e.path, "pandoc-api-version")
            throw(e)
        end
    end
    _decode_fields(T, enc, j)
end

function _decode_fields(T, enc, c)
    names = fieldnames(T)
    n = length(names)
    if enc === :value
        return T(_at(() -> _decode(fieldtype(T, 1), c), names[1]))
    elseif enc === :array
        if !(c isa AbstractVector && length(c) == n)
            got = c isa AbstractVector ? "$T with $(length(c))" : _describe(c)
            throw(_Bad("$T with $n fields", c, got))
        end
        return T((_at(() -> _decode(fieldtype(T, i), c[i]), names[i]) for i in 1:n)...)
    end
    c isa AbstractDict || throw(_Bad("an object ($T)", c))
    keys = enc === :root ? string.(names) : _keys(T)
    vals = map(1:n) do i
        haskey(c, keys[i]) || throw(_Bad("$T with $(repr(keys[i]))", c, "one without"))
        _at(() -> _decode(fieldtype(T, i), c[keys[i]]), names[i])
    end
    T(vals...)
end

"""
    fromjson(T, j)

A value of type `T` (default: a document) from parsed pandoc JSON, checked.
Throws `ASTDecodeError` saying where it is wrong.
"""
function fromjson(T::Type, j)
    try
        _decode(T, j)
    catch e
        if e isa _Bad
            got = e.got_text === nothing ? _describe(e.got) : e.got_text
            throw(ASTDecodeError(reverse(e.path), e.expected, got))
        end
        rethrow()
    end
end
fromjson(j) = fromjson(Pandoc, j)

"A document from pandoc's JSON text."
parse(text::AbstractString) = fromjson(Pandoc, JSON.parse(text))

# -- encoding -----------------------------------------------------------------------

_encode(x::Union{String, Int, Float64, Bool, Nothing}) = x
_encode(x::Vector) = Any[_encode(y) for y in x]
_encode(x::Dict) = Dict{String, Any}(k => _encode(v) for (k, v) in x)
_encode(x::Tuple) = Any[_encode(y) for y in x]
_encode(x::Enum) = Dict{String, Any}("t" => string(x))

function _encode(x::T) where {T <: Node}
    enc = _encoding(T)
    vals = Any[_encode(getfield(x, f)) for f in fieldnames(T)]
    if supertype(T) in _SUMS
        enc === :none && return Dict{String, Any}("t" => string(nameof(T)))
        return Dict{String, Any}("t" => string(nameof(T)), "c" => enc === :value ? vals[1] : vals)
    end
    enc === :array && return vals
    enc === :value && return vals[1]
    keys = enc === :root ? string.(fieldnames(T)) : _keys(T)
    out = Dict{String, Any}(zip(keys, vals))
    enc === :root && (out["pandoc-api-version"] = collect(PANDOC_API_VERSION))
    out
end

"A value (a document, or any node) as parsed pandoc JSON."
tojson(x) = _encode(x)

"A document as pandoc's JSON text."
serialize(doc::Pandoc) = JSON.json(tojson(doc))

# -- nodes ----------------------------------------------------------------------------

function Base.:(==)(a::T, b::T) where {T <: Node}
    all(getfield(a, f) == getfield(b, f) for f in fieldnames(T))
end

function Base.hash(x::T, h::UInt) where {T <: Node}
    foldr((f, h) -> hash(getfield(x, f), h), fieldnames(T); init = hash(T, h))
end

function Base.copy(x::T) where {T <: Node}
    T((getfield(x, f) for f in fieldnames(T))...)
end

# A product field given whole (attr = ...) or by its parts (identifier = ...).
function _flat(::Type{P}, given, owner::Symbol, field::Symbol; parts...) where {P}
    names = fieldnames(P)
    if given === nothing
        missing_ = [n for n in names if parts[n] === nothing]
        isempty(missing_) || throw(ArgumentError(
            "$owner() needs $(join(string.(missing_) .* " =", ", ")) (or $field =)"))
        values = [_attributes(fieldtype(P, i), parts[n]) for (i, n) in enumerate(names)]
        return P(values...)
    end
    default = try
        P()
    catch
        nothing
    end
    changed = [n for n in names if parts[n] !== nothing &&
               (default === nothing || _attributes(fieldtype(P, findfirst(==(n), names)), parts[n]) != getfield(default, n))]
    isempty(changed) || throw(ArgumentError(
        "$owner(): give either $field = or $(join(string.(changed) .* " =", ", ")), not both"))
    given
end

# attributes may be given as a Dict
_attributes(::Type{Vector{Tuple{String, String}}}, x::AbstractDict) =
    Tuple{String, String}[(String(k), String(v)) for (k, v) in x]
_attributes(::Type, x) = x
