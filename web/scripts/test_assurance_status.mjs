/**
 * Pure-logic tests for src/lib/assuranceStatus.js.
 * The web app has no test runner — run with: node web/scripts/test_assurance_status.mjs
 * (package.json is type:module, so the .js lib imports cleanly.)
 */
import assert from "node:assert/strict";
import {
  metaForLabel,
  sortPropertiesByUrgency,
  summarizePortfolio,
} from "../src/lib/assuranceStatus.js";

let passed = 0;
const ok = (name, fn) => { fn(); passed++; console.log("ok -", name); };

ok("metaForLabel maps known labels", () => {
  assert.equal(metaForLabel("Protected").group, "protected");
  assert.equal(metaForLabel("Critical").group, "critical");
  assert.equal(metaForLabel("Pending Install").group, "pending");
  assert.equal(metaForLabel("Inactive / Deactivated").group, "inactive");
});

ok("metaForLabel falls back to Unknown", () => {
  assert.equal(metaForLabel("Nonsense").group, "unknown");
  assert.equal(metaForLabel(undefined).group, "unknown");
});

ok("summarizePortfolio counts by group", () => {
  const rows = [
    { assurance_label: "Protected" },
    { assurance_label: "Pending Install" },
    { assurance_label: "Pending Install" },
    { assurance_label: "Pending Install" },
  ];
  const c = summarizePortfolio(rows);
  // Matches the Integrity example: Protected 1, Attention 0, Critical 0, Pending 3
  assert.equal(c.protected, 1);
  assert.equal(c.attention, 0);
  assert.equal(c.critical, 0);
  assert.equal(c.pending, 3);
  assert.equal(c.total, 4);
});

ok("sortPropertiesByUrgency puts Critical then Attention on top", () => {
  const rows = [
    { site_name: "Z Protected", assurance_label: "Protected" },
    { site_name: "B Attention", assurance_label: "Attention Needed" },
    { site_name: "A Critical", assurance_label: "Critical" },
    { site_name: "C Pending", assurance_label: "Pending Install" },
  ];
  const order = sortPropertiesByUrgency(rows).map((r) => r.assurance_label);
  assert.deepEqual(order, ["Critical", "Attention Needed", "Protected", "Pending Install"]);
});

ok("sort is stable-ish by name within same label", () => {
  const rows = [
    { site_name: "Belle", assurance_label: "Critical" },
    { site_name: "Aspen", assurance_label: "Critical" },
  ];
  const names = sortPropertiesByUrgency(rows).map((r) => r.site_name);
  assert.deepEqual(names, ["Aspen", "Belle"]);
});

ok("sort does not mutate input", () => {
  const rows = [{ site_name: "x", assurance_label: "Protected" }];
  const copy = [...rows];
  sortPropertiesByUrgency(rows);
  assert.deepEqual(rows, copy);
});

console.log(`\n${passed} assertions passed.`);
