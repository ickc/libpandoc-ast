-- The metadata as a whole, then the document: a field changed, two added
-- (one the output format), one removed; the document gets a paragraph
-- after the metadata's changes.
-- stateless: the same with traverse = "bottomup"
return {{
  Meta = function(m)
    m.draft = true
    m.format = FORMAT
    m.tags = pandoc.MetaList{pandoc.MetaString("a"), pandoc.MetaInlines{pandoc.Str("b")}}
    m.count = nil
    return m
  end,
  Pandoc = function(doc)
    doc.blocks:insert(1, pandoc.Para{pandoc.Str(doc.meta.draft and "draft" or "final")})
    return doc
  end,
}}
