import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const jobProgressPanel = readFileSync(
  fileURLToPath(new URL("../Component/JobProgressPanel.jsx", import.meta.url)),
  "utf8"
);

test("job progress tile shows model input context details", () => {
  assert.match(jobProgressPanel, /metadata_loaded/);
  assert.match(jobProgressPanel, /array_summary/);
  assert.match(jobProgressPanel, /GPT got image/);
  assert.match(jobProgressPanel, /PDS4 bands/);
});
