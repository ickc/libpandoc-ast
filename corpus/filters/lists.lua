-- Functions on whole lists, after (typewise) their elements' functions:
-- every list of inlines loses its spaces and gets a marker at its end;
-- every list of blocks gets a rule after each header.
-- stateless: the same with traverse = "bottomup"
return {{
  Inlines = function(xs)
    local out = pandoc.Inlines{}
    for _, x in ipairs(xs) do
      if x.t ~= "Space" then out:insert(x) end
    end
    out:insert(pandoc.Str("<" .. #xs .. ">"))
    return out
  end,
  Blocks = function(bs)
    local out = pandoc.Blocks{}
    for _, b in ipairs(bs) do
      out:insert(b)
      if b.t == "Header" then out:insert(pandoc.HorizontalRule()) end
    end
    return out
  end,
}}
