import { useEffect, useRef, useState } from "react";

const PDS_API = "/api/discovery";
const PROJECTS_API = "/api/projects";
const PAGE_INDEX_URL = "/pds4-page-index.json";

const SOL_KEY = "mars2020:Observation_Information.mars2020:sol_number";
const FILE_KEY = "pds:File.pds:file_name";
const START_KEY = "pds:Time_Coordinates.pds:start_date_time";
const SORT_KEY = "ops:Harvest_Info.ops:harvest_date_time";
const BROWSE_KEY = "ref_lid_browse";
const BROWSE_REF_KEY = "ops:Data_File_Info.ops:file_ref";

const DIRECT_THUMB_KEYS = [
  "tublurl",
  "thumbUrl",
  "thumb_url",
  "thumbnail",
  "thumbnail_url",
  BROWSE_REF_KEY,
];

// const Q =
//   `((ref_lid_investigation eq "urn:nasa:pds:context:investigation:mission.mars2020") and ` +
//   `((ref_lid_instrument eq "urn:nasa:pds:context:instrument:mars2020.mastcamz") and ` +
//   `((ref_lid_target eq "urn:nasa:pds:context:target:planet.mars") and ` +
//   `(${START_KEY} ge "2021-02-18T00:00:00Z"))))`;
const Q = `((ref_lid_investigation eq "urn:nasa:pds:context:investigation:mission.mars2020") and ` +
  `(ref_lid_instrument eq "urn:nasa:pds:context:instrument:mars2020.mastcamz") and ` +
  `(${START_KEY} ge "2021-02-18T00:00:00Z"))`;


const FIELDS = [
  "lid",
  "title",
  START_KEY,
  SOL_KEY,
  FILE_KEY,
  SORT_KEY,
  BROWSE_KEY,
].join(",");

function toItem(product) {
  const p = product.properties ?? {};

  const filename = (p[FILE_KEY] ?? [])[0];
  const id = filename
    ? filename.replace(/\.[^.]+$/, "")
    : String(product.id ?? "").split(":").pop();

  const sol = (p[SOL_KEY] ?? [])[0];
  const browseLid = (p[BROWSE_KEY] ?? [])[0] ?? null;

  const directThumb = DIRECT_THUMB_KEYS
    .map((key) => (p[key] ?? [product?.[key]])[0])
    .find((value) => typeof value === "string" && value.trim());

  return {
    id,
    lid: (p.lid ?? [product.id])[0],
    title: sol != null ? `sol=${String(sol).padStart(4, "0")}` : id.slice(0, 12),
    thumbUrl: directThumb ?? null,
    previewSource: directThumb ? "pds" : null,
    browseLid,
  };
}

async function resolveThumbUrls(items, signal) {
  const resolved = await Promise.all(
    items.map(async (item) => {
      if (!item.browseLid) return item;
      try {
        const r = await fetch(
          `${PDS_API}/products/${encodeURIComponent(item.browseLid)}`,
          { signal }
        );
        if (!r.ok) return item;
        const json = await r.json();
        const props =
          json.properties ??
          (json.data ?? [null])[0]?.properties ??
          json.data?.properties ??
          {};
        const ref = (props[BROWSE_REF_KEY] ?? [])[0] ?? null;
        return ref ? { ...item, thumbUrl: ref, previewSource: "pds" } : item;
      } catch (e) {
        if (e.name !== "AbortError") {
          console.warn("thumb fetch failed", item.browseLid, e);
        }
        return item;
      }
    })
  );
  return resolved;
}

