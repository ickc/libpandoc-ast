-- Bottom-up in one walk (panflute's order), which pandoc's Lua doesn't
-- have: each node after its children, a list after its elements, Meta
-- after the metadata, Pandoc last. So this Lua filter only appends the
-- expected calls, written out by hand for bottomup.md; each language's
-- filter notes its calls as typewise.lua does and appends them. Checked:
-- the inlines alone, and the blocks alone, are in the order pandoc's
-- typewise walk visits them.
return {{
  Pandoc = function(doc)
    doc.blocks:insert(pandoc.Para(table.concat({
      "Str:The", "Str:title", "Inlines1", "Emph", "Inlines3", "Meta",
      "Str:A", "Str:b", "Inlines1", "Emph", "Inlines3", "Header",
      "Str:c", "Str:g", "Inlines1", "Para", "Blocks1", "Note", "Str:d", "Inlines4", "Para",
      "Str:e", "Str:f", "Inlines1", "Strong", "Inlines3", "Para", "Blocks1", "Div",
      "Blocks3", "Pandoc",
    }, " ")))
    return doc
  end,
}}
