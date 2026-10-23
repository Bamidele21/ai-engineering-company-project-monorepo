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
  fetchTelemetryReport,
  formatErrorRate,
  formatLatency,
  reportUrl,
  type TelemetryReport,
} from "../telemetry-report";

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
  it("adds both ISO date bounds when supplied", () => {
    expect(reportUrl({ startDate: "2026-10-21", endDate: "2026-10-22" })).toBe(
      `${INVENTORY_API_URL}/telemetry/report?start_date=2026-10-21&end_date=2026-10-22`
    );
  });

  it("omits the query string when no bounds are supplied", () => {
    expect(reportUrl()).toBe(`${INVENTORY_API_URL}/telemetry/report`);
  });
});

describe("metric formatting", () => {
  it("renders an error share as a one-decimal percentage", () => {
    expect(formatErrorRate(1 / 3)).toBe("33.3%");
    expect(formatErrorRate(1)).toBe("100.0%");
  });

  it("renders zero and positive latency values with milliseconds", () => {
    expect(formatLatency(0)).toBe("0.0 ms");
    expect(formatLatency(742)).toBe("742.0 ms");
  });
});

describe("fetchTelemetryReport", () => {
  const report: TelemetryReport = {
    period: {
      from: "2026-10-21T00:00:00Z",
      to: "2026-10-22T00:00:00Z",
    },
    metrics: {
      events_per_day: [
        { date: "2026-10-21", event_type: "page_view", count: 2 },
      ],
      error_rate_by_type: [
        {
          date: "2026-10-21",
          event_type: "frontend_error_captured",
          error_count: 1,
          total_count: 1,
          daily_total: 3,
          error_rate: 0.3333,
        },
      ],
      page_load_latency_by_day: [
        {
          date: "2026-10-21",
          page_path: "/inventory/products",
          average_load_duration_ms: 742,
          sample_count: 1,
        },
      ],
    },
  };

  it("returns the parsed report from the inventory API", async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, report));

    const result = await fetchTelemetryReport({
      startDate: "2026-10-21",
      endDate: "2026-10-22",
    });

    expect(result).toEqual(report);
    const [url] = fetchMock.mock.calls[0] as [string];
    expect(url).toContain("/telemetry/report?start_date=2026-10-21");
  });

  it("returns empty metric arrays when the payload omits metrics", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(200, {
        period: { from: "2026-10-21T00:00:00Z", to: "2026-10-22T00:00:00Z" },
      })
    );

    const result = await fetchTelemetryReport();

    expect(result.metrics).toEqual({
      events_per_day: [],
      error_rate_by_type: [],
      page_load_latency_by_day: [],
    });
  });

  it("surfaces the API error detail", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(503, { detail: "Telemetry report unavailable" })
    );

    await expect(fetchTelemetryReport()).rejects.toThrow(
      "Telemetry report unavailable"
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

    await expect(fetchTelemetryReport()).rejects.toThrow(
      "Unable to load the telemetry report."
    );
  });
});
