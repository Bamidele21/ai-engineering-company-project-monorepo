import { afterEach, describe, expect, it, jest } from "@jest/globals";
import {
  navigationPagePath,
  readNavigationDuration,
  sameOriginReferrer,
} from "../telemetry/page-view";

const originalPerformance = globalThis.performance;

afterEach(() => {
  (globalThis as unknown as { performance: Performance }).performance =
    originalPerformance;
});

describe("readNavigationDuration", () => {
  it("returns the rounded document navigation duration", () => {
    (globalThis as unknown as { performance: unknown }).performance = {
      getEntriesByType: jest.fn(() => [{ duration: 812.4 }]),
    };

    expect(readNavigationDuration()).toBe(812);
  });

  it("returns undefined when no navigation entry exists", () => {
    (globalThis as unknown as { performance: unknown }).performance = {
      getEntriesByType: jest.fn(() => []),
    };

    expect(readNavigationDuration()).toBeUndefined();
  });

  it("discards a non-finite measurement", () => {
    (globalThis as unknown as { performance: unknown }).performance = {
      getEntriesByType: jest.fn(() => [{ duration: Number.NaN }]),
    };

    expect(readNavigationDuration()).toBeUndefined();
  });
});

describe("sameOriginReferrer", () => {
  it("keeps a same-origin referrer and strips the query", () => {
    expect(
      sameOriginReferrer(
        "https://backoffice.nexova.test/inventory?token=secret",
        "https://backoffice.nexova.test"
      )
    ).toBe("/inventory");
  });

  it("rejects cross-origin and malformed referrers", () => {
    expect(
      sameOriginReferrer(
        "https://evil.test/inventory",
        "https://backoffice.nexova.test"
      )
    ).toBeUndefined();
    expect(sameOriginReferrer("not a url", "https://backoffice.nexova.test")).toBeUndefined();
  });
});

describe("navigationPagePath", () => {
  it("strips query strings from the route", () => {
    expect(navigationPagePath("/login?next=%2Finventory")).toBe("/login");
  });
});
