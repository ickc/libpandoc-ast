using Pandom
using Pandom: fromjson, tojson, parse, serialize
using JSON
using Test

const CORPUS = joinpath(@__DIR__, "..", "..", "corpus")
# split on "\n" only: strings may hold other line separators
corpus(name) = [JSON.parse(l) for l in split(read(joinpath(CORPUS, name), String), '\n') if !isempty(l)]

# compare parsed JSON regardless of the parser's container types
norm(x::AbstractDict) = Dict(String(k) => norm(v) for (k, v) in x)
norm(x::AbstractVector) = Any[norm(v) for v in x]
norm(x) = x

@testset "corpus" begin
    @testset "round trip" begin
        for (i, j) in enumerate([corpus("arbitrary.jsonl"); corpus("pandoc.jsonl")])
            @test norm(tojson(fromjson(j))) == norm(j)
        end
    end
    @testset "invalid: $(c["name"])" for c in corpus("invalid.jsonl")
        err = try
            fromjson(c["document"])
            nothing
        catch e
            e
        end
        @test err isa ASTDecodeError
        # field names are Symbols, map keys Strings
        err isa ASTDecodeError &&
            @test Any[p isa Symbol ? String(p) : p for p in err.path] == [p isa Integer ? Int(p) : String(p) for p in c["path"]]
    end
end

@testset "constructors" begin
    h = Header(1, Str("Hi"); identifier = "hi", classes = ["x"])
    @test h.level == 1 && h.attr == Attr("hi", ["x"], Tuple{String, String}[]) && h.content == [Str("Hi")]
    @test Div(; attributes = Dict("k" => "v")).attr.attributes == [("k", "v")]
    @test OrderedList([Plain(Str("a"))]; start = 3).list_attributes.start == 3
    @test OrderedList().list_attributes == ListAttributes(1, DefaultStyle, DefaultDelim)
    @test Cell(Para()).row_span == 1
    @test Link(Str("x"); url = "u").target == Target("u", "")
    @test_throws ArgumentError Link(Str("x"))
    @test_throws ArgumentError Code("x"; attr = Attr(), identifier = "y")
end

@testset "Julia checks types" begin
    p = Para(Str("a"))
    @test_throws MethodError push!(p.content, Para())
    @test_throws MethodError (p.content = "x")
    h = Header(1)
    @test_throws MethodError (h.level = "2")
    @test_throws MethodError Para(Para())
end

doc() = Pandoc(
    Header(1, Str("Title")),
    Para(Str("a"), Space(), Emph(Str("b")), Note(Para(Str("n")))),
    BulletList([Plain(Str("x"))], [Plain(Str("y"))]),
)

@testset "walk!" begin
    d = walk!(doc()) do x
        if x isa Header
            x.level += 1
        end
        nothing
    end
    @test d.blocks[1].level == 2

    act(x) = nothing
    act(s::Str) = s.text == "a" ? Str("A") : s.text == "b" ? Inline[Str("b1"), Space(), Str("b2")] :
                  s.text == "x" ? Inline[] : nothing
    d = walk!(act, doc())
    @test stringify(d.blocks[2]) == "A b1 b2"
    @test d.blocks[3].content[1] == Block[Plain()]

    # dispatch: the most specific method
    seen = String[]
    f(x::Inline) = (push!(seen, string(nameof(typeof(x)))); nothing)
    f(x::Str) = (push!(seen, "str"); nothing)
    walk!(f, Pandoc(Para(Str("a"), Space())))
    @test seen == ["str", "Space"]

    for topdown in (false, true)
        order = String[]
        g(x::Union{Emph, Str}) = (push!(order, string(nameof(typeof(x)))); nothing)
        walk!(g, Pandoc(Para(Emph(Str("x")))); topdown)
        @test order == (topdown ? ["Emph", "Str"] : ["Str", "Emph"])
    end

    found = Ref{Any}()
    where_(s::Str, ctx) = (s.text == "b" && (found[] = ctx); nothing)
    walk!(where_, doc(); format = "html")
    ctx = found[]
    @test ctx.path == Any[:blocks, 1, :content, 2, :content, 0]
    @test ctx.parent isa Emph && ctx.index == 0 && ctx.format == "html"
end

@testset "JSON text, stringify" begin
    d = doc()
    @test parse(serialize(d)) == d
    q = Para(Str("a"), Space(), Quoted(DoubleQuote, Str("q")), Code("c"), Note(Para(Str("n"))))
    @test stringify(q) == "a “q”c"
end
