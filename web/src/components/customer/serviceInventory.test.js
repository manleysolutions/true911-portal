// Node built-in test runner (`npm test`).
// Canonical service inventory (#186b): machine-readable readiness replaces the
// "Being finalized by True911" placeholder ONLY when the backend sends it, and
// never becomes "certified", a service total or a connection total.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import {
  INVENTORY_PLACEHOLDER, INVENTORY_STATES, portfolioInventoryView, locationInventoryView,
} from "./serviceInventory.js";
import { opTiles } from "./commandCenter.js";
import { portfolioHero } from "./selfService.js";

const here = dirname(fileURLToPath(import.meta.url));
const SUMMARY_BASE = { locations_total: 45, operational_states: {} };
const INV = {
  locations_total: 45, locations_ready: 1, locations_partially_ready: 1,
  locations_being_finalized: 40, locations_no_services_on_record: 3,
  ready_services_by_type: [{ service: "Elevator", count: 2 }, { service: "Fire Alarm", count: 1 }],
  records_being_finalized: true, as_of: "2026-10-02T00:00:00Z",
};

test("no service_inventory: both tiles keep the original placeholder exactly", () => {
  const tile = opTiles(SUMMARY_BASE, null).find((t) => t.key === "services");
  assert.equal(tile.title, "Service inventory");
  assert.equal(tile.value, "Being finalized by True911");
  assert.equal(tile.detail, "Service and connection totals appear once your inventory is confirmed.");
  assert.equal(tile.numeric, false);
  const fact = portfolioHero(SUMMARY_BASE, null).facts.find((f) => f.key === "inventory");
  assert.deepEqual(fact, { key: "inventory", label: "Service inventory",
    value: "Being finalized by True911", pending: true });
  assert.equal(portfolioInventoryView(SUMMARY_BASE), null);
});

test("with service_inventory: location counts only - never a service or connection total", () => {
  const tile = opTiles({ ...SUMMARY_BASE, service_inventory: INV }, null).find((t) => t.key === "services");
  assert.equal(tile.title, "Service inventory");
  assert.equal(tile.value, "2 locations have confirmed inventory");
  assert.equal(tile.numeric, false);
  assert.equal(tile.detail, "1 ready · 1 partially ready · 40 being finalized · 3 no services on record");
  const text = JSON.stringify(tile);
  assert.doesNotMatch(text, /\b3 services?\b|connections?\b|certif/i);
});

test("no ready locations yet: still the placeholder wording", () => {
  const v = portfolioInventoryView({ service_inventory: { ...INV, locations_ready: 0, locations_partially_ready: 0 } });
  assert.equal(v.value, INVENTORY_PLACEHOLDER);
  assert.equal(v.pending, true);
  const one = portfolioInventoryView({ service_inventory: { ...INV, locations_ready: 1, locations_partially_ready: 0 } });
  assert.equal(one.value, "1 location has confirmed inventory");
});

test("location view: states, messages, requirements - never a number for FACP", () => {
  const v = locationInventoryView({
    state: "PARTIALLY_READY", message: "Some service inventory is confirmed. Additional records are being finalized by True911.",
    ready_services: [
      { service_ref: "lss_2kAAA", service: "Fire Alarm", name: "Fire alarm panel", required_paths: 2, telephone_number: null },
      { service_ref: "lss_2kBBB", service: "Elevator", name: "Elevator 1", required_paths: 1, telephone_number: "(555) 010-0001" },
    ] });
  assert.equal(v.state, INVENTORY_STATES.PARTIALLY_READY);
  assert.equal(v.pending, true);
  assert.equal(v.services[0].paths, "2 required communication paths");
  assert.equal(v.services[0].phone, null);
  assert.equal(v.services[1].phone, "(555) 010-0001");
  assert.equal(locationInventoryView(undefined), null);
  assert.equal(locationInventoryView({ state: "SOMETHING_NEW" }).state, INVENTORY_STATES.BEING_FINALIZED);
});

test("customer inventory UI never says 'certified'", () => {
  for (const f of ["serviceInventory.js", "LocationCommandCenter.jsx"]) {
    const src = readFileSync(join(here, f), "utf8").split("\n")
      .filter((l) => !l.trim().startsWith("//")).join("\n");
    assert.doesNotMatch(src, /certified/i, f);
  }
});

test("drawer: canonical mode replaces the legacy Services & Lines and header counts", () => {
  const v = locationInventoryView({ state: "PARTIALLY_READY", ready_services: [
    { service_ref: "lss_2kA", service: "Elevator", name: "Elevator 1", required_paths: 1, telephone_number: "(904) 689-0616" },
    { service_ref: "lss_2kB", service: "Elevator", name: "Elevator 2", required_paths: 1, telephone_number: "(904) 689-0656" }] });
  assert.equal(v.headline, "Some service inventory confirmed · additional records being finalized");
  assert.equal(v.finalizingNote, "Additional service records are being finalized by True911.");
  assert.deepEqual(v.services.map((s) => [s.label, s.phone, s.paths]),
    [["Elevator · Elevator 1", "(904) 689-0616", null], ["Elevator · Elevator 2", "(904) 689-0656", null]]);
  assert.equal(locationInventoryView({ state: "READY", ready_services: [] }).finalizingNote, null);
  const D = readFileSync(join(here, "LocationCommandCenter.jsx"), "utf8");
  // the legacy services / lines / devices block renders ONLY when canonical mode is off
  assert.match(D, /tab === "connections" && !invView && \(/);
  // the header says readiness, not "N monitored life-safety services · N telephone lines"
  assert.match(D, /\{invView\s*\?\s*invView\.headline/);
  // the canonical block carries no monitoring word, status pill or device rows
  const block = D.split('tab === "connections" && invView && (')[1].split("</Block>")[0];
  assert.doesNotMatch(block, /Monitored|statusWord|<Pill|equipment|Cpu/);
});

test("Confirm E911 review lists the canonical confirmed services when the API sends them", () => {
  const OPS = readFileSync(join(here, "LocationOperations.jsx"), "utf8");
  assert.match(OPS, /e\.services \? \(/);                         // canonical set first
  assert.match(OPS, /No confirmed service numbers on file yet/);  // fail-closed wording
  assert.match(OPS, /\(e\.service_numbers \|\| \[\]\)\.join\(" · "\) \|\| "No number on file yet"/);  // flag-off unchanged
});
