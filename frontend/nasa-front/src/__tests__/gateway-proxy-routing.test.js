import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const viteConfig = readFileSync(
  fileURLToPath(new URL("../../vite.config.js", import.meta.url)),
  "utf8"
);
const pdsProductsHook = readFileSync(
  fileURLToPath(new URL("../hooks/usePds4Products.js", import.meta.url)),
  "utf8"
);
const metadataHook = readFileSync(
  fileURLToPath(new URL("../hooks/useFullMetadata.js", import.meta.url)),
  "utf8"
);
const gatewayUrlSource = readFileSync(
  fileURLToPath(new URL("../api/gatewayUrl.js", import.meta.url)),
  "utf8"
);
const myProjectItemSource = readFileSync(
  fileURLToPath(new URL("../Routes/MyProjectItemPage.jsx", import.meta.url)),
  "utf8"
);
const nginxConfig = readFileSync(
  fileURLToPath(new URL("../../docker/nginx.conf", import.meta.url)),
  "utf8"
);

test("frontend proxies app API calls only to the Spring gateway", () => {
  assert.match(viteConfig, /target:\s*['"]http:\/\/localhost:8080['"]/);
  assert.doesNotMatch(viteConfig, /target:\s*['"]http:\/\/localhost:8000['"]/);
  assert.doesNotMatch(viteConfig, /pds\.mcp\.nasa\.gov/);
});

test("discovery calls go through the gateway discovery API", () => {
  assert.match(pdsProductsHook, /const PDS_API = ["']\/api\/discovery["']/);
  assert.match(metadataHook, /const PDS_API = ["']\/api\/discovery["']/);
});

test("public gallery and multipart publishing have dedicated gateway routes", () => {
  assert.match(viteConfig, /\/api/);
});

test("production API calls stay same-origin instead of using localhost gateway", () => {
  assert.match(gatewayUrlSource, /import\.meta\.env\.PROD\s*\?\s*["']["']/);
  assert.match(gatewayUrlSource, /VITE_GATEWAY_URL/);
  assert.doesNotMatch(myProjectItemSource, /localhost:8080/);
  assert.doesNotMatch(myProjectItemSource, /VITE_GATEWAY_URL/);
  assert.match(myProjectItemSource, /gatewayUrl\(["']\/api\/jobs["']\)/);
});

test("bare admin minio URL enters the SPA handoff before nginx proxies MinIO console", () => {
  assert.match(nginxConfig, /location = \/api\/admin\/minio\s*\{/);
  assert.match(nginxConfig, /return 302 \/admin\/minio;/);
  assert.match(nginxConfig, /location \/minio\/\s*\{/);
  assert.match(nginxConfig, /proxy_pass http:\/\/minio:9001\//);
  assert.match(nginxConfig, /location \/api\/v1\/\s*\{/);
  assert.match(nginxConfig, /location \/static\/\s*\{/);
  assert.match(nginxConfig, /location \/styles\/\s*\{/);
  assert.match(nginxConfig, /location \/ws\/\s*\{/);
  assert.match(nginxConfig, /proxy_set_header Upgrade \$http_upgrade;/);
  assert.match(nginxConfig, /proxy_set_header Origin http:\/\/minio:9001;/);
  assert.match(nginxConfig, /proxy_read_timeout 86400;/);
  assert.match(nginxConfig, /location \/api\/\s*\{/);
});
