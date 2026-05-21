import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const tabsSource = readFileSync(
  fileURLToPath(new URL("../Component/AIControlPanelTabs.jsx", import.meta.url)),
  "utf8"
);

test("my projects tab is only visible for researcher or admin users", () => {
  assert.match(tabsSource, /useKeycloak/);
  assert.match(tabsSource, /isResearcherOrAdmin/);
  assert.match(tabsSource, /canUseProjects\s*=\s*initialized\s*&&\s*keycloak\?\.authenticated\s*&&\s*isResearcherOrAdmin\(keycloak\)/);
  assert.match(tabsSource, /filter\(\(tab\) => tab\.public \|\| canUseProjects\)/);
  assert.match(tabsSource, /label:\s*["']MyProjects["'],\s*path:\s*["']\/my-projects["'],\s*public:\s*false/);
});
