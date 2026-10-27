import { parseApiError } from "./api/errors";
import { authorizedFetch } from "./auth/client";
import { INVENTORY_API_URL } from "./inventory";

// Typed client for the weekly office and programme performance report served
// by the reporting module of the Inventory API.

export type ReportingOffice = "valencia" | "miami";
export type ReportingCurrency = "EUR" | "USD";

export interface ReportEntry {
  office: ReportingOffice;
  programme_id: string;
  total_material_cost: number;
  kits_delivered_count: number;
  shortage_events_count: number;
  cost_variance_events_count: number;
  currency: ReportingCurrency;
}

export interface WeeklyReport {
  week_start: string;
  entries: ReportEntry[];
}

export const OFFICE_LABELS: Record<ReportingOffice, string> = {
  valencia: "Valencia",
  miami: "Miami",
};

export const PROGRAMME_LABELS: Record<string, string> = {
  "b2b-sales": "B2B Sales Certification",
  "basic-leadership": "Basic Leadership",
  "new-hire-onboarding": "New Hire Onboarding",
};

export function officeLabel(office: ReportingOffice): string {
  return OFFICE_LABELS[office] ?? office;
}

export function programmeLabel(programmeId: string): string {
  return PROGRAMME_LABELS[programmeId] ?? programmeId;
}

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const MILLISECONDS_PER_DAY = 24 * 60 * 60 * 1000;

function isoUtcDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}

export function isMondayIso(value: string): boolean {
  if (!ISO_DATE.test(value)) {
    return false;
  }
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.getTime()) && parsed.getUTCDay() === 1;
}

/**
 * The Monday of the most recent completed UTC week. The current UTC week is
 * never complete, so it is excluded even on a Sunday.
 */
export function mostRecentCompletedMonday(now: Date = new Date()): string {
  const daysSinceMonday = (now.getUTCDay() + 6) % 7;
  const completedMonday = new Date(
    Date.UTC(
      now.getUTCFullYear(),
      now.getUTCMonth(),
      now.getUTCDate() - daysSinceMonday - 7
    )
  );
  return isoUtcDate(completedMonday);
}

/** The most recent completed Monday weeks, newest first. */
export function completedWeekMondays(
  count: number,
  now: Date = new Date()
): string[] {
  const latest = mostRecentCompletedMonday(now);
  const base = new Date(`${latest}T00:00:00Z`).getTime();
  const weeks: string[] = [];
  for (let index = 0; index < count; index += 1) {
    weeks.push(isoUtcDate(new Date(base - index * 7 * MILLISECONDS_PER_DAY)));
  }
  return weeks;
}

/** "2026-10-19 to 2026-10-25 (UTC)" for a week that starts on the Monday. */
export function weekRangeLabel(weekStart: string): string {
  const start = new Date(`${weekStart}T00:00:00Z`);
  const end = new Date(start.getTime() + 6 * MILLISECONDS_PER_DAY);
  return `${isoUtcDate(start)} to ${isoUtcDate(end)} (UTC)`;
}

const MONEY_FORMATTERS: Record<ReportingCurrency, Intl.NumberFormat> = {
  EUR: new Intl.NumberFormat("en-IE", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: 2,
  }),
  USD: new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
  }),
};

/** Format money in the row's own currency; never a cross-currency total. */
export function formatMoney(value: number, currency: ReportingCurrency): string {
  return MONEY_FORMATTERS[currency].format(value);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

const MALFORMED_RESPONSE = "Received an unexpected weekly report response.";

function expectFiniteNumber(value: unknown): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error(MALFORMED_RESPONSE);
  }
  return value;
}

function expectCount(value: unknown): number {
  const number = expectFiniteNumber(value);
  if (!Number.isInteger(number) || number < 0) {
    throw new Error(MALFORMED_RESPONSE);
  }
  return number;
}

/**
 * Validate the server payload instead of presenting malformed data as zero
 * business activity. Throws on any unexpected shape.
 */
export function parseWeeklyReport(payload: unknown): WeeklyReport {
  if (!isRecord(payload)) {
    throw new Error(MALFORMED_RESPONSE);
  }

  const weekStart = payload.week_start;
  if (typeof weekStart !== "string" || !isMondayIso(weekStart)) {
    throw new Error(MALFORMED_RESPONSE);
  }

  const entries = payload.entries;
  if (!Array.isArray(entries)) {
    throw new Error(MALFORMED_RESPONSE);
  }

  const parsedEntries = entries.map((entry): ReportEntry => {
    if (!isRecord(entry)) {
      throw new Error(MALFORMED_RESPONSE);
    }
    const office = entry.office;
    const programmeId = entry.programme_id;
    const currency = entry.currency;
    if (office !== "valencia" && office !== "miami") {
      throw new Error(MALFORMED_RESPONSE);
    }
    if (typeof programmeId !== "string" || programmeId.length === 0) {
      throw new Error(MALFORMED_RESPONSE);
    }
    if (currency !== "EUR" && currency !== "USD") {
      throw new Error(MALFORMED_RESPONSE);
    }
    return {
      office,
      programme_id: programmeId,
      total_material_cost: expectFiniteNumber(entry.total_material_cost),
      kits_delivered_count: expectCount(entry.kits_delivered_count),
      shortage_events_count: expectCount(entry.shortage_events_count),
      cost_variance_events_count: expectCount(entry.cost_variance_events_count),
      currency,
    };
  });

  return { week_start: weekStart, entries: parsedEntries };
}

export function reportUrl(weekStart?: string): string {
  const search = weekStart
    ? `?week_start=${encodeURIComponent(weekStart)}`
    : "";
  return `${INVENTORY_API_URL}/reporting/weekly-office-program-performance${search}`;
}

/** Raised when the API has no computed report for the selected week (404). */
export class ReportNotFoundError extends Error {
  constructor() {
    super("No report has been computed for this week.");
    this.name = "ReportNotFoundError";
  }
}

export async function fetchWeeklyReport(
  weekStart?: string
): Promise<WeeklyReport> {
  const response = await authorizedFetch(reportUrl(weekStart));
  const payload = await response.json().catch(() => null);

  if (!response.ok) {
    if (response.status === 404) {
      throw new ReportNotFoundError();
    }
    throw new Error(
      parseApiError(payload, "Unable to load the weekly report.")
    );
  }

  return parseWeeklyReport(payload);
}
