#!/usr/bin/env node
// A pandoc filter: upper-case all text outside code.
//
//     pandoc --filter ./upper.js input.md

import { Str } from "libpandoc-ast";
import { runFilter } from "libpandoc-ast/node";

await runFilter({
  Str: (s) => Str(s.text.toUpperCase()),
});
