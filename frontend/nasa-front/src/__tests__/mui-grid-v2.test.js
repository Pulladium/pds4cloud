import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { join } from "node:path";
import test from "node:test";

const sourceRoot = fileURLToPath(new URL("../", import.meta.url));
const legacyGridPropPattern = /<Grid\b(?![^>]*\bcontainer\b)[^>]*\b(item|xs|sm|md|lg|xl)=/;

function* sourceFiles(dir) {
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) {
      yield* sourceFiles(path);
    } else if (/\.(jsx?|tsx?)$/.test(entry)) {
      yield path;
    }
  }
}

test("MUI Grid items use the v2 size API", () => {
  const offenders = [];

  for (const path of sourceFiles(sourceRoot)) {
    const lines = readFileSync(path, "utf8").split("\n");
    lines.forEach((line, index) => {
      if (legacyGridPropPattern.test(line)) {
        offenders.push(`${path}:${index + 1}: ${line.trim()}`);
      }
    });
  }

  assert.deepEqual(offenders, []);
});
