"use client";

import { ChangeEvent, DragEvent, useState } from "react";
import dynamic from "next/dynamic";
import { BackofficeShell } from "@/components/backoffice/BackofficeShell";
import type { Analysis } from "@/components/incidents/IncidentReadout";

const IncidentReadout = dynamic(
  () => import("@/components/incidents/IncidentReadout"),
  {
    loading: () => (
      <p className="incident-success" role="status">
        Loading the report summary...
      </p>
    ),
  }
);

const API_URL = process.env.NEXT_PUBLIC_ANALYZER_API_URL ?? "http://localhost:8000";

export default function IncidentsPage() {
  const [file, setFile] = useState<File | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [error, setError] = useState("");
  const [isDragging, setIsDragging] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const chooseFile = (nextFile: File | undefined) => { setError(""); setAnalysis(null); if (!nextFile) return; if (!nextFile.name.toLowerCase().endsWith(".csv")) { setFile(null); setError("Please choose a CSV file. Other file types cannot be analyzed."); return; } setFile(nextFile); };
  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => chooseFile(event.target.files?.[0]);
  const handleDrop = (event: DragEvent<HTMLLabelElement>) => { event.preventDefault(); setIsDragging(false); chooseFile(event.dataTransfer.files?.[0]); };
  const analyzeFile = async () => {
    if (!file) { setError("Choose an incident CSV before starting the analysis."); return; }
    setIsLoading(true); setError(""); setAnalysis(null);
    const formData = new FormData(); formData.append("file", file);
    try {
      const response = await fetch(`${API_URL}/api/incidents/analyze`, { method: "POST", body: formData });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail ?? "The incident file could not be analyzed.");
      setAnalysis(payload as Analysis);
    } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "The analyzer API is unavailable. Check that it is running and try again."); } finally { setIsLoading(false); }
  };
  const exportUrl = `${API_URL}/api/incidents/results/export`;

  return (
    <BackofficeShell
      eyebrow="Customer support operations / Nexova"
      title="Incident report analyzer"
      initials="RS"
      connectedLabel="Analyzer API connected locally"
      pageClassName="incident-page"
    >
      <section className="incident-hero" id="analyze">
        <div>
          <p>01 / Intake</p>
          <h2>Turn a support export into a useful brief.</h2>
          <span>Upload the latest incident report to validate its records and surface the patterns your support team needs to act on.</span>
        </div>
        <b>NEX<br />OPS</b>
      </section>

      <section className="incident-upload">
        <header>
          <div>
            <p>Source file</p>
            <h2>Upload incident CSV</h2>
          </div>
          <small>CSV only</small>
        </header>
        <label className={`incident-dropzone ${isDragging ? "dragging" : ""}`} onDragOver={(event) => { event.preventDefault(); setIsDragging(true); }} onDragLeave={() => setIsDragging(false)} onDrop={handleDrop}>
          <input type="file" accept=".csv,text/csv" onChange={handleFileChange} />
          <b>+</b>
          <strong>{file ? file.name : "Drop your CSV here"}</strong>
          <span>{file ? `${(file.size / 1024).toFixed(1)} KB ready to analyze` : "or choose a file from your computer"}</span>
        </label>
        <div className="incident-upload-actions">
          <span>Customer email values are never shown or exported.</span>
          <button type="button" onClick={analyzeFile} disabled={isLoading}>{isLoading ? "Analyzing..." : "Analyze report"} <b>-&gt;</b></button>
        </div>
        {error ? <p className="incident-error" role="alert">{error}</p> : null}
        {analysis ? <p className="incident-success" role="status">Analysis complete. The summary below is based on {file?.name}.</p> : null}
      </section>

      {analysis ? (
        <IncidentReadout analysis={analysis} exportUrl={exportUrl} />
      ) : (
        <section className="incident-empty" id="summary">
          <b>02</b>
          <div>
            <h2>Your summary will appear here.</h2>
            <span>Upload a report to see data quality, support demand, and customer satisfaction in one view.</span>
          </div>
        </section>
      )}

      <footer>Nexova customer support intelligence <i /> Privacy-first aggregate reporting</footer>
    </BackofficeShell>
  );
}
