#!/usr/bin/env node
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const DEFAULT_API = "https://pds.mcp.nasa.gov/api/search/1";
const DEFAULT_PAGE_SIZE = 10;
const DEFAULT_MAX_PAGES = 1;
const DEFAULT_OUT = "public/pds4-page-index.json";

const START_KEY = "pds:Time_Coordinates.pds:start_date_time";
const SORT_KEY = "ops:Harvest_Info.ops:harvest_date_time";
const SOL_KEY = "mars2020:Observation_Information.mars2020:sol_number";
const FILE_KEY = "pds:File.pds:file_name";
const BROWSE_KEY = "ref_lid_browse";

const Q =
  `((ref_lid_investigation eq "urn:nasa:pds:context:investigation:mission.mars2020") and ` +
  `(ref_lid_instrument eq "urn:nasa:pds:context:instrument:mars2020.mastcamz") and ` +
  `(${START_KEY} ge "2021-02-18T00:00:00Z"))`;

const FIELDS = [
  "lid", "title", START_KEY, SOL_KEY, FILE_KEY, SORT_KEY, BROWSE_KEY,
].join(",");

function parseArgs(argv) {
  const args = {
    api: DEFAULT_API,
    pageSize: DEFAULT_PAGE_SIZE,
    maxPages: DEFAULT_MAX_PAGES,
    out: DEFAULT_OUT,
  };
  for (const arg of argv) {
    const [key, value] = arg.split("=");
    if (key === "--api" && value) args.api = value;
    if (key === "--page-size" && value) args.pageSize = Number(value);
    if (key === "--max-pages" && value) args.maxPages = Number(value);
    if (key === "--out" && value) args.out = value;
  }
  if (!Number.isInteger(args.pageSize) || args.pageSize < 1) {
    throw new Error("--page-size must be a positive integer");
  }
  if (!Number.isInteger(args.maxPages) || args.maxPages < 1) {
    throw new Error("--max-pages must be a positive integer");
  }
  return args;
}

// ✅ Match your hook: simple sol extraction, numeric for cursor
function getSortValue(product) {
  const p = product?.properties ?? {};
  const val = (p[SOL_KEY] ?? [])[0];
  return val != null ? Number(val) : null;
}

async function fetchPage(api, pageSize, searchAfter) {
  const params = new URLSearchParams({
    q: Q,
    fields: FIELDS,
    limit: String(pageSize),
    sort: SOL_KEY,  // ✅ Only this — NO "order" parameter
  });
  if (searchAfter != null) {
    params.set("search-after", String(searchAfter));
  }
  const response = await fetch(`${api}/classes/observational?${params.toString()}`);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`PDS API ${response.status}: ${text}`);
  }
  return response.json();
}

async function writePageIndex(outputPath, index) {
  await mkdir(dirname(outputPath), { recursive: true });
  await writeFile(outputPath, `${JSON.stringify(index, null, 2)}\n`);
}

async function buildPageIndex({ api, pageSize, maxPages, onProgress }) {
  const pageIndex = [{ page: 1, searchAfter: null }];
  let searchAfter = null;
  let total = 0;
  let generatedAt = new Date().toISOString();

  function snapshot(complete) {
    return {
      query: Q,
      sort: SOL_KEY,  // ✅ Record what we actually used
      pageSize,
      total,
      generatedAt,
      complete,
      pages: pageIndex,
    };
  }

  for (let page = 1; page <= maxPages; page += 1) {
    const json = await fetchPage(api, pageSize, searchAfter);
    const raw = json.data ?? [];
    total = json.summary?.hits ?? total;
    generatedAt = new Date().toISOString();

    if (!raw.length) {
      await onProgress?.(snapshot(true));
      break;
    }

    const nextCursor = getSortValue(raw[raw.length - 1]);  // ✅ Same as hook
    if (!nextCursor) {
      await onProgress?.(snapshot(true));
      break;
    }

    if (page < maxPages) {
      pageIndex.push({ page: page + 1, searchAfter: nextCursor });
    }

    searchAfter = nextCursor;
    await onProgress?.(snapshot(page === maxPages));
  }

  return snapshot(true);
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const cwd = dirname(fileURLToPath(import.meta.url));
  const outputPath = resolve(cwd, "..", args.out);
  const index = await buildPageIndex({
    ...args,
    onProgress: async (partialIndex) => {
      await writePageIndex(outputPath, partialIndex);
      console.log(`Checkpoint: ${partialIndex.pages.length} page cursors`);
    },
  });
  await writePageIndex(outputPath, index);
  console.log(`Wrote ${index.pages.length} page cursors to ${outputPath}`);
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});