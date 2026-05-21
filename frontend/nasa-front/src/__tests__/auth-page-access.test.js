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
const addToProjectDialog = readFileSync(
  fileURLToPath(new URL("../Component/AddToProjectDialog.jsx", import.meta.url)),
  "utf8"
);
const appSource = readFileSync(
  fileURLToPath(new URL("../App.jsx", import.meta.url)),
  "utf8"
);
const useApiSource = readFileSync(
  fileURLToPath(new URL("../api/useApi.js", import.meta.url)),
  "utf8"
);
const useProjectsSource = readFileSync(
  fileURLToPath(new URL("../hooks/useProjects.js", import.meta.url)),
  "utf8"
);

test("project pages wait for auth before calling protected project APIs", () => {
  assert.match(appSource, /function RequireLogin\(/);
  assert.match(appSource, /keycloak\.login\(\{\s*redirectUri:\s*window\.location\.href\s*\}\)/);
  assert.match(appSource, /path=["']\/my-projects["']\s+element=\{<RequireLogin>/);
  assert.match(appSource, /path=["']\/my-projects\/:id["']\s+element=\{<RequireLogin>/);
  assert.match(myProjectsPage, /canUseProjects\s*=\s*initialized\s*&&\s*keycloak\?\.authenticated/);
  assert.match(myProjectsPage, /useProjects\(canUseProjects,\s*refreshKey\)/);
  assert.match(myProjectItemPage, /if \(!initialized\) return/);
  assert.match(myProjectItemPage, /if \(!canUseProjects\)/);
  assert.match(addToProjectDialog, /useProjects\(open && canUseProjects\)/);
  assert.match(useProjectsSource, /setState\(\{ projects: \[\], loading: false, error: null \}\)/);
});

test("admin page is route-guarded for admin users only", () => {
  assert.match(appSource, /function RequireAdmin\(/);
  assert.match(appSource, /isAdmin\(keycloak\)/);
  assert.match(appSource, /path=["']\/admin["']\s+element=\{<RequireAdmin><AdminPanelPage \/><\/RequireAdmin>\}/);
  assert.doesNotMatch(appSource, /path=["']\/admin["']\s+element=\{<AdminPanelPage \/>/);
});

test("api client does not force a login redirect on 401", () => {
  assert.doesNotMatch(useApiSource, /keycloak\.login\(\)/);
  assert.match(useApiSource, /interceptors\.response\.use\(\s*\(res\) => res,\s*\(error\) => Promise\.reject\(error\)/);
});
