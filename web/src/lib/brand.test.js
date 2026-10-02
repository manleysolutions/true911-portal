// Node built-in test runner (`npm test`) — no extra dependencies.
// True911 Beacon brand assets: present, vector, on-palette, correctly referenced,
// and never sourced from the brand_source concept boards.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const WEB = join(HERE, "..", "..");
const BRAND = join(WEB, "public", "brand");
const INDEX = readFileSync(join(WEB, "index.html"), "utf8");
const SVGS = ["true911-beacon.svg", "true911-beacon-reversed.svg", "true911-logo-horizontal.svg",
  "true911-logo-reversed.svg", "true911-logo-monochrome.svg", "favicon.svg"];
const PNGS = ["apple-touch-icon.png", "favicon-32.png"];
// Brand palette (D: Beacon) + its gradient steps and descriptor greys; mask black/white.
const ALLOWED = new Set(["#0b1f3b", "#2d8cff", "#60a9ff", "#ffffff", "#fff", "#000", "#1c6fe6", "#12408f",
  "#4a5b75", "#c9d6ea"]);

function walk(dir, out = []) {
  for (const n of readdirSync(dir)) {
    const p = join(dir, n);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (/\.(jsx?|tsx?|css|html)$/.test(n)) out.push(p);
  }
  return out;
}

test("the production Beacon family exists (and only what is needed)", () => {
  for (const f of [...SVGS, ...PNGS]) assert.ok(existsSync(join(BRAND, f)), f);
  assert.deepEqual(readdirSync(BRAND).sort(), [...SVGS, ...PNGS].sort(), "no stray or duplicate assets");
});

test("logo files are clean vectors on the brand palette — never red, amber or status colours", () => {
  for (const f of SVGS) {
    const s = readFileSync(join(BRAND, f), "utf8");
    assert.match(s, /^<svg xmlns="http:\/\/www\.w3\.org\/2000\/svg" viewBox="/, f);
    assert.doesNotMatch(s, /<image|base64|<script|<foreignObject|<text/i, `${f}: vector only, text outlined`);
    for (const c of s.match(/#[0-9a-f]{3,6}\b/gi) || []) assert.ok(ALLOWED.has(c.toLowerCase()), `${f}: ${c}`);
    assert.doesNotMatch(s, /#dc2626|#ef4444|#f59e0b|#d97706|#059669|red|amber/i, f);
  }
});

test("the master logo does not bake in the application descriptor", () => {
  for (const f of SVGS) {
    const s = readFileSync(join(BRAND, f), "utf8");
    assert.doesNotMatch(s, /Command Center/i, f);
  }
  assert.match(readFileSync(join(BRAND, "true911-logo-horizontal.svg"), "utf8"), /aria-label="True911 — Life-Safety Communications"/);
  assert.match(readFileSync(join(BRAND, "true911-beacon.svg"), "utf8"), /role="img" aria-label="True911"><title>True911<\/title>/);
});

test("assets are small enough to ship", () => {
  for (const f of SVGS) assert.ok(statSync(join(BRAND, f)).size < 40_000, f);
  for (const f of PNGS) assert.ok(statSync(join(BRAND, f)).size < 20_000, f);
});

test("the browser tab uses the Beacon favicon and the new brand title", () => {
  assert.match(INDEX, /<link rel="icon" type="image\/svg\+xml" href="\/brand\/favicon\.svg" \/>/);
  assert.match(INDEX, /<link rel="icon" type="image\/png" sizes="32x32" href="\/brand\/favicon-32\.png" \/>/);
  assert.match(INDEX, /<link rel="apple-touch-icon" href="\/brand\/apple-touch-icon\.png" \/>/);
  assert.match(INDEX, /<title>True911 — Life-Safety Communications<\/title>/);
  assert.doesNotMatch(INDEX, /True911\+|#dc2626/);
});

test("every /brand/ reference resolves; nothing loads the brand_source boards", () => {
  const files = [join(WEB, "index.html"), ...walk(join(WEB, "src"))].filter((p) => !p.endsWith(".test.js"));
  let refs = 0;
  for (const p of files) {
    const s = readFileSync(p, "utf8");
    assert.doesNotMatch(s, /brand_source/, p);
    for (const m of s.matchAll(/\/brand\/([\w.-]+)/g)) { refs++; assert.ok(existsSync(join(BRAND, m[1])), `${p} -> ${m[1]}`); }
  }
  assert.ok(refs >= 6, "header, login, internal shell and favicon all reference the brand assets");
});

test("customer header: Beacon + True911, descriptor kept, decorative mark is silent", () => {
  const shell = readFileSync(join(WEB, "src", "components", "customer", "command", "CustomerShell.jsx"), "utf8");
  assert.match(shell, /export const BEACON_REVERSED = "\/brand\/true911-beacon-reversed\.svg"/);
  assert.match(shell, /<img src=\{BEACON_REVERSED\} alt="" aria-hidden="true"/);
  assert.match(shell, />Life-Safety Command Center</);
  assert.match(shell, /True<span className="text-\[#60A9FF\]">911<\/span>/);
  assert.doesNotMatch(shell, /\bShield\b/, "the generic shield is gone from the customer header");
  assert.match(shell, /h-14 /, "header height unchanged (56px)");
  const auth = readFileSync(join(WEB, "src", "pages", "AuthGate.jsx"), "utf8");
  assert.equal((auth.match(/src="\/brand\/true911-beacon-reversed\.svg" alt="" aria-hidden="true"/g) || []).length, 4);
  assert.doesNotMatch(auth, /bg-red-600 rounded-2xl/);
});
