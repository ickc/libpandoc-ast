/**
 * Running a filter under pandoc, with Node.js:
 *
 *     #!/usr/bin/env node
 *     import { Str } from "libpandoc-ast";
 *     import { runFilter } from "libpandoc-ast/node";
 *     runFilter({ Str: (s) => Str(s.text.toUpperCase()) });
 *
 *     pandoc --filter ./upper.js input.md
 */

import { applyFilter } from "./walk.ts";
import type { Filter } from "./walk.ts";
import { parse, serialize } from "./index.ts";

/** Read a document from stdin, apply the filter, write it to stdout. */
export async function runFilter(filter: Filter): Promise<void> {
  const chunks: Buffer[] = [];
  for await (const chunk of process.stdin) chunks.push(chunk as Buffer);
  const doc = parse(Buffer.concat(chunks).toString("utf8"));
  const format = process.argv[2];
  process.stdout.write(serialize(applyFilter(doc, filter, format)));
}
