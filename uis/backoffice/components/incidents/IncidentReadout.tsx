"use client";

export type Analysis = {
  total: number;
  valid: number;
  invalid: number;
  invalid_counts: Record<string, number>;
  category_counts: Record<string, number>;
  status_counts: Record<string, number>;
  closed_count: number;
  scored_count: number;
  average_score: number | null;
};

const invalidLabels: Record<string, string> = {
  missing_client_company: "Missing client company",
  invalid_category: "Invalid or missing category",
  invalid_email: "Invalid or missing email",
  closed_without_score: "Closed ticket without score",
  invalid_description: "Invalid or missing description",
  invalid_agent_id: "Invalid or missing agent ID",
  invalid_satisfaction_score: "Satisfaction score out of range",
};

function Metric({ label, value, detail, accent = false }: { label: string; value: string; detail: string; accent?: boolean }) {
  return <article className={`incident-metric ${accent ? "incident-metric-accent" : ""}`}><span>{label}</span><strong>{value}</strong><small>{detail}</small></article>;
}

interface IncidentReadoutProps {
  analysis: Analysis;
  exportUrl: string;
}

export default function IncidentReadout({ analysis, exportUrl }: IncidentReadoutProps) {
  const validRate = analysis.total ? Math.round((analysis.valid / analysis.total) * 100) : 0;
  const formatNumber = (value: number) => new Intl.NumberFormat("en-US").format(value);

  return (
    <section id="summary">
      <div className="incident-results-header">
        <div>
          <p>02 / Readout</p>
          <h2>Report summary</h2>
          <span>Validated records only are used for the category, status, and satisfaction breakdowns.</span>
        </div>
        <a href={exportUrl}>Download results ↓</a>
      </div>
      <div className="incident-metrics">
        <Metric label="Total records" value={formatNumber(analysis.total)} detail="Rows received" accent />
        <Metric label="Valid records" value={formatNumber(analysis.valid)} detail={`${validRate}% of the report`} />
        <Metric label="Needs review" value={formatNumber(analysis.invalid)} detail="Records with issues" />
        <Metric label="Average satisfaction" value={analysis.average_score === null ? "N/A" : `${analysis.average_score.toFixed(2)}/5`} detail={`${analysis.scored_count} scored closed tickets`} />
      </div>
      <div className="incident-summary-grid">
        <article>
          <header>
            <div>
              <p>Record quality</p>
              <h3>Invalid records</h3>
            </div>
            <b>{analysis.invalid}</b>
          </header>
          {analysis.invalid ? Object.entries(analysis.invalid_counts).filter(([, count]) => count > 0).map(([key, count]) => <div className="incident-issue" key={key}><span>{invalidLabels[key] ?? key}</span><strong>{count}</strong></div>) : <span className="incident-muted">No invalid records found. This report is ready for operational use.</span>}
        </article>
        <article>
          <header>
            <div>
              <p>Valid records</p>
              <h3>By category</h3>
            </div>
            <b>{analysis.valid}</b>
          </header>
          <div className="incident-bars">
            {Object.entries(analysis.category_counts).map(([category, count]) => <div key={category}><span>{category.replace("_", " ")} <strong>{count}</strong></span><i><em style={{ width: `${analysis.valid ? (count / analysis.valid) * 100 : 0}%` }} /></i></div>)}
          </div>
        </article>
        <article>
          <header>
            <div>
              <p>Valid records</p>
              <h3>By status</h3>
            </div>
            <b>{analysis.valid}</b>
          </header>
          <div className="incident-statuses">
            {Object.entries(analysis.status_counts).map(([status, count]) => <div key={status}><i className={status.toLowerCase()} />{status}<strong>{count}</strong></div>)}
          </div>
          <div className="incident-score">Scored closed tickets<strong>{analysis.scored_count} <small>of {analysis.closed_count}</small></strong></div>
        </article>
      </div>
    </section>
  );
}
