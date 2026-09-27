-- The default order: every Inline (bottom-up, the metadata first), then
-- every list of inlines, then every Block, then every list of blocks,
-- then the metadata, then the document. Each call is noted; a last
-- paragraph lists them.
local seen = {}
local function note(name)
  return function(el) seen[#seen + 1] = el.text and (name .. ":" .. el.text) or name end
end
return {{
  Str = note("Str"), Emph = note("Emph"), Note = note("Note"), Link = note("Link"),
  Code = note("Code"), Para = note("Para"), Header = note("Header"), Div = note("Div"),
  Table = note("Table"), Figure = note("Figure"), BlockQuote = note("BlockQuote"),
  Inlines = function(xs) seen[#seen + 1] = "Inlines" .. #xs end,
  Blocks = function(xs) seen[#seen + 1] = "Blocks" .. #xs end,
  Meta = function() seen[#seen + 1] = "Meta" end,
  Pandoc = function(doc)
    seen[#seen + 1] = "Pandoc"
    doc.blocks:insert(pandoc.Para(table.concat(seen, " ")))
    return doc
  end,
}}
