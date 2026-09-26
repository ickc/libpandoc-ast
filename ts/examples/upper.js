#!/usr/bin/env node
// A pandoc filter: upper-case all text outside code.
//
//     pandoc --filter ./upper.js input.md

import { Str } from "pandom-js";
import { runFilter } from "pandom-js/node";

await runFilter({
  Str: (s) => Str(s.text.toUpperCase()),
});
