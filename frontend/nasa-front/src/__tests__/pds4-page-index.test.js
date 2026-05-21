import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const scriptSource = readFileSync(
  fileURLToPath(new URL("../../scripts/build-pds4-page-index.mjs", import.meta.url)),
  "utf8"
);
const pdsProductsHook = readFileSync(
  fileURLToPath(new URL("../hooks/usePds4Products.js", import.meta.url)),
  "utf8"
);
const discoverPage = readFileSync(
  fileURLToPath(new URL("../Routes/DiscoverPage.jsx", import.meta.url)),
  "utf8"
);
const discoverItemPage = readFileSync(
  fileURLToPath(new URL("../Routes/DiscoverItemPage.jsx", import.meta.url)),
  "utf8"
);

test("page index script writes the static frontend artifact", () => {
  assert.match(scriptSource, /pds4-page-index\.json/);
  assert.match(scriptSource, /https:\/\/pds\.mcp\.nasa\.gov\/api\/search\/1/);
  assert.match(scriptSource, /const DEFAULT_MAX_PAGES = 1/);
  assert.match(scriptSource, /pages:\s*pageIndex/);
  assert.match(scriptSource, /searchAfter:\s*null/);
  assert.match(scriptSource, /writePageIndex\(outputPath,\s*partialIndex\)/);
});

test("PDS4 product hook loads static cursors before rejecting a direct page jump", () => {
  assert.match(pdsProductsHook, /PAGE_INDEX_URL\s*=\s*["']\/pds4-page-index\.json["']/);
  assert.match(pdsProductsHook, /loadPageIndex/);
  assert.match(pdsProductsHook, /staticCursorByPageRef/);
  assert.match(pdsProductsHook, /getStaticSearchAfter/);
  assert.match(pdsProductsHook, /cache:\s*["']no-store["']/);
  assert.match(pdsProductsHook, /indexedMaxPage/);
  assert.match(pdsProductsHook, /Last indexed page:/);

  const staticLookupPosition = pdsProductsHook.indexOf("getStaticSearchAfter");
  const unreachablePosition = pdsProductsHook.indexOf("Page ${page} is not reachable yet");

  assert.ok(staticLookupPosition !== -1);
  assert.ok(unreachablePosition !== -1);
  assert.ok(staticLookupPosition < unreachablePosition);
});

test("Discover page has a direct page number search control", () => {
  assert.match(discoverPage, /TextField/);
  assert.match(discoverPage, /GoToPageIcon/);
  assert.match(discoverPage, /handlePageSearchSubmit/);
  assert.match(discoverPage, /onKeyDown=\{\(e\) =>/);
  assert.match(discoverPage, /setSearchParams\(\{\s*page:\s*String\(targetPage\)\s*\}\)/);
});

test("generated MinIO previews are marked and shown with a yellow border", () => {
  assert.match(pdsProductsHook, /generatedPreviewKeys/);
  assert.match(pdsProductsHook, /item\.id/);
  assert.match(pdsProductsHook, /generatedByLid\?\.\[item\.id\]/);
  assert.match(pdsProductsHook, /previewSource\s*=\s*generatedPreview\?\.preview_source\s*\?\?\s*["']generated_transform["']/);
  assert.match(pdsProductsHook, /itemsWithThumbs\.every\(\(item\)\s*=>\s*item\.thumbUrl\)/);
  assert.match(discoverPage, /p\.previewSource\s*===\s*["']generated_transform["']/);
  assert.match(discoverPage, /border:\s*isGeneratedPreview\s*\?\s*["']2px solid #facc15["']/);
  assert.match(discoverItemPage, /state\.previewSource\s*===\s*["']generated_transform["']/);
  assert.match(discoverItemPage, /border:\s*isGeneratedPreview\s*\?\s*["']3px solid #facc15["']/);
});
