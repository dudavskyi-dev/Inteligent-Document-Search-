import type { JobStatusResponse } from "../types/extraction";

async function asJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status} ${response.statusText}`);
  }
  return (await response.json()) as T;
}

export async function getSettings(): Promise<{ model: string }> {
  const response = await fetch("/api/settings");
  return asJson(response);
}

export async function putSettings(model: string): Promise<{ model: string }> {
  const response = await fetch("/api/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model }),
  });
  return asJson(response);
}

export async function uploadFile(file: File): Promise<{ file_id: string; filename: string }> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch("/api/upload", { method: "POST", body: formData });
  return asJson(response);
}

export async function createJob(fileId: string): Promise<{ job_id: string }> {
  const response = await fetch("/api/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ file_id: fileId }),
  });
  return asJson(response);
}

export async function getJob(jobId: string): Promise<JobStatusResponse> {
  const response = await fetch(`/api/jobs/${jobId}`);
  return asJson(response);
}
