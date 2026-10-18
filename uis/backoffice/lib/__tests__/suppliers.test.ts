import { describe, expect, it } from "@jest/globals";
import { isRenewalWithin60Days } from "../suppliers";

function isoDate(offsetDays: number): string {
  const date = new Date();
  date.setUTCDate(date.getUTCDate() + offsetDays);
  return date.toISOString().slice(0, 10);
}

describe("isRenewalWithin60Days", () => {
  it("returns true for a renewal within the next 60 days", () => {
    expect(isRenewalWithin60Days(isoDate(30))).toBe(true);
  });

  it("returns true at the 0- and 60-day boundaries", () => {
    expect(isRenewalWithin60Days(isoDate(0))).toBe(true);
    expect(isRenewalWithin60Days(isoDate(60))).toBe(true);
  });

  it("returns false for a renewal beyond 60 days or in the past", () => {
    expect(isRenewalWithin60Days(isoDate(61))).toBe(false);
    expect(isRenewalWithin60Days(isoDate(-1))).toBe(false);
  });

  it("returns false for null, empty, or malformed dates", () => {
    expect(isRenewalWithin60Days(null)).toBe(false);
    expect(isRenewalWithin60Days("")).toBe(false);
    expect(isRenewalWithin60Days("not-a-date")).toBe(false);
  });
});
