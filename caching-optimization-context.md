## 💻 What You Need to Do

### Frontend Analysis and Optimisation

- [ ] Audit your Next.js application and identify at least **two components or routes** that are good candidates for Lazy Loading. Document your reasoning: why is deferring this component's load justified?
- [ ] Implement Lazy Loading for those components using `next/dynamic` or `React.lazy`.
- [ ] Audit your components for expensive computed values. Identify at least **one `useMemo` opportunity** where the computation is non-trivial and the dependency array is well-defined.
- [ ] Implement the `useMemo` optimisation. Do not apply it to trivial calculations.

### Backend Analysis and Optimisation

- [ ] List all endpoints in your FastAPI application. For each one, assess: (a) how expensive is the operation? (b) how frequently is it called? (c) how often does the underlying data change?
- [ ] Identify at least **two endpoints** that meet the cost + frequency + stability criteria for caching.
- [ ] Implement caching for those endpoints. You may use an in-memory dictionary with TTL logic, `functools.lru_cache` where applicable, or a Redis-based cache if your stack supports it.
- [ ] Implement cache invalidation: if the underlying data changes (e.g., a write operation), the relevant cached values must be cleared or marked stale.

> ⚠️ **IMPORTANT:** Do not cache endpoints that return personalised, session-specific, or sensitive data without scoping the cache key to the authenticated user. A shared cache key for private data is a data leak, not a performance gain.

### Technical Report

- [ ] Write a `CACHING_REPORT.md` (or equivalent) in your monorepo with the following sections:
  - **Frontend decisions**: which components were lazy-loaded and why; which values were memoized and what the measured or estimated benefit is.
  - **Backend decisions**: for each cached endpoint, document the operation cost, call frequency estimate, TTL chosen, and invalidation strategy.
  - **Tradeoffs acknowledged**: at least one explicit discussion of a data freshness tradeoff — where you chose a specific TTL and why that level of potential staleness is acceptable for this use case.
  - **What was not cached and why**: identify at least one endpoint or component you considered but decided against caching, with justification.

---

## ✅ What We Will Evaluate

- [ ] At least two components or routes implement Lazy Loading with documented justification.
- [ ] At least one `useMemo` is applied to a non-trivial computed value with a correct dependency array.
- [ ] At least two backend endpoints are cached with TTL-based expiry.
- [ ] Cache invalidation is implemented: cached values are cleared when the underlying data changes.
- [ ] No private or session-specific data is stored in a shared cache key.
- [ ] `CACHING_REPORT.md` is present and addresses all required sections.
- [ ] Decisions in the report are specific and justified — not generic ("we cached this because it's slow").
- [ ] At least one tradeoff (freshness vs. performance) is explicitly discussed.

> Note: The evaluation focuses on decision quality and implementation correctness, not on the number of endpoints or components cached. Fewer well-justified decisions are preferred over many unjustified ones.
