-- Top-down: the document, the metadata, then depth-first from the root, a
-- list before its elements and a node before its children. Each call is
-- noted; a second filter adds a last paragraph listing them.
local seen = {}
local function note(name)
  return function(el) seen[#seen + 1] = el.text and (name .. ":" .. el.text) or name end
end
return {
  {
    traverse = "topdown",
    Str = note("Str"), Emph = note("Emph"), Note = note("Note"), Link = note("Link"),
    Code = note("Code"), Para = note("Para"), Header = note("Header"), Div = note("Div"),
    Table = note("Table"), Figure = note("Figure"), BlockQuote = note("BlockQuote"),
    Inlines = function(xs) seen[#seen + 1] = "Inlines" .. #xs end,
    Blocks = function(xs) seen[#seen + 1] = "Blocks" .. #xs end,
    Meta = function() seen[#seen + 1] = "Meta" end,
    Pandoc = function() seen[#seen + 1] = "Pandoc" end,
  },
  {
    Pandoc = function(doc)
      doc.blocks:insert(pandoc.Para(table.concat(seen, " ")))
      return doc
    end,
  },
}
