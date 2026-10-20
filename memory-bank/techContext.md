# Tech Context

## Current served scope

The apps actually built and served by `uis/start.sh` (and the Docker `ui` service) are:

1. `uis/website` — public corporate site (port 3000).
2. `uis/backoffice` — internal operations dashboard (port 3001).
3. `scripts` — shared TypeScript domain logic consumed by the backoffice overview.

Earlier-milestone apps `uis/landing_page` (static HTML) and `uis/talent-pipeline-tracker`
(Next.js) are still present in the tree but are **not part of the currently served stack**.
`memory-bank/projectbrief.md` still describes those older apps and should be treated as stale
until updated.

## Stack by area

### 1) `uis/website`

1. Next.js App Router application (Next 16, React 19, TypeScript), `"use client"` pages.
2. Tailwind CSS v4 (`@import "tailwindcss"`) plus custom keyframe animations in `app/globals.css`.
3. Routes: `/` (marketing home) and `/application` (talent application form).
4. Shared presentational components: `components/SiteHeader.tsx` (`linkMode: "anchor" | "route"`)
   and `components/SiteFooter.tsx`.
5. Form logic extracted to `hooks/useApplicationForm.ts` over the pure
   `lib/applicationValidation.ts` module.
6. Hero and content images served through `next/image` (`preload` + `fetchPriority="high"` on the
   hero; per-breakpoint `sizes` on the service/why images).
7. SEO: static `public/robots.txt` and `public/sitemap.xml`.

### 2) `uis/backoffice`

1. Next.js App Router application (Next 16, React 19, TypeScript).
2. Tailwind CSS v4 plus a hand-maintained `app/globals.css` design system (`.bo-*`, `.nav-*`,
   `.inventory-*`).
3. Routes: `/`, `/suppliers`, `/incidents`, `/inventory/*`, plus auth routes (`/login`,
   `/register`, `/forgot-password`, `/reset-password`, `/account/profile`,
   `/account/change-password`).
4. API layer under `lib/` using `authorizedFetch` (bearer token + 401 redirect); shared error
   normalisation in `lib/api/errors.ts` (`parseApiError`).
5. Auth UI standardised through `components/auth/AuthCard.tsx` (+ `AuthAlert`, shared input/submit
   classes) and the `hooks/useAuthSubmit.ts` state machine.
6. `components/auth/AuthGuard.tsx` performs client-side session gating; it renders route content
   immediately and only redirects when the token is missing.
7. Imports the repo-root `scripts/src/sample-usage` module for the overview dashboard (cross-
   directory import, enabled via `experimental.externalDir`).

### 3) `scripts`

1. TypeScript domain models in `src/models/models.ts`.
2. Utility modules by concern: `src/utils/{collections,search,transformations,validations}.ts`.
3. Demonstration runner in `src/sample-usage.ts`, eagerly imported by the backoffice overview.

## Cross-cutting technical constraints

1. Context alignment is mandatory: terminology and framing must match the Nexova scenario documents.
2. Async UX requirement: loading, success, and error states must be visible.
3. Environment dependency: tracker/backoffice require `NEXT_PUBLIC_*` API URLs in `.env`.
4. Milestone constraints emphasise Next.js + React + TypeScript with no external state manager.
5. **Performance baseline is measured on the dev build.** `uis/start.sh` runs
   `next dev --webpack` for both apps, so Lighthouse captures ship unminified dev bundles and
   dev tooling. The `performance-audit/` loop therefore treats the dev-build numbers as
   pessimistic and fixes only the issues that are real regardless of build (images, render
   gating, contrast, SEO, duplication).

## Technical risks observed

1. Root `CONTEXT.md` is still a placeholder; active context is split across subfolder context
   files.
2. `memory-bank/projectbrief.md` and this file previously described `uis/landing_page` +
   `uis/talent-pipeline-tracker`; the live audited apps are `uis/website` + `uis/backoffice`.
3. Tracker/backoffice folders include build/runtime artefacts (`.next/`, `node_modules/`) in the
   workspace, which increases repo noise.
4. The dev bundle (`_next/static/chunks/main-app.js`, `webpack.js`, dev tooling) dominates
   Lighthouse byte weight and TBT; this is a build-mode artefact, not application code.
5. The website's source hero PNG (`bphoto1.png`, ~2.7 MB) and `bphoto5.jpg` (~18 MB) remain large
   on disk; `next/image` downsizes the delivered bytes but the sources are still worth
   re-compressing.
