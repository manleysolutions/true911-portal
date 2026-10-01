// Node built-in test runner (`npm test`) — no extra dependencies.
// The web app has no DOM/React test harness, so the map's behavior lives in
// pure modules tested here; the few JSX wiring guarantees are asserted against
// the component source.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import {
  resolveTileConfig, TILE_CONFIG, OSM_TILE_URL, OSM_ATTRIBUTION, OSM_MAX_ZOOM,
} from "../../lib/mapTiles.js";
import { validPoint, mapMarkers, pointsSignature, filterLocations } from "./portfolioMap.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "..");
const VIEW = readFileSync(join(HERE, "CustomerAssuranceView.jsx"), "utf8");

const loc = (ref, point, extra = {}) => ({
  location_ref: ref, location: ref, map_point: point,
  op: { label: "Monitored", tone: "good" }, emergency_address_state: "Verified", ...extra,
});

// ── tile provider ────────────────────────────────────────────────────
test("default basemap is the keyless OSM standard tile server", () => {
  const cfg = resolveTileConfig({});
  assert.equal(cfg.url, "https://tile.openstreetmap.org/{z}/{x}/{y}.png");
  assert.equal(cfg.url, OSM_TILE_URL);
  assert.equal(cfg.maxZoom, OSM_MAX_ZOOM);
  assert.equal(cfg.provider, "osm");
  assert.equal(TILE_CONFIG.url, OSM_TILE_URL);   // no VITE_* env under node
});

test("required OpenStreetMap attribution is present and links to /copyright", () => {
  const { attribution } = resolveTileConfig({});
  assert.equal(attribution, OSM_ATTRIBUTION);
  assert.match(attribution, /OpenStreetMap/);
  assert.match(attribution, /contributors/);
  assert.match(attribution, /href="https:\/\/www\.openstreetmap\.org\/copyright"/);
});

test("no CARTO URL is requested unless one is explicitly configured", () => {
  assert.doesNotMatch(resolveTileConfig({}).url, /carto/i);
  assert.doesNotMatch(TILE_CONFIG.url, /carto/i);
  // and nothing in the app source hard-codes a CARTO basemap anymore
  const offenders = [];
  const walk = (dir) => {
    for (const name of readdirSync(dir)) {
      const p = join(dir, name);
      if (statSync(p).isDirectory()) walk(p);
      else if (/\.(jsx?|tsx?)$/.test(name) && !name.endsWith(".test.js")
        && /cartocdn|basemaps\.carto/i.test(readFileSync(p, "utf8"))) offenders.push(p);
    }
  };
  walk(SRC);
  assert.deepEqual(offenders, []);
});

test("a custom provider is used only with its own attribution, over https", () => {
  const custom = resolveTileConfig({
    VITE_MAP_TILE_URL: "https://tiles.example.com/{z}/{x}/{y}.png",
    VITE_MAP_TILE_ATTRIBUTION: "&copy; Example", VITE_MAP_TILE_MAX_ZOOM: "18",
  });
  assert.deepEqual({ ...custom }, {
    url: "https://tiles.example.com/{z}/{x}/{y}.png", attribution: "&copy; Example",
    maxZoom: 18, provider: "custom",
  });
  // URL without attribution → never shown uncredited; fall back to OSM
  assert.equal(resolveTileConfig({ VITE_MAP_TILE_URL: "https://tiles.example.com/{z}/{x}/{y}.png" }).url, OSM_TILE_URL);
  // plain http is refused
  assert.equal(resolveTileConfig({ VITE_MAP_TILE_URL: "http://x/{z}/{x}/{y}.png", VITE_MAP_TILE_ATTRIBUTION: "x" }).url, OSM_TILE_URL);
});

test("both Leaflet maps take their tiles from the shared config", () => {
  const deploy = readFileSync(join(SRC, "pages", "DeploymentMap.jsx"), "utf8");
  for (const src of [VIEW, deploy]) {
    assert.match(src, /url=\{TILE_CONFIG\.url\}/);
    assert.match(src, /attribution=\{TILE_CONFIG\.attribution\}/);
  }
});

// ── markers: only real server coordinates, once per building ─────────
test("missing-coordinate buildings are excluded and counted", () => {
  const { markers, hidden } = mapMarkers([
    loc("bldg:1", { lat: 40.7, lng: -74.0 }),
    loc("bldg:2", null),
    loc("bldg:3", undefined),
    loc("bldg:4", { lat: null, lng: -80 }),
  ]);
  assert.deepEqual(markers.map((m) => m.loc.location_ref), ["bldg:1"]);
  assert.equal(hidden, 3);
});

