-- Delete and splice: notes and emphasis go (an empty list), strong
-- inlines and divs are replaced by their contents, and a horizontal rule
-- becomes two paragraphs.
-- stateless: the same with traverse = "bottomup"
return {{
  Note = function() return {} end,
  Emph = function() return {} end,
  Strong = function(s) return s.content end,
  Div = function(d) return d.content end,
  HorizontalRule = function() return {pandoc.Para{pandoc.Str("one")}, pandoc.Para{pandoc.Str("two")}} end,
}}
