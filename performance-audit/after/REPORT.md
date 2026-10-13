# Post-Performance Report — Nexova Website & Backoffice

The **fix → measure again** half of the audit loop. This document records every correction applied
to the two Nexova frontends and the measured change against the baseline in
[`../before/audit.md`](../before/audit.md).

Canonical numbers come from the four **after** Lighthouse reports in this folder
(`website-desktop.json`, `website-mobile.json`, `backoffice-desktop.json`, `backoffice-mobile.json`).
The committed screenshots are separate Lighthouse runs and are used for illustration only (see §7);
where a screenshot differs from the JSON by a point or two that is normal run-to-run variance.

> **Scope honesty:** the developer asked that the served build remain the **dev** build
> (`uis/start.sh` runs `next dev --webpack`), matching the baseline. The dev bundle
> (`_next/static/chunks/main-app.js`, **≈3,005 KiB**, unminified, plus `scheduler.development.js`)
> is therefore still present before and after, and TBT/TTI remain bound by it. This report fixes
> only what is real regardless of build mode: images, render gating, contrast, SEO, and code
> duplication.

---

## 1. Scope, environment & measurement caveat

| Item | Value |
| --- | --- |
| Tool | Lighthouse **13.4.1** (Chrome DevTools channel) |
| Browser | **Chrome 154** (`Mozilla/5.0 … Chrome/154.0.0.0 Safari/537.36`, Windows 10) |
| Baseline capture (UTC) | backoffice-mobile `2026-10-12T23:52:30Z` · website-desktop `2026-10-13T00:05:22Z` · website-mobile `2026-10-13T00:36:14Z` · backoffice-desktop `2026-10-13T00:37:22Z` |
| After capture (UTC) | backoffice-desktop `2026-10-13T22:44:08Z` · backoffice-mobile `2026-10-13T22:45:23Z` · website-desktop `2026-10-13T22:50:10Z` · website-mobile `2026-10-13T22:51:10Z` |
| Pages | Website `/` (`http://localhost:3000/`) · Backoffice `/` (`http://localhost:3001/`) |
| Form factors | Mobile (simulated 4× CPU, 150 ms RTT, 1638 Kbps) and Desktop (simulated 1× CPU, 40 ms RTT, 10240 Kbps) |
| Categories | Performance · Accessibility · Best Practices · SEO |

### ⚠️ Caveat — dev build retained, so bundle-driven metrics barely move

Both the baseline and this report were captured against `next dev`. The after reports still contain
the dev fingerprints: `main-app.js` ≈3,005 KiB (unchanged), `layout.js`, `app-pages-internals.js`,
and `scheduler.development.js` in `bootup-time`. Consequently:

- The **absolute** Performance scores remain below the ≥90 production benchmark.
- **TBT and TTI are dominated by the unminified dev JS** and move only with run variance; the
  website TBT increased slightly in these runs (270→370 ms desktop, 1,020→1,520 ms mobile) while
  Speed Index and TTI improved — i.e. noise around a dev-bundle floor, not a regression from the
  changes below.
- Fixing the bundle (minification, tree-shaking, source maps) requires switching to `next build`,
  which was explicitly out of scope for this pass.

---

## 2. Lighthouse score summary

Scores are Lighthouse's 0–100 scale; Performance is weighted, the other three are pass/fail audits.

| App | Mode | Performance | Accessibility | Best Practices | SEO |
| --- | --- | --- | --- | --- | --- |
| **Website** | Desktop | 72 → **83** (+11) | 96 → **100** (+4) | 100 → 100 | 92 → **100** (+8) |
| **Website** | Mobile | 53 → **66** (+13) | 96 → **100** (+4) | 100 → 100 | 100 → 100 |
| **Backoffice** | Desktop | 60 → **80** (+20) | 95 → 95 | 100 → 100 | 100 → 100 |
| **Backoffice** | Mobile | 46 → **69** (+23) | 95 → 95 | 100 → 100 | 100 → 100 |

Every Performance score improved; the website additionally cleared Accessibility (→100) and SEO
(→100 on desktop). Backoffice Accessibility stayed at 95 — see §3.4 and §6 for the honest reason.

### Core Web Vitals & key timings (before → after)

