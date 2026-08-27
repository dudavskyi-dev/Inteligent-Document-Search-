import { useState } from "react";
import { createJob } from "./api/client";
import JobStatusBanner from "./components/JobStatusBanner";
import ResultsView from "./components/ResultsView";
import SettingsPanel from "./components/SettingsPanel";
import UploadControl from "./components/UploadControl";
import type { ExtractionCandidateResponse, JobStatus } from "./types/extraction";

export default function App() {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [fileId, setFileId] = useState<string | null>(null);
  const [filename, setFilename] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<JobStatus | null>(null);
  const [result, setResult] = useState<ExtractionCandidateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleProcess() {
    if (!fileId) return;
    setResult(null);
    setError(null);
    setJobStatus("queued");
    const job = await createJob(fileId);
    setJobId(job.job_id);
  }

  return (
    <div style={{ maxWidth: "900px", margin: "0 auto", padding: "1.5rem", fontFamily: "sans-serif" }}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>Document Extraction</h1>
        <button onClick={() => setSettingsOpen(true)}>Settings</button>
      </header>

      {settingsOpen && <SettingsPanel onClose={() => setSettingsOpen(false)} />}

      <section style={{ marginTop: "1.5rem" }}>
        <UploadControl
          onUploaded={(id, name) => {
            setFileId(id);
            setFilename(name);
            setJobId(null);
            setJobStatus(null);
            setResult(null);
            setError(null);
          }}
        />
        <button
          onClick={handleProcess}
          disabled={!fileId || jobStatus === "queued" || jobStatus === "running"}
          style={{ marginTop: "1rem" }}
        >
          Process
        </button>
        {filename && jobStatus === null && (
          <p style={{ color: "#666" }}>Ready to process "{filename}".</p>
        )}
      </section>

      {jobId && (jobStatus === "queued" || jobStatus === "running") && (
        <JobStatusBanner
          jobId={jobId}
          onSettled={(job) => {
            setJobStatus(job.status);
            if (job.status === "succeeded" && job.result) {
              setResult(job.result);
            } else if (job.status === "failed") {
              setError(job.error ?? "Processing failed.");
            }
          }}
        />
      )}

      {error && (
        <p style={{ color: "#a12622", background: "#fdeceb", padding: "0.75rem", borderRadius: "4px" }}>
          {error}
        </p>
      )}

      {result && <ResultsView result={result} />}
    </div>
  );
}
