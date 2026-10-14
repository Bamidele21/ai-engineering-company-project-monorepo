import { describe, expect, it } from "@jest/globals";
import { parseApiError } from "../errors";

describe("parseApiError", () => {
  it("returns a string detail verbatim", () => {
    expect(parseApiError({ detail: "Insufficient stock" }, "fallback")).toBe(
      "Insufficient stock"
    );
  });

  it("joins an array of validation messages", () => {
    expect(
      parseApiError(
        { detail: [{ msg: "field required" }, { msg: "bad value" }] },
        "fallback"
      )
    ).toBe("field required. bad value");
  });

  it("skips blank entries when joining validation messages", () => {
    expect(
      parseApiError({ detail: [{ msg: "" }, { msg: "only this" }] }, "fallback")
    ).toBe("only this");
  });

  it("falls back for null, empty, non-object, and unrecognised payloads", () => {
    expect(parseApiError(null, "fallback")).toBe("fallback");
    expect(parseApiError({}, "fallback")).toBe("fallback");
    expect(parseApiError("oops", "fallback")).toBe("fallback");
    expect(parseApiError({ detail: [] }, "fallback")).toBe("fallback");
    expect(parseApiError({ detail: [{ msg: "" }] }, "fallback")).toBe("fallback");
  });
});
