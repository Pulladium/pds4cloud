import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const myProjectsPage = readFileSync(
  fileURLToPath(new URL("../Routes/MyProjectsPage.jsx", import.meta.url)),
  "utf8"
);
const myProjectItemPage = readFileSync(
  fileURLToPath(new URL("../Routes/MyProjectItemPage.jsx", import.meta.url)),
  "utf8"
);

test("project list supports deleting projects with confirmation", () => {
  assert.match(myProjectsPage, /DeleteOutlineIcon/);
  assert.match(myProjectsPage, /deleteTarget/);
  assert.match(myProjectsPage, /method:\s*["']DELETE["']/);
  assert.match(myProjectsPage, /Delete project/);
  assert.match(myProjectsPage, /setRefreshKey/);
});

test("project detail supports deleting and returns to list", () => {
  assert.match(myProjectItemPage, /DeleteOutlineIcon/);
  assert.match(myProjectItemPage, /deleteOpen/);
  assert.match(myProjectItemPage, /method:\s*["']DELETE["']/);
  assert.match(myProjectItemPage, /navigate\(["']\/my-projects["']\)/);
  assert.match(myProjectItemPage, /Delete project/);
});
