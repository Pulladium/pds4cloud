import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const myProjectItemPage = readFileSync(
  fileURLToPath(new URL("../Routes/MyProjectItemPage.jsx", import.meta.url)),
  "utf8"
);
const appSource = readFileSync(
  fileURLToPath(new URL("../App.jsx", import.meta.url)),
  "utf8"
);
const publishedProjectsPage = readFileSync(
  fileURLToPath(new URL("../Routes/PublishedProjectsPage.jsx", import.meta.url)),
  "utf8"
);
const publishedProjectItemPage = readFileSync(
  fileURLToPath(new URL("../Routes/PublishedProjectItemPage.jsx", import.meta.url)),
  "utf8"
);
const tabsSource = readFileSync(
  fileURLToPath(new URL("../Component/AIControlPanelTabs.jsx", import.meta.url)),
  "utf8"
);

test("project detail has a publication form with 2 MB image validation", () => {
  assert.match(myProjectItemPage, /MAX_PUBLISH_IMAGE_BYTES\s*=\s*2\s*\*\s*1024\s*\*\s*1024/);
  assert.match(myProjectItemPage, /FormData/);
  assert.match(myProjectItemPage, /researcherComment/);
  assert.match(myProjectItemPage, /publishImages/);
  assert.match(myProjectItemPage, /pdf_url",\s*reportUrl/);
  assert.match(myProjectItemPage, /\/api\/projects\/\$\{id\}\/publish/);
  assert.doesNotMatch(myProjectItemPage, /label=["']PDF report URL["']/);
});

test("gallery route renders published project cards", () => {
  assert.match(appSource, /PublishedProjectsPage/);
  assert.match(appSource, /path=["']\/gallery["']\s+element=\{<PublishedProjectsPage \/>/);
  assert.match(appSource, /path=["']\/published-projects["']\s+element=\{<PublishedProjectsPage \/>/);
  assert.match(appSource, /path=["']\/gallery\/:id["']\s+element=\{<PublishedProjectItemPage \/>/);
  assert.match(tabsSource, /label:\s*['"]Published['"],\s*path:\s*['"]\/gallery['"]/);
  assert.match(publishedProjectsPage, /\/api\/projects\/published/);
  assert.match(publishedProjectsPage, /CardActionArea/);
  assert.match(publishedProjectsPage, /to=\{`\/gallery\/\$\{encodeURIComponent\(project\.id\)\}`\}/);
  assert.match(publishedProjectsPage, /researcher_comment/);
});

test("published project preview shows images, metrics, model, and embedded PDF", () => {
  assert.match(publishedProjectItemPage, /PdfPanel/);
  assert.match(publishedProjectItemPage, /research_images/);
  assert.match(publishedProjectItemPage, /CardActionArea/);
  assert.match(publishedProjectItemPage, /to=\{`\/discover\/\$\{encodeURIComponent\(img\.lid\)\}`\}/);
  assert.match(publishedProjectItemPage, /project\?\.metrics/);
  assert.match(publishedProjectItemPage, /\/api\/jobs\/project\/\$\{id\}/);
  assert.match(publishedProjectItemPage, /Model/);
  assert.match(publishedProjectItemPage, /Prompt tokens/);
  assert.match(publishedProjectItemPage, /Completion tokens/);
  assert.match(publishedProjectItemPage, /Observed cost/);
});
