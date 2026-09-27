#!/usr/bin/env node
// A pandoc filter: upper-case all text outside code.
//
//     pandoc --filter ./upper.js input.md

import { Str } from "panir";
import { runFilter } from "panir/node";

await runFilter({
  Str: (s) => Str(s.text.toUpperCase()),
});
