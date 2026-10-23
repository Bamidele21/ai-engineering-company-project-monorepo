import { describe, expect, it } from "@jest/globals";
import {
  firstStackFrame,
  normalizeNetworkTarget,
  pagePath,
  sanitizeMessage,
  stripQuery,
} from "../telemetry/sanitize";

describe("stripQuery", () => {
  it("removes query strings and fragments", () => {
    expect(stripQuery("/login?next=%2Finventory#top")).toBe("/login");
    expect(stripQuery("/reset-password?token=secret")).toBe("/reset-password");
  });

  it("leaves a clean path unchanged", () => {
    expect(stripQuery("/inventory/products")).toBe("/inventory/products");
  });
});

describe("pagePath", () => {
  it("falls back to the root for an empty path", () => {
    expect(pagePath("")).toBe("/");
  });
});

describe("sanitizeMessage", () => {
  it("strips emails and URLs from error messages", () => {
    expect(
      sanitizeMessage(
        "Failed for elena.vargas@nexova.com at https://nexova.test/reset?token=abc"
      )
    ).toBe("Failed for [email] at [url]");
  });

  it("redacts sensitive query values in relative paths", () => {
    expect(
      sanitizeMessage("Reset failed at /reset-password?token=secret&next=%2Finventory")
    ).toBe("Reset failed at /reset-password?token=[redacted]&next=[redacted]");
  });

  it("truncates messages to 300 characters", () => {
    expect(sanitizeMessage("x".repeat(400))).toHaveLength(300);
  });
});

describe("firstStackFrame", () => {
  it("returns the first stack frame location only", () => {
    expect(
      firstStackFrame(
        "TypeError: boom\n    at renderRow (inventory-products.tsx:104:12)\n    at other (x.ts:1:1)"
      )
    ).toBe("inventory-products.tsx:104:12");
  });

  it("returns null when no frame exists", () => {
    expect(firstStackFrame("TypeError: boom")).toBeNull();
    expect(firstStackFrame(undefined)).toBeNull();
  });
});

describe("normalizeNetworkTarget", () => {
  it("maps known API origins to the service identifier", () => {
    expect(
      normalizeNetworkTarget(
        "http://localhost:8001/inventory/orders/inbound?asset_id=3"
      )
    ).toBe("inventory-api:/inventory/orders/inbound");
  });

  it("maps the auth API origin", () => {
    expect(normalizeNetworkTarget("http://localhost:8000/auth/login")).toBe(
      "supply-directory-api:/auth/login"
    );
  });

  it("falls back to a generic api target for unknown origins", () => {
    expect(normalizeNetworkTarget("https://example.test/x?y=1")).toBe("api:/x");
  });
});
