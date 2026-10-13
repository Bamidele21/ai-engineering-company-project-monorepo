# Pre-Performance Audit — Nexova Website & Backoffice

Baseline ("before") Lighthouse audit of the two live Nexova frontends, analysed by form factor
from the four raw reports in this folder. No code or configuration was changed to produce it —
this document is the **measure → analyse** half of the audit loop and is the reference the
`REPORT.md` "after" comparison will be measured against.

> Naming: this baseline is `pre-performance-audit.md`. The challenge deliverables are `AUDIT.md`
> (analysis) and `REPORT.md` (applied corrections + measured impact); this file is the raw,
> unfiltered evidence behind `AUDIT.md`.

---

## 1. Scope, environment & measurement caveat

| Item | Value |
| --- | --- |
| Tool | Lighthouse 13.4.1 (Chrome DevTools channel) |
| Browser | Chrome 154 (Windows 10) |
| Capture dates (UTC) | backoffice-mobile `2026-10-12T23:52:30Z` · website-desktop `2026-10-13T00:05:22Z` · website-mobile `2026-10-13T00:36:14Z` · backoffice-desktop `2026-10-13T00:37:22Z` |
| Pages audited | Website `/` (`http://localhost:3000/`) · Backoffice `/` (`http://localhost:3001/`) |
| Form factors | Mobile (simulated 4× CPU, 150 ms RTT, 1638 Kbps) and Desktop (simulated 1× CPU, 40 ms RTT, 10240 Kbps) |
| Categories | Performance · Accessibility · Best Practices · SEO |

### ⚠️ Caveat — these numbers are from the **dev** servers, not a production build

Both URLs are served by `npm run dev` (`uis/start.sh:10,13` runs `next dev --webpack`). Every
report contains the fingerprints of a development bundle:

- A ~3,005 KiB **unminified** `_next/static/chunks/main-app.js` (see §4.1).
- The `next-devtools` chunk executing on the page.
- `webpack.js` shipped unminified (79.9% wasted bytes).
- Missing source maps for large first-party JS.

The React DevTools Chrome extension (`chrome-extension://fmkadmapgofadopljbjfkapdkoienihi/…`) also
leaked into `bootup-time`, `unused-javascript` and `valid-source-maps`, slightly inflating those
audits.

**Consequence:** the absolute scores below are pessimistic and none of the four Performance scores
should be treated as shippable. The recommended action is to re-baseline on a production build
(`next build && next start`) before applying fixes, and to close the loop against that baseline.
The measurements still correctly identify the *relative* hotspots (hero image, render gating, bundle
weight), which is what this audit prioritises.

---

## 2. Lighthouse score summary

Scores are Lighthouse's 0–100 scale (Performance is weighted; the other three are pass/fail audits).

| App | Mode | Performance | Accessibility | Best Practices | SEO |
| --- | --- | --- | --- | --- | --- |
| **Website** | Desktop | **72** | 96 | 100 | **92** |
| **Website** | Mobile | **53** | 96 | 100 | 100 |
| **Backoffice** | Desktop | **60** | 95 | 100 | 100 |
| **Backoffice** | Mobile | **46** | 95 | 100 | 100 |

Nothing meets the `Performance ≥ 90` production benchmark. Mobile is materially worse than desktop
in every case, which points at network/CPU-bound work (bundle size + unoptimised hero image) rather
than server response time (TTFB is healthy everywhere — see §3).

### Core Web Vitals & key timings

| Metric | Target | Website DT | Website MOB | Backoffice DT | Backoffice MOB |
| --- | --- | --- | --- | --- | --- |
| FCP | — | 0.4 s | 1.2 s | 0.3 s | 0.8 s |
| **LCP** | **< 2.5 s** | **3.1 s ❌** | **17.7 s ❌** | **3.6 s ❌** | **20.1 s ❌** |
| **TBT** (INP proxy) | **< 200 ms** | 270 ms ❌ | 1,020 ms ❌ | 460 ms ❌ | 2,440 ms ❌ |
| **CLS** | **< 0.1** | 0.003 ✅ | 0 ✅ | 0.0001 ✅ | 0 ✅ |
| Speed Index | — | 0.6 s | 1.6 s | 1.0 s | 2.6 s |
| Time to Interactive | — | 5.1 s | 29.5 s | 3.6 s | 20.3 s |
| **TTFB** (server response) | — | 127 ms ✅ | 493 ms ✅ | 127 ms ✅ | 148 ms ✅ |
| Total byte weight | — | 6,369 KiB | 6,369 KiB | 3,329 KiB | 3,329 KiB |
| Main-thread work | — | 1.5 s | 5.3 s | 0.9 s | 3.9 s |
| JS execution (bootup) | — | 0.7 s | 2.6 s | 0.6 s | 2.9 s |
| Max Potential FID | — | 600 ms | 2,090 ms | 520 ms | 2,270 ms |

