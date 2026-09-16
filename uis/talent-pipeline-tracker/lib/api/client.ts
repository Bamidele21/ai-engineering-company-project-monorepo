import { redirectToLogin } from "@/lib/auth/client";
import { getToken } from "@/lib/auth/storage";

const API_BASE_URL = process.env.PROJECT_API_URL;

function assertApiBaseUrl() {
  if (!API_BASE_URL) {
    throw new Error("Missing PROJECT_API_URL. Define it in .env before running the app.");
  }
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
    const errorBody = await response.text();
    throw new Error(errorBody || `Request failed with status ${response.status}`);
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
    const errorBody = await response.text();
    throw new Error(errorBody || `Request failed with status ${response.status}`);
  }
}
