// ════════════════════════════════════════════════════════════════════
// Basemap tile configuration — the ONE place every Leaflet map in the app
// gets its tile source from.
//
// Default: the OpenStreetMap Foundation standard tile server.  Keyless, and
// permitted for low-volume use under the OSMF Tile Usage Policy
// (https://operations.osmfoundation.org/policies/tiles/), which requires:
//   • visible attribution "© OpenStreetMap contributors" linking to
//     /copyright — never remove or hide it;
//   • a valid HTTP Referer (browsers send one by default);
//   • no bulk download / prefetch, and honoring the server's cache headers;
//   • max zoom 19.
//
// History: the maps used CARTO "light_all" without a key.  CARTO now serves
// an "API KEY REQUIRED" placeholder PNG (HTTP 200) for every keyless tile,
// which is what covered the customer map.  No decision required CARTO.
//
// Override per deployment (Vite build-time env), all three together:
//   VITE_MAP_TILE_URL          e.g. https://tiles.example.com/{z}/{x}/{y}.png
//   VITE_MAP_TILE_ATTRIBUTION  the provider's REQUIRED attribution HTML
//   VITE_MAP_TILE_MAX_ZOOM     optional, defaults to 19
// Anything in a VITE_* variable ships to every browser.  A provider token in
// VITE_MAP_TILE_URL must be a PUBLIC, domain-restricted client token — never a
// secret or server credential.
// ════════════════════════════════════════════════════════════════════

export const OSM_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
export const OSM_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
export const OSM_MAX_ZOOM = 19;

// Tile errors before the map tells the viewer the background is unavailable.
export const TILE_FAILURE_THRESHOLD = 4;

const DEFAULT_TILES = Object.freeze({
  url: OSM_TILE_URL, attribution: OSM_ATTRIBUTION, maxZoom: OSM_MAX_ZOOM, provider: "osm",
});

function viteEnv() {
  try { return import.meta.env || {}; } catch { return {}; }
}

/** Resolve the basemap tile config from an env object (defaults to Vite's).
 *  A custom URL is honored only with its own attribution — a provider is never
 *  shown without the credit its terms require. */
export function resolveTileConfig(env = viteEnv()) {
  const url = (env.VITE_MAP_TILE_URL || "").trim();
  const attribution = (env.VITE_MAP_TILE_ATTRIBUTION || "").trim();
  if (!url || !attribution || !/^https:\/\//i.test(url)) return DEFAULT_TILES;
  const z = Number.parseInt(env.VITE_MAP_TILE_MAX_ZOOM, 10);
  return Object.freeze({
    url, attribution, maxZoom: Number.isFinite(z) && z > 0 ? z : OSM_MAX_ZOOM, provider: "custom",
  });
}

export const TILE_CONFIG = resolveTileConfig();
