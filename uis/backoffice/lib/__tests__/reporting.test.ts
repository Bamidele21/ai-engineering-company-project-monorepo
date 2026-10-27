import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  jest,
} from "@jest/globals";
import { INVENTORY_API_URL } from "../inventory";
import {
  ReportNotFoundError,
  completedWeekMondays,
  fetchWeeklyReport,
  formatMoney,
  isMondayIso,
  mostRecentCompletedMonday,
  officeLabel,
  parseWeeklyReport,
  programmeLabel,
  reportUrl,
  weekRangeLabel,
  type WeeklyReport,
} from "../reporting";

const fetchMock = jest.fn();

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response;
}

beforeEach(() => {
  global.fetch = fetchMock as unknown as typeof fetch;
});

afterEach(() => {
  fetchMock.mockReset();
});

describe("reportUrl", () => {
  it("adds the week_start parameter when supplied", () => {
    expect(reportUrl("2026-10-19")).toBe(
      `${INVENTORY_API_URL}/reporting/weekly-office-program-performance?week_start=2026-10-19`
    );
  });

  it("omits the query string for the default week", () => {
    expect(reportUrl()).toBe(
      `${INVENTORY_API_URL}/reporting/weekly-office-program-performance`
    );
  });
});

describe("week helpers", () => {
  it("computes the most recent completed Monday for a Monday", () => {
    const now = new Date("2026-10-26T12:00:00Z");
    expect(mostRecentCompletedMonday(now)).toBe("2026-10-19");
  });

  it("computes the most recent completed Monday for a Sunday", () => {
    const now = new Date("2026-10-25T23:59:59Z");
    expect(mostRecentCompletedMonday(now)).toBe("2026-10-12");
  });

  it("computes the most recent completed Monday for a mid-week day", () => {
    const now = new Date("2026-10-22T08:00:00Z");
    expect(mostRecentCompletedMonday(now)).toBe("2026-10-12");
  });

  it("lists completed Mondays newest first", () => {
    const now = new Date("2026-10-26T12:00:00Z");
    expect(completedWeekMondays(3, now)).toEqual([
      "2026-10-19",
      "2026-10-12",
      "2026-10-05",
    ]);
  });

  it("accepts only real Mondays", () => {
    expect(isMondayIso("2026-10-19")).toBe(true);
    expect(isMondayIso("2026-10-20")).toBe(false);
    expect(isMondayIso("not-a-date")).toBe(false);
  });

  it("labels the covered UTC week", () => {
    expect(weekRangeLabel("2026-10-19")).toBe(
      "2026-10-19 to 2026-10-25 (UTC)"
    );
  });
});

describe("labels and money formatting", () => {
  it("formats EUR and USD money without mixing currencies", () => {
    expect(formatMoney(48, "EUR")).toBe("€48.00");
    expect(formatMoney(0, "USD")).toBe("$0.00");
    expect(formatMoney(1240.5, "EUR")).toBe("€1,240.50");
    expect(formatMoney(490, "USD")).toBe("$490.00");
  });

  it("renders friendly office and programme labels", () => {
    expect(officeLabel("valencia")).toBe("Valencia");
    expect(officeLabel("miami")).toBe("Miami");
    expect(programmeLabel("b2b-sales")).toBe("B2B Sales Certification");
    expect(programmeLabel("unknown-slug")).toBe("unknown-slug");
  });
});

