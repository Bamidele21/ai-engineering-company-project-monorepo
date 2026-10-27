import { clearToken, getToken } from "./storage";
import { shouldEmitThrottled } from "../telemetry/catalog";
import { normalizeNetworkTarget, pagePath } from "../telemetry/sanitize";
import {
  createRequestId,
  endSession,
  getSessionId,
} from "../telemetry/session";
import { trackWithRequestId } from "../telemetry/telemetry";

export const AUTH_API_URL =
  process.env.NEXT_PUBLIC_SUPPLIERS_API_URL ?? "http://localhost:8000";

let isRedirecting = false;

export function redirectToLogin(): void {
  if (typeof window === "undefined" || isRedirecting) {
    return;
  }

  isRedirecting = true;
  clearToken();
  endSession();

  const current = `${window.location.pathname}${window.location.search}`;
  const target = current.startsWith("/login")
    ? "/login"
    : `/login?next=${encodeURIComponent(current)}`;

  window.location.assign(target);
}

function buildHeaders(init: RequestInit, requestId: string): Headers {
  const headers = new Headers(init.headers);

  if (
    init.body &&
    !(init.body instanceof FormData) &&
    !headers.has("Content-Type")
  ) {
    headers.set("Content-Type", "application/json");
  }

  headers.set("X-Request-Id", requestId);
  headers.set("X-Session-Id", getSessionId());

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
  const requestId = createRequestId();
  let response: Response;
  try {
    response = await fetch(url, {
      ...init,
      headers: buildHeaders(init, requestId),
      cache: "no-store",
    });
  } catch {
    const target = normalizeNetworkTarget(url);
    const currentPath = pagePath(
      typeof window === "undefined" ? "/" : window.location.pathname
    );
    const throttleKey = `network:${getSessionId()}:${target}:${currentPath}`;
    if (shouldEmitThrottled(throttleKey, 60_000)) {
      trackWithRequestId(
        "network_request_failed",
        { target, page_path: currentPath },
        requestId
      );
    }
    throw new Error(
      "Network error — unable to reach the server. Please check your connection and try again."
    );
  }

  if (response.status === 401) {
    redirectToLogin();
  }

  return response;
}
