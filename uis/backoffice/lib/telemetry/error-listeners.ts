import { shouldEmitThrottled } from "./catalog";
import { pagePath, firstStackFrame, sanitizeMessage } from "./sanitize";
import { getSessionId } from "./session";
import { track } from "./telemetry";

type ErrorSource = "window_onerror" | "unhandledrejection" | "error_boundary";

const ERROR_CAP_PER_MINUTE = 10;
let errorWindowStartedAt = 0;
let errorCountInWindow = 0;

function withinErrorBudget(now: number = Date.now()): boolean {
  if (now - errorWindowStartedAt >= 60_000) {
    errorWindowStartedAt = now;
    errorCountInWindow = 0;
  }
  if (errorCountInWindow >= ERROR_CAP_PER_MINUTE) {
    return false;
  }
  errorCountInWindow += 1;
  return true;
}

export function resetErrorListenersForTests(): void {
  errorWindowStartedAt = 0;
  errorCountInWindow = 0;
}

function errorDetails(error: unknown, fallback: string): {
  errorType: string;
  message: string;
  stack?: string;
} {
  if (error instanceof Error) {
    return {
      errorType: error.name || "Error",
      message: error.message || fallback,
      stack: error.stack,
    };
  }
  if (typeof error === "string") {
    return { errorType: "Error", message: error };
  }
  return { errorType: "UnhandledRejection", message: fallback };
}

export function trackFrontendError(
  error: unknown,
  source: ErrorSource,
  pathname: string,
  fallback = "Unknown frontend error"
): void {
  if (typeof window === "undefined") {
    return;
  }

  if (!withinErrorBudget()) {
    return;
  }

  const sessionId = getSessionId();
  const details = errorDetails(error, fallback);
  const message = sanitizeMessage(details.message);
  const sameKey = `error_same:${sessionId}:${details.errorType}:${message}`;
  if (!shouldEmitThrottled(sameKey, 5 * 60_000)) {
    return;
  }

  track("frontend_error_captured", {
    error_type: details.errorType.slice(0, 200),
    message,
    page_path: pagePath(pathname),
    source,
    stack_frame: firstStackFrame(details.stack),
  });
}

export function installErrorListeners(): () => void {
  if (typeof window === "undefined") {
    return () => undefined;
  }

  const onError = (event: ErrorEvent) => {
    trackFrontendError(
      event.error ?? event.message,
      "window_onerror",
      window.location.pathname,
      event.message
    );
  };

  const onUnhandledRejection = (event: PromiseRejectionEvent) => {
    trackFrontendError(
      event.reason,
      "unhandledrejection",
      window.location.pathname
    );
  };

  window.addEventListener("error", onError);
  window.addEventListener("unhandledrejection", onUnhandledRejection);

  return () => {
    window.removeEventListener("error", onError);
    window.removeEventListener("unhandledrejection", onUnhandledRejection);
  };
}
