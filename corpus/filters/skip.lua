-- Top-down, what is below a node is walked after the node's function,
-- in its replacement if it has one, unless the function says to skip it
-- (Lua: return el, false). Here Str is upper-cased; headers become
-- paragraphs (their text still upper-cased), and nothing under a div,
-- a block quote or an emphasis is.
return {{
  traverse = "topdown",
  Str = function(s) return pandoc.Str(s.text:upper()) end,
  Header = function(h) return pandoc.Para(h.content) end,
  Div = function(d) return d, false end,
  BlockQuote = function(q) return pandoc.Div(q.content), false end,
  Emph = function(e) return nil, false end,
}}
