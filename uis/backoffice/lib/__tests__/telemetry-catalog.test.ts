import { beforeEach, describe, expect, it } from "@jest/globals";
import {
  allowedProperties,
  hasRequiredProperties,
  isSupportedFrontendEvent,
  resetCatalogForTests,
  shouldEmitThrottled,
} from "../telemetry/catalog";

beforeEach(() => {
  resetCatalogForTests();
});

describe("allowedProperties", () => {
  it("keeps only allowlisted keys", () => {
    const result = allowedProperties("page_view", {
      page_path: "/inventory",
      email: "elena@nexova.com",
      load_duration_ms: 1200,
    });

    expect(result.allowed).toEqual({
      page_path: "/inventory",
      load_duration_ms: 1200,
    });
    expect(result.rejected).toEqual(["email"]);
  });

  it("returns an empty allowlist for an unsupported event", () => {
    const result = allowedProperties("login_succeeded", { role: "admin" });
    expect(result.allowed).toEqual({});
    expect(result.rejected).toEqual(["role"]);
  });
});

describe("isSupportedFrontendEvent", () => {
  it("supports the Sprint 1 technical events", () => {
    expect(isSupportedFrontendEvent("page_view")).toBe(true);
    expect(isSupportedFrontendEvent("validation_failed")).toBe(true);
  });

  it("rejects deferred and backend-only events", () => {
    expect(isSupportedFrontendEvent("inbound_order_created")).toBe(false);
    expect(isSupportedFrontendEvent("login_failed")).toBe(false);
  });
});

describe("hasRequiredProperties", () => {
  it("accepts a complete event", () => {
    expect(hasRequiredProperties("page_view", { page_path: "/inventory" })).toBe(
      true
    );
  });

  it("rejects an event missing a required key", () => {
    expect(hasRequiredProperties("page_view", {})).toBe(false);
    expect(
      hasRequiredProperties("validation_failed", { source: "client" })
    ).toBe(false);
  });
});

describe("shouldEmitThrottled", () => {
  it("allows the first event and suppresses repeats inside the window", () => {
    expect(shouldEmitThrottled("k", 60_000, 1_000)).toBe(true);
    expect(shouldEmitThrottled("k", 60_000, 2_000)).toBe(false);
  });

  it("allows the event again after the window expires", () => {
    expect(shouldEmitThrottled("k", 60_000, 1_000)).toBe(true);
    expect(shouldEmitThrottled("k", 60_000, 61_000)).toBe(true);
  });
});
