"use client";
/* eslint-disable react-hooks/set-state-in-effect */

import { ChangeEvent, useCallback, useEffect, useRef, useState } from "react";
import { BackofficeShell } from "@/components/backoffice/BackofficeShell";
import {
  ReportNotFoundError,
  completedWeekMondays,
  fetchWeeklyReport,
  formatMoney,
  mostRecentCompletedMonday,
  officeLabel,
  programmeLabel,
  weekRangeLabel,
  type ReportEntry,
  type WeeklyReport,
} from "@/lib/reporting";

const AVAILABLE_WEEKS = 12;

export default function ReportingPage() {
  const weeks = completedWeekMondays(AVAILABLE_WEEKS);
  const [selectedWeek, setSelectedWeek] = useState<string>(() =>
    mostRecentCompletedMonday()
  );
  const [report, setReport] = useState<WeeklyReport | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [isNotFound, setIsNotFound] = useState(false);
  const requestSequence = useRef(0);

  const loadReport = useCallback(async (weekStart: string) => {
    const sequence = ++requestSequence.current;
    setIsLoading(true);
    setLoadError("");
    setIsNotFound(false);

    try {
      const data = await fetchWeeklyReport(weekStart);
      if (sequence !== requestSequence.current) {
        return; // A newer week was selected; never overwrite it with a stale response.
      }
      setReport(data);
    } catch (error) {
      if (sequence !== requestSequence.current) {
        return;
      }
      setReport(null);
      if (error instanceof ReportNotFoundError) {
        setIsNotFound(true);
        return;
      }
      setLoadError(
        error instanceof Error ? error.message : "Unable to load the weekly report."
      );
    } finally {
      if (sequence === requestSequence.current) {
        setIsLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    void loadReport(selectedWeek);
  }, [loadReport, selectedWeek]);

  const handleWeekChange = (event: ChangeEvent<HTMLSelectElement>) => {
    setSelectedWeek(event.target.value);
  };

  const hasAnyActivity =
    report !== null &&
    report.entries.some(
      (entry) =>
        entry.total_material_cost > 0 ||
        entry.kits_delivered_count > 0 ||
        entry.shortage_events_count > 0 ||
        entry.cost_variance_events_count > 0
    );

  const renderCountRow = (
    entry: ReportEntry,
    value: number,
    keyPrefix: string
  ) => (
    <tr key={`${keyPrefix}-${entry.office}-${entry.programme_id}`}>
      <td>{officeLabel(entry.office)}</td>
      <td>
        <strong>{programmeLabel(entry.programme_id)}</strong>
      </td>
      <td>{value}</td>
    </tr>
  );

  return (
    <BackofficeShell
      eyebrow="Reporting / Nexova"
      title="Weekly Office & Programme Performance Report"
      initials="RP"
      connectedLabel="Reporting API"
    >
      <section className="inventory-hero">
        <div>
          <p>01 / Business performance</p>
          <h2>Weekly material investment and delivery, per office and programme.</h2>
          <span>
            Material cost stays in each office&apos;s local currency. Kits Delivered
            counts delivery events, and the shortage and variance frequencies count
            captured alerts.
          </span>
        </div>
        <b>
          NEX
          <br />
          RPT
        </b>
      </section>

      <section className="inventory-card inventory-form-card">
        <header>
          <h2>Reporting week</h2>
          <small>Completed UTC weeks only</small>
        </header>
        <label>
          Week
          <select value={selectedWeek} onChange={handleWeekChange} disabled={isLoading}>
            {weeks.map((week) => (
              <option key={week} value={week}>
                {week} ({weekRangeLabel(week)})
              </option>
            ))}
          </select>
        </label>
      </section>

      {loadError ? (
        <p className="inventory-error" role="alert">
          {loadError}{" "}
          <button type="button" onClick={() => void loadReport(selectedWeek)}>
            Try again
          </button>
        </p>
      ) : null}

      {isNotFound ? (
        <section className="inventory-card">
          <header>
            <h2>No report</h2>
            <small>Missing computation</small>
          </header>
          <p className="inventory-stock-hint">
            No report has been computed for this week. Pick another completed
            week, or ask an operations manager to trigger a pipeline run.
          </p>
        </section>
      ) : null}

      {report ? (
        <section className="inventory-card">
          <header>
            <h2>Reporting period</h2>
            <small>UTC</small>
          </header>
          <p className="inventory-stock-hint">
            Week starting <strong>{report.week_start}</strong> —{" "}
            <strong>{weekRangeLabel(report.week_start)}</strong>
          </p>
        </section>
      ) : null}

      <section className="inventory-card">
        <header>
          <h2>Material Cost per Office/Programme</h2>
          <small>Inbound material spend, in the office&apos;s local currency</small>
        </header>
        <div className="inventory-table-wrapper">
          <table className="inventory-table">
            <thead>
              <tr>
                <th>Office</th>
                <th>Programme</th>
                <th>Material cost</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr>
                  <td colSpan={3}>Loading weekly report...</td>
                </tr>
              ) : report ? (
                report.entries.map((entry) => (
                  <tr key={`cost-${entry.office}-${entry.programme_id}`}>
                    <td>{officeLabel(entry.office)}</td>
                    <td>
                      <strong>{programmeLabel(entry.programme_id)}</strong>
                    </td>
                    <td>
                      {formatMoney(entry.total_material_cost, entry.currency)}
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={3}>No report loaded.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <p className="inventory-stock-hint">
          Costs are shown per row in that office&apos;s currency. Valencia reports
          EUR and Miami reports USD; there is deliberately no cross-currency
          total.
        </p>
      </section>

      <section className="inventory-card">
        <header>
          <h2>Kits Delivered</h2>
          <small>Delivery events per programme</small>
        </header>
        <div className="inventory-table-wrapper">
          <table className="inventory-table">
            <thead>
              <tr>
                <th>Office</th>
                <th>Programme</th>
                <th>Kits delivered</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr>
                  <td colSpan={3}>Loading weekly report...</td>
                </tr>
              ) : report ? (
                report.entries.map((entry) =>
                  renderCountRow(entry, entry.kits_delivered_count, "kits")
                )
              ) : (
                <tr>
                  <td colSpan={3}>No report loaded.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <p className="inventory-stock-hint">
          Kits Delivered counts delivery events, not individual kits: one
          outbound order counts once, whatever its quantity.
        </p>
      </section>

      <section className="inventory-card">
        <header>
          <h2>Shortage Frequency</h2>
          <small>Captured stock-threshold alerts per programme</small>
        </header>
        <div className="inventory-table-wrapper">
          <table className="inventory-table">
            <thead>
              <tr>
                <th>Office</th>
                <th>Programme</th>
                <th>Shortage events</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr>
                  <td colSpan={3}>Loading weekly report...</td>
                </tr>
              ) : report ? (
                report.entries.map((entry) =>
                  renderCountRow(entry, entry.shortage_events_count, "shortage")
                )
              ) : (
                <tr>
                  <td colSpan={3}>No report loaded.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <p className="inventory-stock-hint">
          Shortage Frequency counts captured threshold alerts; the inventory
          emitter throttles these alerts, so it is not a full census of every
          minute a product is below its minimum.
        </p>
      </section>

      <section className="inventory-card">
        <header>
          <h2>Cost Variance Frequency</h2>
          <small>Captured price-variance alerts per programme</small>
        </header>
        <div className="inventory-table-wrapper">
          <table className="inventory-table">
            <thead>
              <tr>
                <th>Office</th>
                <th>Programme</th>
                <th>Variance events</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr>
                  <td colSpan={3}>Loading weekly report...</td>
                </tr>
              ) : report ? (
                report.entries.map((entry) =>
                  renderCountRow(entry, entry.cost_variance_events_count, "variance")
                )
              ) : (
                <tr>
                  <td colSpan={3}>No report loaded.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <p className="inventory-stock-hint">
          Cost Variance Frequency counts captured price-variance alerts against
          historical supplier prices; the emitter throttles these alerts too.
        </p>
      </section>

      {report && !hasAnyActivity && !isLoading ? (
        <section className="inventory-card">
          <header>
            <h2>No activity this week</h2>
            <small>Computed zero</small>
          </header>
          <p className="inventory-stock-hint">
            The pipeline ran and found no events for this week, so every
            programme shows zero. This is a computed result, not a missing
            report.
          </p>
        </section>
      ) : null}
    </BackofficeShell>
  );
}
