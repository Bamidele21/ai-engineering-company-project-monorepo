const EVENT_ALLOWLISTS: Record<string, readonly string[]> = {
  page_view: ["page_path", "load_duration_ms", "referrer_path"],
  frontend_error_captured: [
    "error_type",
    "message",
    "page_path",
    "source",
    "stack_frame",
  ],
  network_request_failed: ["target", "page_path"],
  validation_failed: ["source", "context", "field", "reason", "page_path"],
};

const REQUIRED_PROPERTIES: Record<string, readonly string[]> = {
  page_view: ["page_path"],
  frontend_error_captured: ["error_type", "message", "page_path", "source"],
  network_request_failed: ["target", "page_path"],
  validation_failed: ["source", "context", "field", "reason"],
};

const throttleState = new Map<string, number>();

export function isSupportedFrontendEvent(eventType: string): boolean {
  return Object.prototype.hasOwnProperty.call(EVENT_ALLOWLISTS, eventType);
}

export function allowedProperties(
  eventType: string,
  properties: Record<string, unknown>
): { allowed: Record<string, unknown>; rejected: string[] } {
  const allowlist = EVENT_ALLOWLISTS[eventType] ?? [];
  const allowed: Record<string, unknown> = {};
  const rejected: string[] = [];

  for (const [key, value] of Object.entries(properties)) {
    if (allowlist.includes(key)) {
      allowed[key] = value;
    } else {
      rejected.push(key);
    }
  }

  return { allowed, rejected };
}

export function hasRequiredProperties(
  eventType: string,
  properties: Record<string, unknown>
): boolean {
  const required = REQUIRED_PROPERTIES[eventType] ?? [];
  return required.every((key) => properties[key] !== undefined && properties[key] !== null);
}

export function shouldEmitThrottled(
  key: string,
  windowMs: number,
  now: number = Date.now()
): boolean {
  const last = throttleState.get(key);
  if (last !== undefined && now - last < windowMs) {
    return false;
  }
  throttleState.set(key, now);
  return true;
}

export function resetCatalogForTests(): void {
  throttleState.clear();
}
