-- Typewise, what a function returns isn't walked again: the Emph that
-- replaces a Str stays an Emph, while the document's own Emphs become
-- Strongs.
-- stateless: the same with traverse = "bottomup"
return {{
  Str = function(s)
    if s.text == "Some" then return pandoc.Emph{pandoc.Str("new")} end
  end,
  Emph = function(e) return pandoc.Strong(e.content) end,
}}
