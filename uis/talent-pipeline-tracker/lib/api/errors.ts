interface ApiErrorPayload {
  detail?: string | Array<{ msg?: string }>;
}

/**
 * Normalise a FastAPI error body into a single human-readable message.
 *
 * FastAPI returns `detail` either as a string or as a list of validation
 * objects (`[{ "msg": ... }, ...]`). This helper flattens both shapes, joining
 * array messages with ". ", and falls back when the payload is null, a
 * non-object, or carries no usable detail.
 */
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
