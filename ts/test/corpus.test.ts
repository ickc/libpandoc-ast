// The shared corpus: what every binding must accept and reject.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { ASTDecodeError, fromJSON, toJSON } from "../src/index.ts";

function corpus(name: string): unknown[] {
  const text = readFileSync(new URL(`../../corpus/${name}`, import.meta.url), "utf8");
  // split on "\n" only: strings may hold other line separators
  return text.split("\n").filter((l) => l).map((l) => JSON.parse(l));
}

test("round trip", () => {
  const docs = [...corpus("arbitrary.jsonl"), ...corpus("pandoc.jsonl")];
  docs.forEach((j, i) => assert.deepEqual(toJSON(fromJSON(j)), j, `document ${i}`));
});

// the corpus names fields as the schema does; TypeScript in camelCase
const camel = (p: unknown) => typeof p === "string" && p !== "pandoc-api-version"
  ? p.replace(/_([a-z])/g, (_, c: string) => c.toUpperCase()) : p;

for (const c of corpus("invalid.jsonl") as { name: string; path: unknown[]; document: unknown }[]) {
  test(`invalid: ${c.name}`, () => {
    assert.throws(() => fromJSON(c.document), (e: unknown) => {
      assert.ok(e instanceof ASTDecodeError, String(e));
      assert.deepEqual(e.path, c.path.map(camel), e.message);
      return true;
    });
  });
}
