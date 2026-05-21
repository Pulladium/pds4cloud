import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const projectItemPage = readFileSync(
  fileURLToPath(new URL("../Routes/MyProjectItemPage.jsx", import.meta.url)),
  "utf8"
);
const fullMetadataPanel = readFileSync(
  fileURLToPath(new URL("../Component/FullMetadataPanel.jsx", import.meta.url)),
  "utf8"
);

test("project detail shows the latest generated report when no current job is selected", () => {
  assert.match(projectItemPage, /latestReportUrl/);
  assert.match(projectItemPage, /\/api\/jobs\/project\/\$\{id\}/);
  assert.match(projectItemPage, /job\?\.pdf_url\s*\?\?\s*latestReportUrl/);
  assert.match(projectItemPage, /PdfPanel pdfUrl=\{reportUrl\}/);
});

test("full metadata panel can open loaded raw JSON in a new tab", () => {
  assert.match(fullMetadataPanel, /Open raw metadata/);
  assert.match(fullMetadataPanel, /JSON\.stringify\(data,\s*null,\s*2\)/);
  assert.match(fullMetadataPanel, /window\.open\(url,\s*["_']_blank["_']/);
  assert.match(fullMetadataPanel, /URL\.createObjectURL/);
});
