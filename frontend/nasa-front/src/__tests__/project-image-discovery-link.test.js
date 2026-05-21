import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const projectItemPage = readFileSync(
  fileURLToPath(new URL("../Routes/MyProjectItemPage.jsx", import.meta.url)),
  "utf8"
);

const publishedProjectItemPage = readFileSync(
  fileURLToPath(new URL("../Routes/PublishedProjectItemPage.jsx", import.meta.url)),
  "utf8"
);

const discoverItemPage = readFileSync(
  fileURLToPath(new URL("../Routes/DiscoverItemPage.jsx", import.meta.url)),
  "utf8"
);

test("project image cards link to discovery item pages with compatible state", () => {
  assert.match(projectItemPage, /CardActionArea/);
  assert.match(projectItemPage, /component=\{RouterLink\}/);
  assert.match(projectItemPage, /to=\{`\/discover\/\$\{encodeURIComponent\(img\.lid\)\}`\}/);
  assert.match(projectItemPage, /state=\{discoveryState\}/);
  assert.match(projectItemPage, /thumbUrl:\s*img\.thumb_url \?\? ["']["']/);
  assert.match(projectItemPage, /previewSource:\s*img\.preview_source \?\? null/);
});

test("published project image cards preserve discovery preview metadata", () => {
  assert.match(publishedProjectItemPage, /function discoveryStateFromPublishedImage\(img\)/);
  assert.match(publishedProjectItemPage, /thumbUrl:\s*publishedImageThumbUrl\(img\)/);
  assert.match(publishedProjectItemPage, /previewSource:\s*img\.preview_source \?\? null/);
  assert.match(publishedProjectItemPage, /border:\s*isGeneratedPreview\s*\?\s*["']3px solid #facc15["']/);
});

test("discovery item page can fall back to the route id when navigation state is missing", () => {
  assert.match(discoverItemPage, /useParams/);
  assert.match(discoverItemPage, /const item = state \?\? \(routeId \? \{/);
  assert.match(discoverItemPage, /lid:\s*routeId/);
  assert.match(discoverItemPage, /useFullMetadata\(item\?\.lid \?\? null/);
});
