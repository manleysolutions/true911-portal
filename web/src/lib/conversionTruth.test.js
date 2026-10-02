// Node built-in test runner (`npm test`).
// CT-1 / CT-2: a planned (converted, not yet installed) site reads as neutral
// "Being set up" — never green "Connected" or red — and the self-service
// invite role lands in the customer Command Center.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import {
  CUSTOMER_STATUS, customerStatusLabel, isCustomerApiRole, isCustomerRole, toCustomerStatus,
} from "./attention.js";

const SRC = join(dirname(fileURLToPath(import.meta.url)), "..");
const read = (p) => readFileSync(join(SRC, p), "utf8");

test("a planned site reads 'Being set up', not Connected", () => {
  const key = toCustomerStatus({ status: "Pending Install" });
  assert.equal(key, CUSTOMER_STATUS.BEING_SET_UP);
  assert.equal(customerStatusLabel(key), "Being set up");
  assert.notEqual(customerStatusLabel(key), "Connected");
});

test("independent evidence still wins: a reporting planned site is shown as reporting", () => {
  assert.equal(toCustomerStatus({ status: "Pending Install", canonical_status: "connected" }),
    CUSTOMER_STATUS.REPORTING);
  assert.equal(toCustomerStatus({ status: "Pending Install", canonical_status: "attention" }),
    CUSTOMER_STATUS.ATTENTION_NEEDED);
});

test("planned status is neutral in every internal badge (never green or red)", () => {
  const badge = read("components/ui/StatusBadge.jsx");
  const line = badge.split("\n").find((l) => l.includes("'Pending Install'"));
  assert.ok(line, "StatusBadge maps Pending Install");
  assert.match(line, /slate/);
  assert.doesNotMatch(line, /emerald|red-/);
  const site = read("pages/CommandSite.jsx");
  assert.match(site, /cat\.status === "pending" \? "text-slate-400"/);
});

test("CUSTOMER_ADMIN routes to the customer Command Center; legacy User does not", () => {
  assert.equal(isCustomerApiRole("CUSTOMER_ADMIN"), true);      // CustomerShell (Layout.jsx)
  assert.equal(isCustomerApiRole("User"), false);               // legacy internal shell
  assert.equal(isCustomerRole("CUSTOMER_ADMIN"), true);
});