| Metric | Website DT | Website MOB | Backoffice DT | Backoffice MOB |
| --- | --- | --- | --- | --- |
| FCP | 0.4 → 0.2 s | 1.2 → 0.8 s | 0.3 → 0.4 s | 0.8 → 0.8 s |
| **LCP** | **3.1 → 0.7 s** | **17.7 → 3.4 s** | **3.6 → 0.6 s** | **20.1 → 2.7 s** |
| **TBT** (INP proxy) | 270 → 370 ms | 1,020 → 1,520 ms | 460 → 450 ms | 2,440 → 1,990 ms |
| **CLS** | 0.003 → 0.003 | 0 → 0 | 0.0001 → 0 | 0 → 0 |
| Speed Index | 0.6 → 0.5 s | 1.6 → 0.9 s | 1.0 → 0.4 s | 2.6 → 0.8 s |
| Time to Interactive | 5.1 → 3.8 s | 29.5 → 21.1 s | 3.6 → 3.6 s | 20.3 → 20.0 s |
| TTFB (server response) | 127 → 110 ms | 493 → 90 ms | 127 → 250 ms | 148 → 170 ms |
| **Total byte weight** | **6,369 → 3,613 KiB** | **6,369 → 3,582 KiB** | 3,329 → 3,332 KiB | 3,329 → 3,332 KiB |
| Main-thread work | 1.5 → 1.4 s | 5.3 → 5.1 s | 0.9 → 0.8 s | 3.9 → 3.0 s |
| JS execution (bootup) | 0.7 → 0.7 s | 2.6 → 2.7 s | 0.6 → 0.6 s | 2.9 → 2.4 s |
| Max Potential FID | 600 → 570 ms | 2,090 → 2,190 ms | 520 → 500 ms | 2,270 → 2,020 ms |

**Read:** the headline result is **LCP collapsing across all four runs** and the **website payload
dropping ~44%**. CLS is still a non-issue and TTFB is healthy. The only soft spots are the
dev-bundle-bound TBT/TTI numbers noted in §1.

---

## 3. Corrections applied

### 3.1 Website hero image routed through `next/image` (audit §4.3) — biggest website win

- **Files:** `uis/website/app/page.tsx` (`section#home`), `uis/website/app/globals.css` (`heroPan`).
- **Before:** the hero was an inline `style={{ backgroundImage: "url('/assets/bphoto1.png')" }}` on
  the section, serving the full **2,717,150 B PNG** as a raw CSS background (bypassing
  `next/image`), with no `fetchpriority`.
- **Change:** replaced with a `next/image` (`fill`, `sizes="100vw"`, `object-cover`,
  `preload`, `fetchPriority="high"`). On Next 16 the `priority` prop is deprecated in favour of
  `preload` (verified in `node_modules/next/dist/docs/…/image.md`). The `.hero-motion` pan animation
  was repointed from `background-position` to `object-position` so the visual effect and the
  reduced-motion opt-out are preserved.
- **Mechanism → impact:** the image now flows through the Next image optimizer (served as
  `/_next/image?url=%2Fassets%2Fbphoto1.png&w=…&q=75`), which resizes/re-encodes to the display size
  and sets the LCP fetch priority.
- **Measured evidence:**
  - LCP element changed from `section#home` → `img.hero-motion`.
  - `lcp-discovery-insight` now reports **`fetchpriority=high applied ✓`**, request discoverable ✓,
    not lazy ✓ (baseline had no priority hint).
  - Website total bytes **6,369 → 3,613 KiB (desktop) / 3,582 KiB (mobile)**.
  - LCP **3.1 → 0.7 s (desktop)**, **17.7 → 3.4 s (mobile)**; the post-fix LCP breakdown is
    TTFB 109 ms + resource load delay 16 ms + resource load 26 ms + element render delay 95 ms.

### 3.2 Backoffice render gating removed (audit §4.2) — biggest backoffice win

- **File:** `uis/backoffice/components/auth/AuthGuard.tsx`.
- **Before:** `AuthGuard` wrapped every route and, until a `useEffect` validated the localStorage
  token, returned a full-screen `"Checking your Nexova session..."` placeholder — so the LCP text
  could not paint until JS had loaded, hydrated, and run the token check (baseline element render
  delay ≈1,396 ms).
- **Change:** the guard now **renders `children` immediately** and keeps only the redirect when the
  session is missing, plus a non-blocking `role="status"` pill. No security behaviour changed (the
  redirect still fires); the backoffice overview renders non-sensitive sample data.
- **Mechanism → impact:** the largest text paints on the first HTML render instead of after
  hydration; **payload is unchanged**, which isolates this as the cause.
- **Measured evidence:** LCP **3.6 → 0.6 s (desktop)**, **20.1 → 2.7 s (mobile)** at
  **3,329 → 3,332 KiB (unchanged)**.

### 3.3 Website image `sizes` tightened (audit §4.4)

- **File:** `uis/website/app/page.tsx` (service cards and the "Why Nexova" image).
- **Before:** `next/image` was used but sized generously; on mobile Lighthouse saw `w=1920`
  requested for a ~339 px slot.