describe("parseWeeklyReport", () => {
  const valid: WeeklyReport = {
    week_start: "2026-10-19",
    entries: [
      {
        office: "valencia",
        programme_id: "b2b-sales",
        total_material_cost: 48.0,
        kits_delivered_count: 2,
        shortage_events_count: 0,
        cost_variance_events_count: 0,
        currency: "EUR",
      },
      {
        office: "miami",
        programme_id: "b2b-sales",
        total_material_cost: 0,
        kits_delivered_count: 0,
        shortage_events_count: 0,
        cost_variance_events_count: 0,
        currency: "USD",
      },
    ],
  };

  it("preserves server totals and numeric zeros", () => {
    const parsed = parseWeeklyReport(valid);

    expect(parsed).toEqual(valid);
    expect(parsed.entries[1].total_material_cost).toBe(0);
  });

  it.each([
    ["non-object payload", 42],
    ["missing week_start", { entries: [] }],
    ["non-Monday week_start", { week_start: "2026-10-20", entries: [] }],
    ["missing entries", { week_start: "2026-10-19" }],
    [
      "string cost",
      {
        week_start: "2026-10-19",
        entries: [
          {
            office: "valencia",
            programme_id: "x",
            total_material_cost: "48",
            kits_delivered_count: 0,
            shortage_events_count: 0,
            cost_variance_events_count: 0,
            currency: "EUR",
          },
        ],
      },
    ],
    [
      "non-finite cost",
      {
        week_start: "2026-10-19",
        entries: [
          {
            office: "valencia",
            programme_id: "x",
            total_material_cost: Number.POSITIVE_INFINITY,
            kits_delivered_count: 0,
            shortage_events_count: 0,
            cost_variance_events_count: 0,
            currency: "EUR",
          },
        ],
      },
    ],
    [
      "unknown office",
      {
        week_start: "2026-10-19",
        entries: [
          {
            office: "berlin",
            programme_id: "x",
            total_material_cost: 1,
            kits_delivered_count: 0,
            shortage_events_count: 0,
            cost_variance_events_count: 0,
            currency: "EUR",
          },
        ],
      },
    ],
    [
      "unknown currency",
      {
        week_start: "2026-10-19",
        entries: [
          {
            office: "valencia",
            programme_id: "x",
            total_material_cost: 1,
            kits_delivered_count: 0,
            shortage_events_count: 0,
            cost_variance_events_count: 0,
            currency: "GBP",
          },
        ],
      },
    ],
  ])("rejects malformed payloads: %s", (_label, payload) => {
    expect(() => parseWeeklyReport(payload)).toThrow(
      "Received an unexpected weekly report response."
    );
  });
});

describe("fetchWeeklyReport", () => {
  it("returns the parsed report from the reporting endpoint", async () => {
    const report: WeeklyReport = {
      week_start: "2026-10-19",
      entries: [
        {
          office: "valencia",
          programme_id: "b2b-sales",
          total_material_cost: 48.0,
          kits_delivered_count: 2,
          shortage_events_count: 1,
          cost_variance_events_count: 0,
          currency: "EUR",
        },
      ],
    };
    fetchMock.mockResolvedValue(jsonResponse(200, report));

    const result = await fetchWeeklyReport("2026-10-19");

    expect(result).toEqual(report);
    const [url] = fetchMock.mock.calls[0] as [string];
    expect(url).toContain("/reporting/weekly-office-program-performance");
    expect(url).toContain("week_start=2026-10-19");
  });

  it("maps a 404 to a no-report error with the required wording", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(404, { detail: "No weekly report has been computed for 2026-10-05" })
    );

    await expect(fetchWeeklyReport("2026-10-05")).rejects.toBeInstanceOf(
      ReportNotFoundError
    );
    await expect(fetchWeeklyReport("2026-10-05")).rejects.toThrow(
      "No report has been computed for this week."
    );
  });

  it("surfaces API error detail for service failures", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(503, { detail: "Reporting dependency is unavailable" })
    );

    await expect(fetchWeeklyReport()).rejects.toThrow(
      "Reporting dependency is unavailable"
    );
  });

  it("rejects a malformed 200 payload instead of showing zero activity", async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { week_start: "2026-10-19" }));

    await expect(fetchWeeklyReport()).rejects.toThrow(
      "Received an unexpected weekly report response."
    );
  });

  it("falls back to a readable error when the body is not JSON", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => {
        throw new Error("invalid json");
      },
    } as unknown as Response);

    await expect(fetchWeeklyReport()).rejects.toThrow(
      "Unable to load the weekly report."
    );
  });
});