async function resolveGeneratedPreviewUrls(items, signal) {
  const missing = items.filter((item) => !item.thumbUrl && item.lid);
  if (missing.length === 0) return items;

  try {
    const generatedPreviewKeys = [
      ...new Set(
        missing
          .flatMap((item) => [item.lid, item.id])
          .filter((value) => typeof value === "string" && value.trim())
      ),
    ];
    const lids = generatedPreviewKeys.join(",");
    const response = await fetch(
      `${PROJECTS_API}/generated-previews?lids=${encodeURIComponent(lids)}`,
      { signal }
    );

    if (!response.ok) return items;

    const generatedByLid = await response.json();
    return items.map((item) => {
      if (item.thumbUrl) return item;
      const generatedPreview = generatedByLid?.[item.lid] ?? generatedByLid?.[item.id];
      const generated = generatedPreview?.thumb_url;
      const previewSource = generatedPreview?.preview_source ?? "generated_transform";
      return generated ? { ...item, thumbUrl: generated, previewSource } : item;
    });
  } catch (e) {
    if (e.name !== "AbortError") {
      console.warn("generated preview fetch failed", e);
    }
    return items;
  }
}

function getSortValue(product, sortKey = SORT_KEY) {
  const p = product?.properties ?? {};
  const val = (p[sortKey] ?? [])[0];
  // If sorting by sol, ensure it's a number for proper comparison
  return sortKey === SOL_KEY && val != null ? Number(val) : val ?? null;
}

function maxKey(map) {
  const keys = Array.from(map.keys());
  return keys.length ? Math.max(...keys) : 1;
}

async function loadPageIndex(pageSize, signal) {
  try {
    const response = await fetch(PAGE_INDEX_URL, { cache: "no-store", signal });
    if (!response.ok) return null;

    const json = await response.json();
    if (json.pageSize !== pageSize || !Array.isArray(json.pages)) return null;

    const cursorByPage = new Map(
      json.pages
        .filter((entry) => Number.isInteger(entry.page))
        .map((entry) => [entry.page, entry.searchAfter ?? null])
    );
    return {
      cursorByPage,
      indexedMaxPage: maxKey(cursorByPage),
    };
  } catch (e) {
    if (e.name !== "AbortError") {
      console.warn("page index fetch failed", e);
    }
    return null;
  }
}

function getStaticSearchAfter(staticPageIndex, page) {
  if (!staticPageIndex?.cursorByPage?.has(page)) return undefined;
  return staticPageIndex.cursorByPage.get(page);
}

