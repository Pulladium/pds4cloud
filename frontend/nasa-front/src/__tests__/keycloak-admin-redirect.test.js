import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const userAppBarSource = readFileSync(
  fileURLToPath(new URL("../Component/UserAppBar.jsx", import.meta.url)),
  "utf8"
);
const keycloakContextSource = readFileSync(
  fileURLToPath(new URL("../context/KeycloakContext.jsx", import.meta.url)),
  "utf8"
);
const keycloakConfigSource = readFileSync(
  fileURLToPath(new URL("../config/keycloak.js", import.meta.url)),
  "utf8"
);

test("login keeps the user on the current route after Keycloak redirects back", () => {
  assert.match(userAppBarSource, /currentUrl\s*=\s*window\.location\.href/);
  assert.match(userAppBarSource, /keycloak\.login\(\{\s*redirectUri:\s*currentUrl\s*\}\)/);
  assert.match(userAppBarSource, /keycloak\.register\(\{\s*redirectUri:\s*currentUrl\s*\}\)/);
  assert.doesNotMatch(userAppBarSource, /redirectUri:\s*window\.location\.origin\s*\+\s*['"]\/['"]/);
});

test("Keycloak checks existing SSO when the app loads on a protected route", () => {
  assert.match(keycloakContextSource, /onLoad:\s*['"]check-sso['"]/);
});

test("Keycloak URL is production-safe instead of hardcoded localhost", () => {
  assert.match(keycloakConfigSource, /VITE_KEYCLOAK_URL/);
  assert.match(keycloakConfigSource, /import\.meta\.env\.PROD\s*\?\s*window\.location\.origin/);
  assert.doesNotMatch(keycloakConfigSource, /url:\s*["']http:\/\/localhost:8484["']/);
});