test("no fabricated fallback coordinates — unusable points are hidden, never substituted", () => {
  for (const p of [{ lat: 0, lng: 0 }, { lat: 91, lng: 0 }, { lat: 10, lng: -181 },
    { lat: "abc", lng: 1 }, { lat: NaN, lng: 1 }, {}]) {
    assert.equal(validPoint(loc("x", p)), null, JSON.stringify(p));
  }
  // a location with only city/state/zip/address still gets NO point
  assert.equal(validPoint(loc("x", null, { city: "Tampa", state: "FL", zip: "33602", address: "1 Main" })), null);
  const { markers, hidden } = mapMarkers([loc("x", null, { city: "Tampa", state: "FL" })]);
  assert.equal(markers.length, 0);
  assert.equal(hidden, 1);
});

test("the plotted point is exactly the server map_point", () => {
  assert.deepEqual(validPoint(loc("x", { lat: 37.77, lng: -122.42 })), [37.77, -122.42]);
  assert.deepEqual(validPoint(loc("x", { lat: "37.77", lng: "-122.42" })), [37.77, -122.42]);
});

test("an approved mapped building renders exactly once even if listed twice", () => {
  const { markers, hidden } = mapMarkers([
    loc("bldg:7", { lat: 30, lng: -90 }), loc("bldg:8", { lat: 31, lng: -91 }),
    loc("bldg:7", { lat: 30, lng: -90 }),   // e.g. duplicated across fetched pages
  ]);
  assert.deepEqual(markers.map((m) => m.loc.location_ref), ["bldg:7", "bldg:8"]);
  assert.equal(hidden, 0);
});

test("point signature is stable across re-fetches and changes with the point set", () => {
  const a = mapMarkers([loc("bldg:1", { lat: 1, lng: 2 }), loc("bldg:2", { lat: 3, lng: 4 })]).markers;
  const b = mapMarkers([loc("bldg:1", { lat: 1, lng: 2 }), loc("bldg:2", { lat: 3, lng: 4 })]).markers;
  assert.equal(pointsSignature(a), pointsSignature(b));        // new objects, same set → no refit
  const c = mapMarkers([loc("bldg:1", { lat: 1, lng: 2 })]).markers;
  assert.notEqual(pointsSignature(a), pointsSignature(c));     // filter changed the set → refit
});

test("missing-coordinate count stays visible in the map footer", () => {
  assert.match(VIEW, /\{hidden > 0 && <div[^>]*>\{hidden\} location\{hidden === 1 \? "" : "s"\} not shown on the map \(no coordinates on file\)\.<\/div>\}/);
});

// ── filters + list/map toggle ────────────────────────────────────────
test("status and E911 filters narrow the set the map plots", () => {
  const all = [
    loc("bldg:1", { lat: 1, lng: 1 }),
    loc("bldg:2", { lat: 2, lng: 2 }, { op: { label: "Needs attention", tone: "problem" } }),
    loc("bldg:3", null, { op: { label: "Needs attention", tone: "problem" }, emergency_address_state: "Verification Pending" }),
  ];
  assert.equal(filterLocations(all, {}).length, 3);
  const attention = filterLocations(all, { status: "Needs attention" });
  assert.deepEqual(attention.map((l) => l.location_ref), ["bldg:2", "bldg:3"]);
  const m = mapMarkers(attention);
  assert.deepEqual(m.markers.map((x) => x.loc.location_ref), ["bldg:2"]);
  assert.equal(m.hidden, 1);
  assert.deepEqual(filterLocations(all, { e911: "Verification Pending" }).map((l) => l.location_ref), ["bldg:3"]);
  assert.deepEqual(filterLocations(all, { status: "Monitored", e911: "Verification Pending" }), []);
});

test("list and map views share the filtered set and toggle on view state", () => {
  assert.match(VIEW, /filterLocations\(locations, \{ status: statusFilter, e911: e911Filter \}\)/);
  assert.match(VIEW, /view === "map" \? \(\s*<div className="p-4"><PortfolioMap locations=\{filtered\}/);
  assert.match(VIEW, /\{filtered\.map\(\(loc\) =>/);
  assert.match(VIEW, /onClick=\{\(\) => setView\("list"\)\}/);
  assert.match(VIEW, /onClick=\{\(\) => setView\("map"\)\}/);
});

test("status marker semantics are unchanged", () => {
  assert.match(VIEW, /\["Monitored", "good"\], \["Needs attention", "problem"\], \["Being reconciled \/ confirming", "neutral"\]/);
});
