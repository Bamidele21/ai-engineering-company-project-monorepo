import { describe, expect, it } from "@jest/globals";
import { INITIAL_VALUES, validateAll, validateField } from "../applicationValidation";

describe("validateField", () => {
  it("accepts valid values", () => {
    expect(
      validateField("fullName", { ...INITIAL_VALUES, fullName: "Ada Lovelace" })
    ).toBe("");
    expect(
      validateField("email", { ...INITIAL_VALUES, email: "ada@nexova.com" })
    ).toBe("");
    expect(
      validateField("phone", { ...INITIAL_VALUES, phone: "+34612345678" })
    ).toBe("");
    expect(
      validateField("experience", { ...INITIAL_VALUES, experience: "5" })
    ).toBe("");
    expect(
      validateField("linkedin", {
        ...INITIAL_VALUES,
        linkedin: "https://linkedin.com/in/ada",
      })
    ).toBe("");
  });

  it("rejects boundary and edge values", () => {
    expect(
      validateField("experience", { ...INITIAL_VALUES, experience: "51" })
    ).toMatch(/between 0 and 50/);
    expect(
      validateField("experience", { ...INITIAL_VALUES, experience: "-1" })
    ).toMatch(/between 0 and 50/);
    expect(
      validateField("comments", {
        ...INITIAL_VALUES,
        comments: "x".repeat(501),
      })
    ).toMatch(/cannot exceed 500/);
    expect(
      validateField("linkedin", {
        ...INITIAL_VALUES,
        linkedin: "linkedin.com/in/ada",
      })
    ).toMatch(/valid URL/);
  });

  it("rejects missing required values", () => {
    expect(validateField("fullName", INITIAL_VALUES)).toMatch(
      /first and last name/
    );
    expect(validateField("email", INITIAL_VALUES)).toMatch(/valid email/);
    expect(validateField("country", INITIAL_VALUES)).toMatch(
      /country of residence/
    );
    expect(validateField("policy", INITIAL_VALUES)).toMatch(
      /data processing policy/
    );
  });
});

describe("validateAll", () => {
  it("returns no errors for a complete valid form", () => {
    const errors = validateAll({
      fullName: "Ada Lovelace",
      email: "ada@nexova.com",
      phone: "+34612345678",
      country: "Spain",
      experience: "8",
      sector: "Technology",
      english: "Advanced",
      availability: "Immediate",
      linkedin: "https://linkedin.com/in/ada",
      comments: "",
      policy: true,
    });

    expect(errors).toEqual({});
  });

  it("collects every failing field", () => {
    const errors = validateAll(INITIAL_VALUES);

    expect(Object.keys(errors).sort()).toEqual(
      [
        "availability",
        "country",
        "email",
        "english",
        "fullName",
        "phone",
        "policy",
        "sector",
      ].sort()
    );
  });
});