**Read:** CLS is a non-issue and TTFB is excellent. The entire Performance deficit is **LCP +
main-thread blocking (TBT)** and, on mobile, **total payload**. The two apps share most of that root
cause (dev bundle); the website adds a large unoptimised image on top.

---

## 3. LCP breakdown — what actually delays the largest element

| App / mode | LCP element | Dominant sub-part |
| --- | --- | --- |
| Website | `<section id="home">` hero — `style="background-image: url('/assets/bphoto1.png')"` | 2,717 KB PNG downloaded as a **raw CSS background** (bypasses `next/image`); `fetchpriority=high` not applied (`lcp-discovery-insight`) |
| Backoffice | `<p class="hero-copy">` in `div#overview > section.hero-panel` | TTFB 151 ms + **element render delay 1,396 ms** — text is inside a client-gated tree (§4.2) |

---

## 4. Issues identified, with root cause

### 4.1 Cross-cutting — development bundle served to Lighthouse (highest impact)

**Evidence**
- `main-app.js` = **3,005 KiB** on both apps (largest single resource in all four reports).
- `unminified-javascript`: `webpack.js` 28,647 B, **22,904 B wasted (79.9%)** — both apps.
- `legacy-javascript-insight`: 10,422 B of `@babel/plugin-transform-classes`, `Array.prototype.at/flat/flatMap` transpilation in `main-app.js` — both apps.
- `valid-source-maps`: "Large JavaScript file is missing a source map" for `main-app.js`.
- `bootup-time` lists the `next-devtools` chunk as executed script.

**Root cause:** Lighthouse ran against `next dev`. The dev bundle ships unminified, un-tree-shaken,
with dev tooling, and is not representative of the app a user downloads. On mobile this single file
drives TBT (2,436 ms backoffice / 1,020 ms website) and the high TTI (20.3 s / 29.5 s).

**Fix direction:** re-baseline on `next build && next start` (the Docker `start.sh` also runs `dev`,
so the audited URL will never reflect production). This is measurement correctness first; the
bundle-size work below then operates on a realistic target.

### 4.2 Backoffice — client-side `AuthGuard` gates the first paint

**Evidence**
- `lcp-breakdown-insight`: element render delay **1,396 ms** for the hero copy.
- `app/layout.tsx:29` wraps every route in `<AuthGuard>`; `components/auth/AuthGuard.tsx:45-51` renders
  a "Checking your Nexova session…" placeholder until a `useEffect` validates the localStorage token.
- `forced-reflow-insight`: `scheduler.development.js` forced reflow (47 ms).
- `render-blocking-insight`: `layout.css` 10,867 B blocks for up to 197 ms.

**Root cause:** auth is resolved **client-side after hydration**, so the real content cannot paint
until JS has loaded, hydrated and run the token check. `app/page.tsx` also imports the cross-directory
`../../../scripts/src/sample-usage` module eagerly into the overview route.

**Fix direction:** keep the guard, but do not gate the LCP element on it — render the shell/hero
optimistically (or statically) and let the guard only redirect, so the largest text paints before
hydration. Consider `fetchpriority`/static rendering for the hero. (Not a rewrite — targeted change.)

### 4.3 Website — 2.7 MB hero PNG used as an inline CSS background

**Evidence**
- `image-delivery-insight` (mobile): `bphoto1.png` **2,717,150 B total, 2,467,150 B wasted** —
  "Using a modern image format (WebP, AVIF)… could improve this image's download size."
- `network-requests`: `bphoto1.png` is the 2nd largest resource (2,654 KB) after dev JS.
- `lcp-discovery-insight`: `fetchpriority=high` not applied.
- Source asset is a 2.7 MB PNG (`uis/website/public/assets/bphoto1.png`); `next.config.ts` has no
  `images` config.

