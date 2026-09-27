-- Replace a node: every Str, wherever it is (metadata, notes, table
-- cells, captions, citation prefixes), by an upper-cased one.
-- stateless: the same with traverse = "bottomup"
return {{
  Str = function(s) return pandoc.Str(s.text:upper()) end,
}}