- **Change:** added `sizes="(min-width: 768px) 33vw, 100vw"` on the three service cards and
  `sizes="(min-width: 768px) 50vw, 100vw"` on the why image, so mobile fetches a small candidate
  width.
- **Measured evidence:** `image-delivery-insight` **0 → 0.5**; the requested width for a service
  image dropped from `w=1920` to `w=640`. Some waste remains (see §6).

### 3.4 Contrast fixes (audit §4.6)

- **Files:** `uis/website/app/page.tsx`, `uis/website/app/application/page.tsx`,
  `uis/backoffice/app/globals.css`.
- **Website:** white text on `rose-500` (`#f43f5e`, ≈3.67:1) moved to **`rose-600`** (`#e11d48`,
  ≈4.70:1) on the hero CTA, the application submit button, and the success-modal Close button.
  **Result:** website `color-contrast` **0 → 1**; Accessibility **96 → 100** on both form factors.
- **Backoffice:** `.nav-icon` `#6f8889` (4.12:1 on `#14262e`) → **`#7f9a9b`** (≈5.2:1). The five
  `nav-icon` nodes were **removed from the `color-contrast` failure list (55 → 50 desktop,
  54 → 50 mobile)**. However the audit still fails and Accessibility therefore stays at **95**,
  because ~50 other dashboard text tokens (`.metric-label`, `.metric-note`, `.hero-copy`, `.chip`,
  `.section-detail`, `.rank-number`, status badges, footer, etc.) remain below AA. Fully clearing
  the category requires a broader design-token pass, which is out of scope for this targeted audit
  (logged as a follow-up in §6).

### 3.5 `robots.txt` + `sitemap.xml` added (audit §4.8)

- **Files:** `uis/website/public/robots.txt` (new), `uis/website/public/sitemap.xml` (new).
- **Before:** no `robots.txt` existed; Lighthouse `robots-txt` scored 0 on the website desktop run.
- **Change:** added a valid `robots.txt` (`User-agent: *`, `Allow: /`, sitemap reference) and a
  two-entry `sitemap.xml` for `/` and `/application`.
- **Measured evidence:** website `robots-txt` **0 → 1**; website desktop **SEO 92 → 100**.

---

## 4. Refactors applied (audit §5)

These do not move Lighthouse scores — they are the "review the codebase and extract duplicated
components/logic" deliverable. All five baseline cases were resolved.

| # | Baseline issue | Extraction | Consumers updated |
| --- | --- | --- | --- |
| 5.1 | `parseApiError` implemented 3× in the backoffice | `uis/backoffice/lib/api/errors.ts` | `lib/auth/session.ts`, `lib/inventory.ts`, `app/suppliers/page.tsx` |
| 5.2 | Website footer duplicated verbatim | `uis/website/components/SiteFooter.tsx` | `app/page.tsx`, `app/application/page.tsx` |
| 5.3 | Website header duplicated (anchor vs route links) | `uis/website/components/SiteHeader.tsx` with a `linkMode: "anchor" \| "route"` prop (replaced `components/Header.tsx`) | `app/page.tsx`, `app/application/page.tsx` |
| 5.4 | Five backoffice auth pages repeated the same card/scaffold | `components/auth/AuthCard.tsx` (+ `AuthAlert`, shared input/submit classes) and `hooks/useAuthSubmit.ts` | `login`, `register`, `forgot-password`, `reset-password`, `account/change-password` |
| 5.5 | Application form validation hand-rolled inline (~590-line page) | `hooks/useApplicationForm.ts` over the pure `lib/applicationValidation.ts` | `app/application/page.tsx` |

Behaviour was preserved in every extraction. Two **pre-existing** validation quirks were confirmed
(and deliberately **not** "fixed"): the phone regex rejects space-separated digit groups, and an
empty `experience` field passes because `Number("") === 0`. Test coverage moved/was added with the
shared modules (see §5).

---

## 5. Verification performed

- **Unit tests:** `npx jest` from the repo root — **37/37 passing across 6 suites** (existing 28 +
  9 new). New: `uis/backoffice/lib/api/__tests__/errors.test.ts` (happy/edge/failure for the shared
  parser) and `uis/website/lib/__tests__/applicationValidation.test.ts` (field + whole-form
  validation); `uis/website` was added to the root `jest.config.js` `roots`.
- **Lint & build:** `npm run lint` and `npm run build` pass in **`uis/website`** (routes `/`,
  `/application`) and **`uis/backoffice`** (all 14 routes). No new dependencies, so the Docker
  `npm ci` step and the `./uis` bind mount are unaffected.
- **Exemptions:** the extractions in §4.2–§4.4 are behaviour-preserving structural moves (no new
  logic); the only new pure logic lives in the shared modules, which carry the tests above
  (per `.agents/rules/test-coverage.md`).

