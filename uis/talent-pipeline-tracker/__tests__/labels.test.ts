import { toStageLabel, toStatusLabel } from "../lib/labels";

describe("toStatusLabel", () => {
  it("returns the human label for a known status", () => {
    expect(toStatusLabel("in_progress")).toBe("In progress");
    expect(toStatusLabel("selected")).toBe("Selected");
    expect(toStatusLabel("discarded")).toBe("Discarded");
  });

  it("returns a dash when no status is provided", () => {
    expect(toStatusLabel(undefined)).toBe("-");
  });

  it("passes through an unknown status unchanged", () => {
    expect(toStatusLabel("bogus" as never)).toBe("bogus");
  });
});

describe("toStageLabel", () => {
  it("returns the human label for a known stage", () => {
    expect(toStageLabel("offer_presented")).toBe("Offer presented");
    expect(toStageLabel("technical_interview")).toBe("Technical interview");
  });

  it("returns a dash when no stage is provided", () => {
    expect(toStageLabel(undefined)).toBe("-");
  });
});
