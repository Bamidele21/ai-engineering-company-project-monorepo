interface ApiErrorPayload {
  detail?: string | Array<{ msg?: string }>;
}

// Normalises a FastAPI error body (a `detail` string or a validation-message
// array) into a single user-facing string, falling back when the payload is
// missing or unrecognised.
export function parseApiError(payload: unknown, fallback: string): string {
  if (!payload || typeof payload !== "object") {
    return fallback;
  }

  const errorPayload = payload as ApiErrorPayload;
  if (typeof errorPayload.detail === "string") {
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
