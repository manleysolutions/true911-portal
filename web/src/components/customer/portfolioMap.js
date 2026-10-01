// Pure logic for the customer portfolio map (no React / Leaflet) so it is
// testable with `node --test`.
//
// The map plots ONLY the server-provided `map_point` of each location.  It
// never geocodes, never guesses, and never substitutes a fallback coordinate:
// a location without a usable point is counted as "not shown on the map" so
// the notice stays truthful.  Fixing those locations is canonical
// address/geocoding work, not a map concern.

/** The location's server map point as [lat, lng], or null when absent or not a
 *  real coordinate (non-numeric, out of range, or the 0,0 null-island
 *  placeholder — the same rule as the API's serialize._map_point). */
export function validPoint(loc) {
  const p = loc?.map_point;
  if (!p || p.lat == null || p.lng == null) return null;
  const lat = Number(p.lat), lng = Number(p.lng);
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
  if (lat < -90 || lat > 90 || lng < -180 || lng > 180) return null;
  if (lat === 0 && lng === 0) return null;
  return [lat, lng];
}

/** Split locations into plotted markers (one per location_ref, first wins) and
 *  the count of locations that cannot be shown. */
export function mapMarkers(locations) {
  const seen = new Set();
  const markers = [];
  let hidden = 0;
  for (const loc of locations || []) {
    if (!loc?.location_ref || seen.has(loc.location_ref)) continue;
    seen.add(loc.location_ref);
    const point = validPoint(loc);
    if (point) markers.push({ loc, point });
    else hidden += 1;
  }
  return { markers, hidden };
}

/** A stable string for the plotted point set — the map refits only when this
 *  changes, not on every render / poll / hover. */
export function pointsSignature(markers) {
  return markers.map((m) => `${m.loc.location_ref}@${m.point[0]},${m.point[1]}`).join("|");
}

/** The Locations status / E911 filter shared by the list and the map. */
export function filterLocations(locations, { status = "all", e911 = "all" } = {}) {
  return (locations || []).filter((l) => {
    if (status !== "all" && l.op?.label !== status) return false;
    if (e911 !== "all" && l.emergency_address_state !== e911) return false;
    return true;
  });
}
