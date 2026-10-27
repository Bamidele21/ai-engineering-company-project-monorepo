"use client";
/* eslint-disable react-hooks/set-state-in-effect */

import { FormEvent, useCallback, useEffect, useState } from "react";
import { BackofficeShell } from "@/components/backoffice/BackofficeShell";
import {
  fetchTelemetryReport,
  formatErrorRate,
  formatLatency,
  type TelemetryReport,
} from "@/lib/telemetry-report";

export default function TelemetryReportPage() {
  const [report, setReport] = useState<TelemetryReport | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");

  const loadReport = useCallback(
    async (params: { startDate?: string; endDate?: string } = {}) => {
      setIsLoading(true);
      setLoadError("");

      try {
        setReport(await fetchTelemetryReport(params));
      } catch (error) {
        setReport(null);
        setLoadError(
          error instanceof Error
            ? error.message
            : "Unable to load the telemetry report."
        );
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  useEffect(() => {
    void loadReport();
  }, [loadReport]);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void loadReport({
      startDate: startDate || undefined,
      endDate: endDate || undefined,
    });
  };

  const showLastSevenDays = () => {
    setStartDate("");
    setEndDate("");
    void loadReport();
  };

  return (
    <BackofficeShell
      eyebrow="Engineering / Nexova"
      title="Telemetry report"
      initials="TE"
      connectedLabel="Inventory API report endpoint"
    >
      <section className="inventory-hero">
        <div>
          <p>01 / System health</p>
          <h2>Operational telemetry, grouped by UTC day.</h2>
          <span>
            Event volume, captured-event error share, and observed page-load
            latency. These are engineering signals, not commercial KPIs.
          </span>
        </div>
        <b>
          NEX
          <br />
          OPS
        </b>
      </section>

      <section className="inventory-card inventory-form-card">
        <header>
          <h2>Reporting period</h2>
          <small>UTC · inclusive start / exclusive end</small>
        </header>
        <form onSubmit={handleSubmit}>
          <div className="inventory-form-grid">
            <label>
              From
              <input
                type="date"
                value={startDate}
                onChange={(event) => setStartDate(event.target.value)}
              />
            </label>
            <label>
              To
              <input
                type="date"
                value={endDate}
                onChange={(event) => setEndDate(event.target.value)}
              />
            </label>
          </div>
          <div className="inventory-form-actions">
            <button type="submit" disabled={isLoading}>
              {isLoading ? "Loading..." : "Apply period"}
            </button>
            <button
              type="button"
              onClick={showLastSevenDays}
              disabled={isLoading}
            >
              Last 7 days
            </button>
          </div>
        </form>
      </section>

      {loadError ? (
        <p className="inventory-error" role="alert">
          {loadError}{" "}
          <button type="button" onClick={() => void loadReport()}>
            Try again
          </button>
        </p>
      ) : null}

      {report ? (
        <section className="inventory-card">
          <header>
            <h2>Current period</h2>
            <small>UTC</small>
          </header>
          <p className="inventory-stock-hint">
            <strong>{report.period.from}</strong> to{" "}
            <strong>{report.period.to}</strong>
          </p>
        </section>
      ) : null}

      <section className="inventory-card">
        <header>
          <h2>Events per day</h2>
          <small>Volume by type</small>
        </header>
        <div className="inventory-table-wrapper">
          <table className="inventory-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Event type</th>
                <th>Count</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr>
                  <td colSpan={3}>Loading telemetry report...</td>
                </tr>
              ) : report && report.metrics.events_per_day.length > 0 ? (
                report.metrics.events_per_day.map((row) => (
                  <tr key={`${row.date}-${row.event_type}`}>
                    <td>{row.date}</td>
                    <td>
                      <strong>{row.event_type}</strong>
                    </td>
                    <td>{row.count}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={3}>No events in this period.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="inventory-card">
        <header>
          <h2>Error rate by type</h2>
          <small>Error-level share of daily activity</small>
        </header>
        <div className="inventory-table-wrapper">
          <table className="inventory-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Event type</th>
                <th>Errors</th>
                <th>Type total</th>
                <th>Daily total</th>
                <th>Error share</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr>
                  <td colSpan={6}>Loading telemetry report...</td>
                </tr>
              ) : report && report.metrics.error_rate_by_type.length > 0 ? (
                report.metrics.error_rate_by_type.map((row) => (
                  <tr key={`${row.date}-${row.event_type}`}>
                    <td>{row.date}</td>
                    <td>
                      <strong>{row.event_type}</strong>
                    </td>
                    <td>{row.error_count}</td>
                    <td>{row.total_count}</td>
                    <td>{row.daily_total}</td>
                    <td>{formatErrorRate(row.error_rate)}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={6}>No captured events in this period.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="inventory-card">
        <header>
          <h2>Page load latency by day</h2>
          <small>Observed document-load time</small>
        </header>
        <div className="inventory-table-wrapper">
          <table className="inventory-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Route</th>
                <th>Mean load</th>
                <th>Samples</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr>
                  <td colSpan={4}>Loading telemetry report...</td>
                </tr>
              ) : report &&
                report.metrics.page_load_latency_by_day.length > 0 ? (
                report.metrics.page_load_latency_by_day.map((row) => (
                  <tr key={`${row.date}-${row.page_path}`}>
                    <td>{row.date}</td>
                    <td>
                      <strong>{row.page_path}</strong>
                    </td>
                    <td>{formatLatency(row.average_load_duration_ms)}</td>
                    <td>{row.sample_count}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={4}>No page-load samples in this period.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </BackofficeShell>
  );
}
