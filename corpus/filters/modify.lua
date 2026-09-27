-- Change fields: headers one level down, links and images to other
-- targets, a class on every code block.
-- stateless: the same with traverse = "bottomup"
return {{
  Header = function(h) h.level = h.level + 1; return h end,
  Link = function(l) l.target = "https://example.org/" .. l.target; return l end,
  Image = function(i) i.src = "img/" .. i.src; i.attributes.loading = "lazy"; return i end,
  CodeBlock = function(c) c.classes:insert("numbered"); return c end,
}}
