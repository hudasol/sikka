// API client. In live mode it calls the API started with `sikka serve`; in static
// mode it reads the precomputed snapshot shipped in public/snapshot. Nothing else
// is fetched: no tiles, fonts, analytics or third party services.

import type { Problem, Sample, ValidateResponse } from "./types";

declare const __SIKKA_MODE__: "live" | "static";

export const MODE: "live" | "static" =
  typeof __SIKKA_MODE__ === "undefined" ? "static" : __SIKKA_MODE__;

const LIVE_BASE = (import.meta.env.VITE_SIKKA_API as string | undefined) ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  readonly status: number;
  readonly problem: Problem | null;

  constructor(status: number, message: string, problem: Problem | null = null) {
    super(message);
    this.status = status;
    this.problem = problem;
  }
}

export class StaticModeError extends Error {}

export function snapshotUrl(path: string): string {
  return `${import.meta.env.BASE_URL}snapshot${path}.json`;
}

export function apiUrl(path: string): string {
  return MODE === "static" ? snapshotUrl(path) : `${LIVE_BASE}${path}`;
}

async function parseError(response: Response): Promise<ApiError> {
  let problem: Problem | null = null;
  try {
    problem = (await response.json()) as Problem;
  } catch {
    problem = null;
  }
  return new ApiError(response.status, problem?.detail ?? response.statusText, problem);
}

export async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(apiUrl(path), { headers: { Accept: "application/json" } });
  if (!response.ok) {
    throw await parseError(response);
  }
  return (await response.json()) as T;
}

export async function validateSample(sample: Sample): Promise<ValidateResponse> {
  if (MODE === "static") {
    if (!sample.report_id) {
      throw new StaticModeError("This sample has no precomputed report in the static build.");
    }
    return { report_id: sample.report_id, notice: "" };
  }
  const body = new FormData();
  body.set("sample", sample.name);
  const response = await fetch(`${LIVE_BASE}/v1/validate`, { method: "POST", body });
  if (!response.ok) {
    throw await parseError(response);
  }
  return (await response.json()) as ValidateResponse;
}

export async function validateUpload(file: File): Promise<ValidateResponse> {
  if (MODE === "static") {
    throw new StaticModeError("Uploads need the live API.");
  }
  const body = new FormData();
  body.set("file", file, file.name);
  const response = await fetch(`${LIVE_BASE}/v1/validate`, { method: "POST", body });
  if (!response.ok) {
    throw await parseError(response);
  }
  return (await response.json()) as ValidateResponse;
}

export function reportHtmlUrl(reportId: string): string {
  return MODE === "static"
    ? `${import.meta.env.BASE_URL}snapshot/v1/reports/${reportId}.html`
    : `${LIVE_BASE}/v1/reports/${reportId}?format=html`;
}

export function reportJsonUrl(reportId: string): string {
  return apiUrl(`/v1/reports/${reportId}`);
}
