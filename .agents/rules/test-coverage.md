# Rule: Test Coverage for Functional Changes

## Scope

- Type: always active
- Applies to: whole monorepo (functional code changes)

## Purpose

Guarantee that every functional behaviour change ships with automated tests that
prove the happy path works, the boundaries behave, and failures are handled
deliberately — instead of relying on manual checks or a single happy-path test.

## Required behavior

1. Every functional code change (business logic, API routes, utilities,
   components, data transforms) must add or update automated tests in the same
   change. A change is not complete until its tests exist and pass.
2. Each covered unit or entrypoint needs three tiers:
   - Happy case: valid input produces the expected successful outcome.
   - Edge case: a boundary or valid alternate input (empty, max, boundary value,
     optional field, alternate role/state) behaves correctly.
   - Failure case: invalid, missing, or rejected input, or an error path,
     produces the expected rejection or handled error.
3. Assert business behaviour (business decisions, computed values, state
   transitions), not framework serialisation or status codes alone.
4. Follow the existing test conventions:
   - Backend: pytest under `backrooms/services` (see `conftest.py`).
   - Frontend utilities: Jest under `uis/talent-pipeline-tracker/__tests__`
     (config at root `jest.config.js`).
   - Reuse the nearest existing suite, fixtures, and naming patterns.
5. Run the targeted suite for the changed scope and capture the result before
   updating `memory-bank/progress.md` and committing.

## Documented exceptions

No tests are required for changes that add no functional behaviour, including:

1. Documentation, markdown, and comments.
2. CSS, styling, and pure visual presentation.
3. Configuration, environment examples, and static markup with no logic.
4. Trivial copy/typo changes.

When an exception applies, state it explicitly in the `memory-bank/progress.md`
entry so the omission is a recorded decision, not an oversight.

## Verification checklist

1. The change includes or updates tests for every functional behaviour changed.
2. Happy, edge, and failure cases are all present for each new behaviour.
3. Assertions target business behaviour, not just transport-layer details.
4. The targeted suite was run and passed (result captured).
5. Any exemption is documented in `memory-bank/progress.md`.
6. No protected path was modified without explicit developer approval.

## Anti-patterns

1. Shipping functional logic with no tests and no documented exemption.
2. One happy-path test presented as adequate coverage.
3. Asserting only HTTP status codes or return types with no business-rule check.
4. Marking a change complete before the tests actually run and pass.
5. Copying generic test shapes that ignore the assigned Nexova context.