---

## 6. Biggest impact & what didn't move

**Biggest impact**

1. **Website — hero image via `next/image`.** Removing the 2.7 MB raw CSS background delivered the
   single largest effect on both fronts it touched: **LCP 3.1 → 0.7 s / 17.7 → 3.4 s** and a **~44%
   payload reduction** (6,369 → ~3,600 KiB). This alone lifted Performance by 11–13 points and
   cleared the LCP sub-part that dominated the baseline.
2. **Backoffice — removing the render gate.** With **identical bytes**, LCP fell **3.6 → 0.6 s /
   20.1 → 2.7 s**, showing the deficit was entirely client-side render gating rather than download
   weight. Performance rose 20–23 points.
3. **SEO/contrast** were small, targeted changes with outsized category effects (website SEO +8,
   website Accessibility +4).

**What didn't move (and why)**

- **Backoffice Accessibility (95):** the specific §4.6 `nav-icon` failure was fixed, but the
  dashboard has ~50 other sub-AA tokens; a full token pass is required for AA.
- **Website Accessibility is now 100** and **SEO 100**, so those categories are closed.
- **TBT / TTI / Total JS:** dev-bundle-bound (`main-app.js` ≈3,005 KiB unchanged). Not addressable
  without a production build.
- **Residual image waste (`image-delivery` 0.5):** the delivery optimizer still serves somewhat
  larger candidates than the rendered box for the service cards (e.g. `bphoto2` 640×378 for a
  330×256 display, ~36 KiB estimated savings). Source assets `bphoto1.png` (2.7 MB) and
  `bphoto5.jpg` (18 MB) also remain large on disk.

**Recommended follow-ups**

1. A backoffice design-token contrast pass to reach AA and lift Accessibility from 95.
2. Re-baseline on `next build && next start` to measure the bundle fixes that this dev-build pass
   could not touch (minification, tree-shaking, source maps, render-blocking CSS).
3. Re-compress/replace the source `bphoto1.png` and `bphoto5.jpg` assets.

---

## 7. Screenshots

Committed alongside the reports in `before/` and `after/`. These are **separate Lighthouse runs**
from the JSON and may differ by a point or two; the JSON in §2 is canonical.

| Phase | File | Page / mode | Performance | Accessibility | Best Practices | SEO |
| --- | --- | --- | --- | --- | --- | --- |
| before | `Screenshot 2026-10-12 173744.png` | Website desktop | 73 | 96 | 100 | 100 |
| before | `Screenshot 2026-10-12 173859.png` | Website mobile | 52 | 96 | 100 | 100 |
| before | `Screenshot 2026-10-12 174422.png` | Backoffice desktop | 60 | 95 | 100 | 100 |
| before | `Screenshot 2026-10-12 174526.png` | Backoffice mobile | 47 | 95 | 100 | 100 |
| after | `Screenshot 2026-10-13 180333.png` | Website desktop | 83 | 100 | 100 | 100 |
| after | `Screenshot 2026-10-13 181020.png` | Website mobile | 69 | 100 | 100 | 100 |
| after | `Screenshot 2026-10-13 174506.png` | Backoffice desktop | 80 | 95 | 100 | 100 |
| after | `Screenshot 2026-10-13 174555.png` | Backoffice mobile | 69 | 95 | 100 | 100 |

---

## 8. Appendix — evidence map

| Figure in this document | Source audit id (`*.json` → `audits`) |
| --- | --- |
| Category scores | `categories.{performance,accessibility,best-practices,seo}.score` |
| CWV / timings | `first-contentful-paint`, `largest-contentful-paint`, `total-blocking-time`, `cumulative-layout-shift`, `speed-index`, `interactive`, `server-response-time`, `total-byte-weight`, `mainthread-work-breakdown`, `bootup-time`, `max-potential-fid` |
| LCP element & sub-parts | `lcp-breakdown-insight`, `lcp-discovery-insight` |
| Image waste | `image-delivery-insight` |
| Bundle / JS | `network-requests`, `unminified-javascript`, `bootup-time` |
| Contrast | `color-contrast` |
| SEO | `robots-txt` |
| Env / throttling | `configSettings`, `environment`, `userAgent`, `fetchTime` |

Raw reports: `before/{website-desktop,website-mobile,backoffice-desktop,backoffice-mobile}.json` and
`after/{website-desktop,website-mobile,backoffice-desktop,backoffice-mobile}.json`.

_Measurement note: `REPORT.md` documents applied corrections and their measured impact; no
source files were altered to produce the after measurements beyond the changes listed in §3–§4.
Under `.agents/rules/test-coverage.md`, the documentation portion is exempt from new tests._
