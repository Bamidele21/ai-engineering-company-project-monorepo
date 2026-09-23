import { parseApiError } from "../lib/auth/session";

describe("parseApiError", () => {
  it("returns the string detail from a payload", () => {
    expect(
      parseApiError({ detail: "Email is already registered" }, "fallback")
    ).toBe("Email is already registered");
  });

  it("joins validation messages from an array detail", () => {
    const payload = {
      detail: [{ msg: "Email is invalid" }, { msg: "Password too short" }],
    };
    expect(parseApiError(payload, "fallback")).toBe(
      "Email is invalid. Password too short"
    );
  });

  it("returns the fallback for a null payload", () => {
    expect(parseApiError(null, "fallback")).toBe("fallback");
  });

  it("returns the fallback when the payload has no usable detail", () => {
    expect(parseApiError({}, "fallback")).toBe("fallback");
  });

  it("returns the fallback for a non-object payload", () => {
    expect(parseApiError("oops", "fallback")).toBe("fallback");
  });
});