**Root cause:** the hero is applied via an inline `style={{ backgroundImage: "url('/assets/bphoto1.png')" }}`
(`uis/website/app/page.tsx:140-144`), which bypasses `next/image` optimisation entirely and serves the
full PNG. It is the LCP element, so it directly costs LCP; on mobile it is the dominant payload driver.

**Fix direction:** route the hero through `next/image` (`fill` + `priority`) or emit an optimised
WebP/AVIF at the right display sizes. Secondary: the 18 MB source `bphoto5.jpg` in the repo should be
re-compressed even though `next/image` downsizes the delivered version.

### 4.4 Website — Service-page images only partially optimised

**Evidence:** `image-delivery-insight` also flags the `next/image` service cards (`bphoto4.jpg`
requested at `w=1920` for a 339 px-wide mobile slot). Delivered sizes: `bphoto4` 134 KB, `bphoto5`
104 KB, `bphoto2` 77 KB.

**Root cause:** `next/image` is used but sized generously; the requested `w` does not match the
rendered box on mobile, so more bytes than necessary are downloaded.

**Fix direction:** tighten `sizes` so mobile fetches a small candidate width.

### 4.5 Cross-cutting — render-blocking CSS and legacy/unminified JS

**Evidence:** `render-blocking-insight` (`layout.css` 7,560–10,867 B, 90–300 ms wasted);
`legacy-javascript-insight` (10,422 B); `unminified-javascript` (22,904 B, `webpack.js`).

**Root cause:** mostly the dev bundle; the blocking Tailwind/global stylesheet remains a smaller,
real opportunity in production.

**Fix direction:** verify on a production build (most of this disappears), then inline/critical-path
tune the remaining CSS if it still blocks.

### 4.6 Accessibility — colour contrast (both apps)

**Evidence** (`color-contrast`, score 0 on all four runs):
- Website: `.cta-pulse` "Join our talent pool" — `#ffffff` on `#ff2056` = **3.75:1** (needs 4.5:1).
- Backoffice: `.nav-icon` "02" — `#6f8889` on `#14262e` = **4.12:1** at 10 px (needs 4.5:1).

**Root cause:** foreground/background token pairs chosen for aesthetics fall below the WCAG AA 4.5:1
threshold.

**Fix direction:** darken the rose background slightly / lighten the nav-icon foreground. Targeted
token change, no layout impact.

### 4.7 Best Practices — missing source maps (both apps)

`valid-source-maps` score 0: `main-app.js` (and `app/page.js` on the website) ship without source
maps. Partly a dev artefact; when auditing production, confirm `productionBrowserSourceMaps` intent.

### 4.8 SEO — `robots.txt` invalid/missing on the website (desktop, score 92)

`robots-txt` score 0 on the website desktop run; there is **no `robots.txt`** in
`uis/website/public/`. Add a valid `robots.txt` (and confirm `sitemap.xml`) for the public corporate
site. The backoffice scores 100 here, which is expected for an internal app.

---

## 5. Refactor analysis — duplicated components & logic

Identified while reviewing the two frontends (all are candidates for the corrections phase; at least
one must be extracted and integrated). Listed by benefit-to-risk.

### 5.1 `parseApiError` is implemented three times (backoffice)

API error normalisation (FastAPI `detail` string vs validation array) is copy-pasted in:

- `uis/backoffice/lib/auth/session.ts:18`
- `uis/backoffice/lib/inventory.ts:114`
- `uis/backoffice/app/suppliers/page.tsx:94`

**Why it qualifies:** three near-identical pure functions, one of which is used by page code instead
of the lib layer; drift between them silently changes user-facing error text. `memory-bank/progress.md`
already flags this as an open candidate.

**Shared abstraction:** `uis/backoffice/lib/api/errors.ts` exporting `parseApiError(payload, fallback)`;
re-import in all three. `lib/inventory.ts` already has tests for it, so coverage moves with the module.

### 5.2 Website footer duplicated verbatim

The full `<footer>` block is identical in `uis/website/app/page.tsx:255-277` and
`uis/website/app/application/page.tsx:519-541`.

**Why it qualifies:** copied markup + Tailwind classes; any brand/copyright/link change must be made
twice.

**Shared abstraction:** `uis/website/components/SiteFooter.tsx`.

### 5.3 Website header/nav duplicated with a subtle divergence

