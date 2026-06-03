/**
 * Pure-logic tests for src/lib/tenantWarnings.js.
 * Run with: node web/scripts/test_tenant_warnings.mjs
 */
import assert from "node:assert/strict";
import { duplicateNameSet, tenantWarnings } from "../src/lib/tenantWarnings.js";

let passed = 0;
const ok = (name, fn) => { fn(); passed++; console.log("ok -", name); };

const TENANTS = [
  { tenant_id: "ipm", name: "Integrity Property Management", customers: 0, sites: 0, devices: 0, users: 0 },
  { tenant_id: "integrity-pm", name: "Integrity Property Management", customers: 1, sites: 4, devices: 3, users: 1 },
  { tenant_id: "default", name: "Default", customers: 0, sites: 0, devices: 0, users: 1 },
];

ok("duplicateNameSet finds shared names", () => {
  const dup = duplicateNameSet(TENANTS);
  assert.ok(dup.has("integrity property management"));
  assert.ok(!dup.has("default"));
});

ok("empty + duplicate-name tenant flagged", () => {
  const dup = duplicateNameSet(TENANTS);
  const w = tenantWarnings(TENANTS[0], dup); // ipm
  assert.ok(w.includes("Duplicate tenant name"));
  assert.ok(w.includes("Empty tenant"));
});

ok("active tenant only flagged for duplicate name", () => {
  const dup = duplicateNameSet(TENANTS);
  const w = tenantWarnings(TENANTS[1], dup); // integrity-pm
  assert.deepEqual(w, ["Duplicate tenant name"]);
});

ok("users but no sites", () => {
  const w = tenantWarnings({ name: "X", users: 1, sites: 0, customers: 0, devices: 0 }, new Set());
  assert.ok(w.includes("Has users but no sites"));
});

ok("sites but no customer", () => {
  const w = tenantWarnings({ name: "X", sites: 2, customers: 0, users: 1, devices: 0 }, new Set());
  assert.ok(w.includes("Has sites but no customer"));
});

ok("devices but no sites", () => {
  const w = tenantWarnings({ name: "X", devices: 3, sites: 0, customers: 1, users: 1 }, new Set());
  assert.ok(w.includes("Has devices but no sites"));
});

ok("healthy tenant has no warnings", () => {
  const w = tenantWarnings({ name: "Solo", customers: 1, sites: 4, devices: 3, users: 1 }, new Set());
  assert.deepEqual(w, []);
});

console.log(`\n${passed} assertions passed.`);
