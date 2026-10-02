// Per-route SEO basics (title, description, canonical, OpenGraph) + first-touch
// attribution capture + page_view on the event boundary.  No SSR, no vendor.
import { useEffect } from "react";
import { captureAttribution, track } from "@/lib/acquisition";

export const SITE_ORIGIN = "https://www.true911.com";

function meta(attr, key, content) {
  let el = document.head.querySelector(`meta[${attr}="${key}"]`);
  if (!el) { el = document.createElement("meta"); el.setAttribute(attr, key); document.head.appendChild(el); }
  el.setAttribute("content", content);
}

export default function usePublicPage({ title, description, path }) {
  useEffect(() => {
    const full = title.includes("True911") ? title : `${title} | True911`;
    document.title = full;
    meta("name", "description", description);
    meta("property", "og:title", full);
    meta("property", "og:description", description);
    meta("property", "og:type", "website");
    meta("property", "og:url", SITE_ORIGIN + path);
    let link = document.head.querySelector('link[rel="canonical"]');
    if (!link) { link = document.createElement("link"); link.setAttribute("rel", "canonical"); document.head.appendChild(link); }
    link.setAttribute("href", SITE_ORIGIN + path);
    captureAttribution();
    track("page_view", { path });
  }, [title, description, path]);
}
