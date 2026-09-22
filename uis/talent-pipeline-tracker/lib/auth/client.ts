import { clearToken, getToken } from "./storage";

export const AUTH_API_URL =
  process.env.NEXT_PUBLIC_AUTH_API_URL ?? "http://localhost:8000";

let isRedirecting = false;

export function redirectToLogin(): void {
  if (typeof window === "undefined" || isRedirecting) {
    return;
  }

  isRedirecting = true;
  clearToken();

  const current = `${window.location.pathname}${window.location.search}`;
  const target = current.startsWith("/login")
    ? "/login"
    : `/login?next=${encodeURIComponent(current)}`;

  window.location.assign(target);
}

function buildHeaders(init: RequestInit): Headers {
  const headers = new Headers(init.headers);

  if (
    init.body &&
    !(init.body instanceof FormData) &&
    !headers.has("Content-Type")
  ) {
    headers.set("Content-Type", "application/json");
  }

  const token = getToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  return headers;
}

export async function authorizedFetch(
  url: string,
  init: RequestInit = {}
): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(url, {
      ...init,
      headers: buildHeaders(init),
      cache: "no-store",
    });
  } catch {
    throw new Error(
      "Network error — unable to reach the server. Please check your connection and try again."
    );
  }

  if (response.status === 401) {
    redirectToLogin();
  }

  return response;
}
