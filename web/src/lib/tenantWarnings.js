/**
 * Pure helpers for the Admin → Tenants table warning badges.
 * Operate on the read-only counts the /admin/tenants endpoint already returns.
 * No React, no I/O → trivially testable.
 */

/** Names (lowercased) that appear on more than one tenant. */
export function duplicateNameSet(tenants) {
  const counts = {};
  for (const t of tenants || []) {
    const n = String(t.name || "").trim().toLowerCase();
    if (!n) continue;
    counts[n] = (counts[n] || 0) + 1;
  }
  return new Set(Object.entries(counts).filter(([, c]) => c > 1).map(([n]) => n));
}

/**
 * Non-blocking diagnostic warnings for one tenant row.
 * dupNames = duplicateNameSet(tenants).
 */
export function tenantWarnings(t, dupNames) {
  const c = (k) => Number((t && t[k]) || 0);
  const name = String((t && t.name) || "").trim().toLowerCase();
  const w = [];

  if (dupNames && dupNames.has(name)) w.push("Duplicate tenant name");
  if (c("customers") + c("sites") + c("devices") + c("users") === 0) w.push("Empty tenant");
  if (c("users") > 0 && c("sites") === 0) w.push("Has users but no sites");
  if (c("sites") > 0 && c("customers") === 0) w.push("Has sites but no customer");
  if (c("devices") > 0 && c("sites") === 0) w.push("Has devices but no sites");
  return w;
}
