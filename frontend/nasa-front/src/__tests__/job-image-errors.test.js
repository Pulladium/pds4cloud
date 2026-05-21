import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const jobProgressPanel = readFileSync(
  fileURLToPath(new URL("../Component/JobProgressPanel.jsx", import.meta.url)),
  "utf8"
);
const projectItemPage = readFileSync(
  fileURLToPath(new URL("../Routes/MyProjectItemPage.jsx", import.meta.url)),
  "utf8"
);

test("job progress preserves failed image entries instead of hiding them by worker", () => {
  assert.match(jobProgressPanel, /failedProgress/);
  assert.match(jobProgressPanel, /progressByLid/);
  assert.doesNotMatch(jobProgressPanel, /new Map\(progress\.map\(\(item\) => \[item\.worker_id, item\]\)\)/);
});

test("job progress cards use a per-image key when a lid is present", () => {
  assert.match(jobProgressPanel, /key=\{slot\.lid\s*\?/);
  assert.match(jobProgressPanel, /\$\{slot\.worker_id\}:\$\{slot\.lid\}/);
  assert.doesNotMatch(jobProgressPanel, /key=\{slot\.worker_id\}/);
});

test("project detail shows per-image job errors and can rerun failed images", () => {
  assert.match(projectItemPage, /jobProgressByLid/);
  assert.match(projectItemPage, /imageJobProgress/);
  assert.match(projectItemPage, /imageJobProgress\?\.error/);
  assert.match(projectItemPage, /handleRerunFailedImages/);
  assert.match(projectItemPage, /Run failed images/);
});

test("completed jobs with partial image errors render as warnings", () => {
  assert.match(jobProgressPanel, /isPartial/);
  assert.match(jobProgressPanel, /job\.status === ["']COMPLETED["'] && Boolean\(job\.error\)/);
  assert.match(jobProgressPanel, /severity=["']warning["']/);
});
