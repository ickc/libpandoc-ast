-- Top-down, a list's function runs before its elements' and can skip
-- them: lists of inlines are reversed, except those of one element,
-- which are left as they are and not walked further; Str is upper-cased
-- in the others.
return {{
  traverse = "topdown",
  Inlines = function(xs)
    if #xs == 1 then return nil, false end
    local r = pandoc.Inlines{}
    for i = #xs, 1, -1 do r:insert(xs[i]) end
    return r
  end,
  Str = function(s) return pandoc.Str(s.text:upper()) end,
}}
