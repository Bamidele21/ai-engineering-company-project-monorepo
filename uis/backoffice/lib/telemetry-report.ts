import { parseApiError } from "./api/errors";
import { authorizedFetch } from "./auth/client";
import { INVENTORY_API_URL } from "./inventory";

export interface TelemetryReportPeriod {
  from: string;
  to: string;
}

export interface EventsPerDayMetric {
  date: string;
  event_type: string;
  count: number;
}

export interface ErrorRateByTypeMetric {
  date: string;
  event_type: string;
  error_count: number;
  total_count: number;
  daily_total: number;
  error_rate: number;
}

export interface PageLoadLatencyMetric {
  date: string;
  page_path: string;
  average_load_duration_ms: number;
  sample_count: number;
}

export interface TelemetryReportMetrics {
  events_per_day: EventsPerDayMetric[];
  error_rate_by_type: ErrorRateByTypeMetric[];
  page_load_latency_by_day: PageLoadLatencyMetric[];
}

export interface TelemetryReport {
  period: TelemetryReportPeriod;
  metrics: TelemetryReportMetrics;
}

export interface TelemetryReportParams {
  startDate?: string;
  endDate?: string;
}

function emptyReport(): TelemetryReport {
  return {
    period: { from: "", to: "" },
    metrics: {
      events_per_day: [],
      error_rate_by_type: [],
      page_load_latency_by_day: [],
    },
  };
}

export function formatErrorRate(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

export function formatLatency(value: number): string {
  return `${value.toFixed(1)} ms`;
}

export function reportUrl(params: TelemetryReportParams = {}): string {
  const search = new URLSearchParams();
  if (params.startDate) {
    search.set("start_date", params.startDate);
  }
  if (params.endDate) {
    search.set("end_date", params.endDate);
  }

  const query = search.toString();
  return `${INVENTORY_API_URL}/telemetry/report${query ? `?${query}` : ""}`;
}

export async function fetchTelemetryReport(
  params: TelemetryReportParams = {}
): Promise<TelemetryReport> {
  const response = await authorizedFetch(reportUrl(params));
  const payload = await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(
      parseApiError(payload, "Unable to load the telemetry report.")
    );
  }

  const report = payload as Partial<TelemetryReport> | null;
  if (!report || typeof report !== "object") {
    return emptyReport();
  }

  return {
    period: report.period ?? { from: "", to: "" },
    metrics: {
      events_per_day: report.metrics?.events_per_day ?? [],
      error_rate_by_type: report.metrics?.error_rate_by_type ?? [],
      page_load_latency_by_day:
        report.metrics?.page_load_latency_by_day ?? [],
    },
  };
}
