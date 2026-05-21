import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const adminPage = readFileSync(
  fileURLToPath(new URL("../Routes/AdminPanelPage.jsx", import.meta.url)),
  "utf8"
);
const jobEventsPage = readFileSync(
  fileURLToPath(new URL("../Routes/AdminJobEventsPage.jsx", import.meta.url)),
  "utf8"
);
const adminMinioPage = readFileSync(
  fileURLToPath(new URL("../Routes/AdminMinioPage.jsx", import.meta.url)),
  "utf8"
);
const appPage = readFileSync(
  fileURLToPath(new URL("../App.jsx", import.meta.url)),
  "utf8"
);

test("admin page renders jobs history metrics and links to event logs", () => {
  assert.match(adminPage, /Job History/);
  assert.match(adminPage, /Duration/);
  assert.match(adminPage, /Events/);
  assert.match(adminPage, /event_count/);
  assert.match(adminPage, /duration_ms/);
  assert.match(adminPage, /\/admin\/jobs\/\$\{job\.job_id\}\/events/);
});

test("admin job events page loads event log from gateway", () => {
  assert.match(jobEventsPage, /\/api\/admin\/jobs\/\$\{jobId\}\/events/);
  assert.match(jobEventsPage, /payload_json/);
  assert.match(jobEventsPage, /Job Events/);
  assert.match(appPage, /\/admin\/jobs\/:jobId\/events/);
});

test("admin minio route opens nginx-proxied console after route guard", () => {
  assert.match(appPage, /\/admin\/minio/);
  assert.match(appPage, /<RequireAdmin fallback=["']home["']><AdminMinioPage \/><\/RequireAdmin>/);
  assert.doesNotMatch(adminMinioPage, /\/api\/admin\/minio\/session/);
  assert.match(adminMinioPage, /window\.location\.assign\(["']\/minio\/["']\)/);
});

test("admin UI no longer contains quarantine controls", () => {
  assert.doesNotMatch(adminPage, /Quarantine/);
  assert.doesNotMatch(adminPage, /\/api\/admin\/quarantine/);
  assert.doesNotMatch(adminPage, /selectedQuarantine/);
});
