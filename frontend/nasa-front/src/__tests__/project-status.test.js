import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const myProjectsPage = readFileSync(
  fileURLToPath(new URL("../Routes/MyProjectsPage.jsx", import.meta.url)),
  "utf8"
);
const addToProjectDialog = readFileSync(
  fileURLToPath(new URL("../Component/AddToProjectDialog.jsx", import.meta.url)),
  "utf8"
);

test("project status chips treat not started as neutral", () => {
  assert.match(myProjectsPage, /case ["']not_started["']:\s*return \{ label: ["']not started["'], color: ["']default["'] \}/);
  assert.match(myProjectsPage, /case ["']published["']:\s*return \{ label: ["']published["'], color: ["']success["'] \}/);
  assert.doesNotMatch(myProjectsPage, /case ["']finished["']:\s*return \{ label: ["']finished["'], color: ["']success["'] \};\s*case ["']not_started["']/);

  assert.match(addToProjectDialog, /STATUS_LABEL\s*=\s*\{[^}]*not_started:\s*["']not started["']/s);
  assert.match(addToProjectDialog, /STATUS_LABEL\s*=\s*\{[^}]*published:\s*["']published["']/s);
  assert.match(addToProjectDialog, /STATUS_COLOR\s*=\s*\{[^}]*not_started:\s*["']default["']/s);
  assert.match(addToProjectDialog, /STATUS_COLOR\s*=\s*\{[^}]*published:\s*["']success["']/s);
});

test("my projects status chip uses latest job errors before project status", () => {
  assert.match(myProjectsPage, /latestJobsByProject/);
  assert.match(myProjectsPage, /function hasImageError\(job\)/);
  assert.match(myProjectsPage, /latestJob\?\.status === ["']FAILED["']/);
  assert.match(myProjectsPage, /label: ["']partial["'], color: ["']warning["']/);
  assert.match(myProjectsPage, /apiFetch\(`\/api\/jobs\/project\/\$\{project\.id\}`\)/);
});

test("project creation shows backend limit errors inside the dialog", () => {
  assert.match(myProjectsPage, /createError/);
  assert.match(myProjectsPage, /setCreateError/);
  assert.match(myProjectsPage, /You can't create more than 3 not published projects|j\.detail/);
  assert.doesNotMatch(myProjectsPage, /alert\(e\.message\)/);
});