`uis/website/components/Header.tsx` renders the nav with in-page anchors (`<a href="#home">`), while
`uis/website/app/application/page.tsx:202-230` re-implements the same header with route-prefixed links
(`<Link href="/#home">`).

**Why it qualifies:** two sources of truth for the same header; the inconsistency (anchor vs route) is
exactly the bug class duplication causes.

**Shared abstraction:** one `SiteHeader` taking a `linkMode: "anchor" | "route"` prop (or deriving it
from the current route).

### 5.4 Backoffice auth pages repeat the same card/scaffold

`login`, `register`, `forgot-password`, `reset-password` and `change-password` all repeat:
the `min-h-screen` centred wrapper, the `max-w-md|lg` rounded card, the "Nexova backoffice" eyebrow,
the shared `inputClass`, the `border-l-4 border-red-500 bg-red-50` error alert, and the
`isSubmitting`-driven teal submit button.

**Why it qualifies:** five files × the same markup + submit/error state machine; a styling or
accessibility fix (e.g. the contrast work in §4.6) must be replicated five times.

**Shared abstraction:** `<AuthCard>` (layout/eyebrow/alert/submit) plus a `useAuthSubmit` hook
(validation + `isSubmitting` + error message).

### 5.5 Website application form validation logic is inline and repetitive

`uis/website/app/application/page.tsx` (~590 lines) hand-rolls `validateField`, `validateAll`,
`validateAndSetField`, `setFieldValue` and `handleBlur`, then wires them field-by-field.

**Why it qualifies:** a generic form state/validation machine repeated across 11 fields inside one
file; it is the main reason the file is so large and hard to test.

**Shared abstraction:** a `useApplicationForm` custom hook (values, errors, `setField`, `validateAll`,
`handleSubmit`), leaving the page as mostly JSX. Directly testable in isolation.

---

## 6. Prioritised remediation roadmap (for the corrections phase)

1. **Re-baseline on a production build** (`next build && next start`), ideally with the React DevTools
   extension disabled. Everything below is judged against that.
2. **Website hero image** (§4.3): move `bphoto1.png` behind `next/image` with `priority` + correct
   sizes, or serve an optimised WebP/AVIF. Biggest single LCP/payload win.
3. **Backoffice render gating** (§4.2): stop the `AuthGuard` from blocking the hero paint; render the
   LCP text before/independently of the token check.
4. **Bundle weight** (§4.1, §4.5): confirm the production bundle sheds the dev bytes; then address any
   remaining unused/legacy JS that survives.
5. **Contrast fixes** (§4.6): website CTA + backoffice nav icons — small, testable token changes.
6. **`robots.txt` + sitemap** (§4.8) for the corporate site.
7. **Refactors** (§5), starting with `parseApiError` (lowest risk, already tested) and the website
   `SiteFooter`; then `SiteHeader` and the backoffice `AuthCard`.

Apply one issue per commit, re-run Lighthouse on the same URL after each, and record the delta.

---

## 7. Appendix — raw evidence map

| Figure in this document | Source audit id (`*.json` → `audits`) |
| --- | --- |
| Category scores | `categories.{performance,accessibility,best-practices,seo}.score` |
| CWV / timings | `first-contentful-paint`, `largest-contentful-paint`, `total-blocking-time`, `cumulative-layout-shift`, `speed-index`, `interactive`, `server-response-time`, `total-byte-weight`, `mainthread-work-breakdown`, `bootup-time`, `max-potential-fid` |
| LCP element & sub-parts | `lcp-breakdown-insight`, `lcp-discovery-insight` |
| Image waste | `image-delivery-insight` |
| Bundle / JS | `network-requests`, `unused-javascript`, `unminified-javascript`, `legacy-javascript-insight`, `valid-source-maps`, `network-dependency-tree-insight` |
| Render/reflow | `render-blocking-insight`, `forced-reflow-insight` |
| Contrast | `color-contrast` |
| SEO | `robots-txt` |
| Env / throttling | `configSettings`, `environment`, `userAgent`, `fetchTime` |

Raw reports audited: `backoffice-desktop.json`, `backoffice-mobile.json`, `website-desktop.json`,
`website-mobile.json` (this folder).

_Measurement note: no source files were modified to produce this baseline. Under
`.agents/rules/test-coverage.md`, documentation-only changes are exempt from new tests._
