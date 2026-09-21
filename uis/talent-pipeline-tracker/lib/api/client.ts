import { redirectToLogin } from "@/lib/auth/client";
import { getToken } from "@/lib/auth/storage";

const API_BASE_URL = process.env.PROJECT_API_URL;

function assertApiBaseUrl() {
  if (!API_BASE_URL) {
    throw new Error("Missing PROJECT_API_URL. Define it in .env before running the app.");
  }
}

interface ApiErrorPayload {
  detail?: string | Array<{ msg?: string }>;
}

function parseApiErrorBody(body: string, status: number): string {
  const fallback = `Request failed with status ${status}`;

  let payload: unknown;
  try {
    payload = JSON.parse(body);
  } catch {
    return fallback;
  }

  if (!payload || typeof payload !== "object") {
    return fallback;
  }

  const errorPayload = payload as ApiErrorPayload;
  if (typeof errorPayload.detail === "string" && errorPayload.detail.trim()) {
    return errorPayload.detail;
  }

  if (Array.isArray(errorPayload.detail)) {
    const messages = errorPayload.detail
      .map((entry) => entry.msg)
      .filter((entry): entry is string => Boolean(entry));

    if (messages.length > 0) {
      return messages.join(". ");
    }
  }

  return fallback;
}

async function throwApiError(response: Response): Promise<never> {
  const rawBody = await response.text();
  console.error(`API request failed (${response.status}):`, rawBody);
  throw new Error(parseApiErrorBody(rawBody, response.status));
}

function buildAuthHeaders(init?: RequestInit): Headers {
  const headers = new Headers(init?.headers);
  const token = getToken();

  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  return headers;
}

function handleUnauthorized(response: Response): void {
  if (response.status === 401) {
    redirectToLogin();
  }
}

export async function apiJsonRequest<T>(path: string, init?: RequestInit): Promise<T> {
  assertApiBaseUrl();

  const headers = buildAuthHeaders(init);
  if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });

  handleUnauthorized(response);

  if (!response.ok) {
    return throwApiError(response);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export async function apiNoContentRequest(path: string, init?: RequestInit): Promise<void> {
  assertApiBaseUrl();

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: buildAuthHeaders(init),
    cache: "no-store",
  });

  handleUnauthorized(response);

  if (!response.ok) {
    return throwApiError(response);
  }
}
