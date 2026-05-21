import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const addToProjectDialog = readFileSync(
  fileURLToPath(new URL("../Component/AddToProjectDialog.jsx", import.meta.url)),
  "utf8"
);

test("add to project shows backend index warnings as warnings, not hard failures", () => {
  assert.match(addToProjectDialog, /json\.index_warning/);
  assert.match(addToProjectDialog, /severity:\s*json\.index_warning \? ["']warning["'] : ["']success["']/);
  assert.match(addToProjectDialog, /Added to/);
});

test("add to project can create a project and add the current image", () => {
  assert.match(addToProjectDialog, /Button,/);
  assert.match(addToProjectDialog, /handleCreateProject/);
  assert.match(addToProjectDialog, /apiFetch\(["']\/api\/projects["']/);
  assert.match(addToProjectDialog, /Create and add/);
  assert.match(addToProjectDialog, /await addImageToProject\(created\)/);
});
