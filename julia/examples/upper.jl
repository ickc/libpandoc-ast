#!/usr/bin/env julia
# A pandoc filter: upper-case all text outside code.
#
#     pandoc --filter ./upper.jl input.md

using Panir

upper(s::Str) = Str(uppercase(s.text))

run_filter(upper)
