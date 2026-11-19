// Typed client for the incident CSV analyzer's async task queue.
//
// `POST /api/incidents/analyze` no longer runs the analysis synchronously:
// it stages the upload and returns `202 {task_id}` immediately. The client
// polls `GET /tasks/{task_id}` until the Celery worker finishes, then reads
// the result (or the failure) from the same response.

import { parseApiError } from "./api/errors";

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

export type TaskStatusName = "pending" | "started" | "success" | "failure";

export interface TaskStatus {
  task_id: string;
  status: TaskStatusName;
  result: Analysis | null;
  error: string | null;
}

export const DEFAULT_POLL_INTERVAL_MS = 1000;
export const DEFAULT_POLL_TIMEOUT_MS = 5 * 60 * 1000; // large CSVs take a while

export async function analyzeIncident(file: File, apiUrl: string): Promise<string> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch(`${apiUrl}/api/incidents/analyze`, {
    method: "POST",
    body: formData,
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(parseApiError(payload, "The incident file could not be analyzed."));
  }
  if (!payload || typeof payload.task_id !== "string" || !payload.task_id) {
    throw new Error("The analyzer did not return a task id.");
  }
  return payload.task_id;
}

export async function fetchTaskStatus(taskId: string, apiUrl: string): Promise<TaskStatus> {
  const response = await fetch(`${apiUrl}/tasks/${taskId}`);
  const payload = await response.json().catch(() => null);
  if (!response.ok || !payload) {
    throw new Error(parseApiError(payload, "The task status could not be read."));
  }
  return payload as TaskStatus;
}

export interface PollOptions {
  intervalMs?: number;
  timeoutMs?: number;
  now?: () => number;
  sleep?: (ms: number) => Promise<void>;
}

export async function pollTaskStatus(
  taskId: string,
  apiUrl: string,
  options: PollOptions = {},
): Promise<TaskStatus> {
  const {
    intervalMs = DEFAULT_POLL_INTERVAL_MS,
    timeoutMs = DEFAULT_POLL_TIMEOUT_MS,
    now = Date.now,
    sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
  } = options;

  const deadline = now() + timeoutMs;
  let status = await fetchTaskStatus(taskId, apiUrl);
  while (status.status === "pending" || status.status === "started") {
    if (now() >= deadline) {
      throw new Error(
        "The analysis is taking longer than expected. Its status can still be checked in Flower.",
      );
    }
    await sleep(intervalMs);
    status = await fetchTaskStatus(taskId, apiUrl);
  }
  return status;
}