export default function usePds4Products(page, pageSize) {
  const cursorByPageRef = useRef(new Map([[1, null]]));
  const pageCacheRef = useRef(new Map());
  const staticCursorByPageRef = useRef(null);
  const staticPageIndexLoadRef = useRef(null);
  const lastPageSizeRef = useRef(pageSize);

  const [state, setState] = useState({
    items: [],
    total: 0,
    loading: true,
    error: null,
    reachableMaxPage: 1,
    indexedMaxPage: 1,
  });

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();

    if (lastPageSizeRef.current !== pageSize) {
      lastPageSizeRef.current = pageSize;
      cursorByPageRef.current = new Map([[1, null]]);
      pageCacheRef.current = new Map();
      staticCursorByPageRef.current = null;
      staticPageIndexLoadRef.current = null;
    }

    const cachedItems = pageCacheRef.current.get(page);
    if (cachedItems) {
      setState((s) => ({
        ...s,
        items: cachedItems,
        loading: false,
        error: null,
        reachableMaxPage: maxKey(cursorByPageRef.current),
      }));
      return;
    }

    async function run() {
      let searchAfter = cursorByPageRef.current.get(page);
      if (page !== 1 && (searchAfter == null || searchAfter === "")) {
        if (!staticPageIndexLoadRef.current) {
          staticPageIndexLoadRef.current = loadPageIndex(pageSize, controller.signal);
        }

        staticCursorByPageRef.current = await staticPageIndexLoadRef.current;
        if (cancelled) return;

        const staticSearchAfter = getStaticSearchAfter(staticCursorByPageRef.current, page);
        if (staticSearchAfter != null && staticSearchAfter !== "") {
          cursorByPageRef.current.set(page, staticSearchAfter);
          searchAfter = staticSearchAfter;
        } else {
          setState((s) => ({
            ...s,
            loading: false,
            error:
              `Page ${page} is not reachable yet. ` +
              `Generate public/pds4-page-index.json to open this page directly, ` +
              `or visit pages in order so cursor pagination can discover it. ` +
              `Last indexed page: ${staticCursorByPageRef.current?.indexedMaxPage ?? 1}.`,
            reachableMaxPage: maxKey(cursorByPageRef.current),
            indexedMaxPage: staticCursorByPageRef.current?.indexedMaxPage ?? 1,
          }));
          return;
        }
      }

      setState((s) => ({
        ...s,
        loading: true,
        error: null,
      }));

      // const params = new URLSearchParams({
      //   q: Q,
      //   fields: FIELDS,
      //   limit: String(pageSize),
      //   sort: SORT_KEY,
      // });

      const params = new URLSearchParams({
        q: Q,
        fields: FIELDS,
        limit: String(pageSize),
        sort: SOL_KEY,        // ← "mars2020:Observation_Information.mars2020:sol_number"
             // ← optional: newest sols first (680 before 72)
      });

      if (page !== 1 && searchAfter != null) {
        params.set("search-after", String(searchAfter));
      }

      const response = await fetch(`${PDS_API}/classes/observational?${params.toString()}`);
      
      if (!response.ok) {
        const text = await response.text();
        throw new Error(`PDS API ${response.status}: ${text}`);
      }

      const json = await response.json();
      if (cancelled) return;
      // === DEBUG BLOCK START ===
      console.group("🔍 PDS API Response Debug");
      console.log("Total hits:", json.summary?.hits);
      console.log("Items returned:", json.data?.length);
      if (json.data?.[0]) {
        console.log("First item keys:", Object.keys(json.data[0]));
        console.log("First item properties keys:", Object.keys(json.data[0].properties ?? {}));
        
        // Check for sol_number in any form
        const props = json.data[0].properties ?? {};
        const solCandidates = Object.keys(props).filter(k => k.toLowerCase().includes('sol'));
        console.log("Sol-related fields found:", solCandidates);
        
        // Try to extract sol with fallback paths
        const sol1 = props[SOL_KEY]?.[0];
        const sol2 = props["mars2020:sol_number"]?.[0];
        const sol3 = props["sol_number"]?.[0];
        console.log("Sol extraction attempts:", { [SOL_KEY]: sol1, "mars2020:sol_number": sol2, "sol_number": sol3 });
        
        // Check filename for sequence ID
        const fname = (props[FILE_KEY]?.[0] ?? "");
        console.log("Filename sample:", fname);
        console.log("Contains zcam?", fname.includes("zcam"));
      }
      console.groupEnd();
      // === DEBUG BLOCK END ===
      const raw = json.data ?? [];
      const items = raw.map(toItem);

      const lastRaw = raw.length ? raw[raw.length - 1] : null;
      const nextCursor = getSortValue(lastRaw, SOL_KEY);  // ← pass the active sort key
      if (nextCursor) {
        cursorByPageRef.current.set(page + 1, nextCursor);
      }

      // Render list immediately (thumbs are null for now)
      setState((s) => ({
        ...s,
        items,
        total: json.summary?.hits ?? s.total,
        loading: false,
        error: null,
        reachableMaxPage: maxKey(cursorByPageRef.current),
        indexedMaxPage: staticCursorByPageRef.current?.indexedMaxPage ?? s.indexedMaxPage,
      }));

      // Resolve thumbnails in parallel
      const pdsThumbs = await resolveThumbUrls(items, controller.signal);
      const itemsWithThumbs = await resolveGeneratedPreviewUrls(pdsThumbs, controller.signal);
      if (cancelled) return;

      // Generated previews can appear after a pipeline finishes, so avoid caching
      // incomplete pages that still have previewless products.
      if (itemsWithThumbs.every((item) => item.thumbUrl)) {
        pageCacheRef.current.set(page, itemsWithThumbs);
      }

      setState((s) => ({ ...s, items: itemsWithThumbs }));
    }

    run().catch((err) => {
      if (cancelled) return;

      setState((s) => ({
        ...s,
        loading: false,
        error: err.message || "Unknown error",
      }));
    });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [page, pageSize]);

  return state;
}
