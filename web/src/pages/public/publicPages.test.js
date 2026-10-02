// Node built-in test runner (`npm test`) — source-level guards for the public site.
// D-030 truth rules on public claims, D-031 durable-before-success, accessibility basics.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const WEB = join(HERE, "..", "..", "..");
const read = (f) => readFileSync(join(HERE, f), "utf8");
const PAGES = ["LandingPage.jsx", "True911Platform.jsx", "Quote.jsx", "GetStarted.jsx", "PublicNav.jsx",
  "PublicFooter.jsx", "LeadForm.jsx", "Register.jsx"];
const MARKETING = ["LandingPage.jsx", "True911Platform.jsx", "Quote.jsx", "GetStarted.jsx", "PublicNav.jsx", "PublicFooter.jsx"];

// Copy text only (strip comments) so the guard tests what visitors read.
const copy = (src) => src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "").replace(/\{\/\*[\s\S]*?\*\/\}/g, "");

const CLASS_D = [
  /guarantee/i, /never go(es)? dark/i, /stay online\.? period/i, /in seconds/i, /instant(ly)? (alert|reroute)/i,
  /enforce[sd]? (e911|compliance|kari)/i, /verified and enforced/i, /with every (emergency )?call/i,
  /inspection-proof/i, /automatic(ally)? (compliance|generated) report/i, /four (independent )?paths/i,
  /4-path/i, /satellite/i, /zero single points? of failure/i, /no vendor lock-in/i, /made in usa/i,
  /ndaa/i, /\bTAA\b/, /free audit/i, /True911\+/, /compliance gaps/i, /audit-ready/i,
];

test("public pages carry no Class D claims", () => {
  for (const f of MARKETING) {
    const text = copy(read(f));
    for (const re of CLASS_D) assert.doesNotMatch(text, re, `${f}: ${re}`);
  }
});

test("Kari's Law / RAY BAUM'S appear only as neutral context, never as a compliance determination", () => {
  for (const f of MARKETING) {
    const text = copy(read(f));
    assert.doesNotMatch(text, /(?<!not\s+)(certif(y|ies|ied)|ensur(e|es)|verif(y|ies)) (your )?(compliance|e911)/i, f);
    assert.doesNotMatch(text, /compliant with (kari|ray baum)/i, f);
  }
  assert.match(copy(read("LandingPage.jsx")), /does not\s+certify compliance/);
});

test("no form shows success outside a server receipt (no false success on 404 / network)", () => {
  for (const f of ["Quote.jsx", "GetStarted.jsx", "LeadForm.jsx"]) {
    const src = read(f);
    assert.doesNotMatch(src, /setSubmitted\(true\)/, f);
    assert.doesNotMatch(src, /status === 404/, f);
    assert.doesNotMatch(src, /Network error/, f);
  }
  const lf = read("LeadForm.jsx");
  assert.match(lf, /submitAcquisition\(/);
  assert.match(lf, /setReceipt\(r\)/);
  for (const f of ["Quote.jsx", "GetStarted.jsx"]) assert.match(read(f), /\{receipt \? \(/, f);
});

test("forms are accessible: labelled controls, described errors, pressed toggles, 44px targets", () => {
  const lf = read("LeadForm.jsx");
  assert.match(lf, /<label htmlFor=\{id\}/);
  assert.match(lf, /aria-describedby=\{describedBy\}/);
  assert.match(lf, /aria-invalid=/);
  assert.match(lf, /aria-pressed=\{on\}/);
  assert.match(lf, /role="alert"/);
  assert.match(lf, /min-h-\[44px\]/);
  for (const f of ["Quote.jsx", "GetStarted.jsx"]) {
    const src = read(f);
    assert.doesNotMatch(src, /<input /, `${f}: raw inputs bypass the labelled Field`);
    assert.match(src, /<Honeypot /, f);
  }
});

test("the dead flyer CTA is gone and no PDF was fabricated", () => {
  for (const f of PAGES) assert.doesNotMatch(read(f), /true911-flyer\.pdf|Download Full Overview/, f);
  assert.equal(existsSync(join(WEB, "public", "downloads", "true911-flyer.pdf")), false);
});

test("login is never a hero/final CTA; primary CTA is the Life-Safety Assessment", () => {
  for (const f of ["LandingPage.jsx", "True911Platform.jsx"]) {
    const src = read(f);
    assert.doesNotMatch(src, /to="\/login"/, f);
    assert.match(src, /Start a Life-Safety Assessment/, f);
  }
  assert.match(read("PublicNav.jsx"), /to="\/login"/);           // login stays in the header
});

test("quote vocabulary is life-safety, mirrored by the server allow-lists", () => {
  const q = read("Quote.jsx");
  for (const v of ["elevator", "fire_alarm", "emergency_phone", "copper_replacement", "visibility", "e911_readiness"])
    assert.match(q, new RegExp(`value: "${v}"`));
  assert.doesNotMatch(q, /NOC|Containers|Edge Compute|service_tier|Full NOC/);
  const svc = readFileSync(join(WEB, "..", "api", "app", "services", "acquisition_service.py"), "utf8");
  for (const v of ["elevator", "fire_alarm", "emergency_phone", "copper_replacement", "visibility", "e911_readiness"])
    assert.match(svc, new RegExp(`"${v}"`));
});

test("SEO baseline exists; the registration flow is not indexed", () => {
  const robots = readFileSync(join(WEB, "public", "robots.txt"), "utf8");
  assert.match(robots, /Disallow: \/register/);
  assert.match(robots, /Sitemap: https:\/\/www\.true911\.com\/sitemap\.xml/);
  const sm = readFileSync(join(WEB, "public", "sitemap.xml"), "utf8");
  for (const p of ["/", "/get-started", "/quote", "/true911-platform"]) assert.ok(sm.includes(`https://www.true911.com${p}<`), p);
  assert.doesNotMatch(sm, /register|login/);
  const idx = readFileSync(join(WEB, "index.html"), "utf8");
  assert.match(idx, /rel="canonical"/);
  assert.match(idx, /property="og:title"/);
});

test("the portal is code-split away from the public entry", () => {
  const app = readFileSync(join(WEB, "src", "App.jsx"), "utf8");
  assert.match(app, /lazy\(\(\) => import\('\.\/AuthenticatedApp'\)\)/);
  assert.match(app, /lazy\(\(\) => import\('\.\/pages\/AuthGate'\)\)/);
  assert.doesNotMatch(app, /pages\.config/);
});
