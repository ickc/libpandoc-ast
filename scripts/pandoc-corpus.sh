#!/usr/bin/env bash
# Regenerate corpus/pandoc.jsonl: documents written by pandoc itself, from
# corpus/*.md. Needs a pandoc whose pandoc-api-version matches the schema.
set -euo pipefail
cd "$(dirname "$0")/.."
: > corpus/pandoc.jsonl
for f in corpus/*.md; do
  pandoc -f markdown -t json "$f" | tr -d "\n" >> corpus/pandoc.jsonl
  echo >> corpus/pandoc.jsonl
done
