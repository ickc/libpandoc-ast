-- A type's function (Inline, Block) applies where no constructor's
-- function does: the constructor's wins.
-- stateless: the same with traverse = "bottomup"
return {{
  Str = function(s) return pandoc.Str(s.text .. "!") end,
  Inline = function(i)
    if i.t == "Str" then return pandoc.Str("never") end
    if i.t == "Code" then return pandoc.Str(i.text) end
  end,
  Block = function(b)
    if b.t == "CodeBlock" then return pandoc.Para{pandoc.Str(b.text)} end
  end,
}}
