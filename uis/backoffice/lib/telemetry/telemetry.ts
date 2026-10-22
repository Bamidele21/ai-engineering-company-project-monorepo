import {
  DEFAULT_BATCH_SIZE,
  DEFAULT_FLUSH_MS,
  EVENT_SCHEMA_VERSIONS,
  MAX_RETRIES,
  RETRY_BASE_MS,
  SCHEMA_VERSION,
  TELEMETRY_SOURCE,
  telemetryEndpoint,
} from "./constants";
import {
  allowedProperties,
  hasRequiredProperties,
  isSupportedFrontendEvent,
  resetCatalogForTests,
} from "./catalog";
import {
  createRequestId,
  getSessionId,
  getSessionUserId,
  randomUuid,
  resetTelemetrySessionForTests,
} from "./session";

export interface TelemetryEventPayload {
  eventId: string;
  timestamp: string;
  sessionId: string;
  userId: string | null;
  event_type: string;
  schemaVersion: string;
  requestId: string;
  source: typeof TELEMETRY_SOURCE;
  properties: Record<string, unknown>;
}

let queue: TelemetryEventPayload[] = [];
let flushTimer: ReturnType<typeof setTimeout> | null = null;
let warnedMissingEndpoint = false;

function clearFlushTimer(): void {
  if (flushTimer !== null) {
    clearTimeout(flushTimer);
    flushTimer = null;
  }
}

function scheduleFlush(): void {
  if (flushTimer !== null) {
    return;
  }
  flushTimer = setTimeout(() => {
    flushTimer = null;
    void flushTelemetry("timer");
  }, DEFAULT_FLUSH_MS);
}

function buildEvent(
  eventType: string,
  properties: Record<string, unknown>,
  requestId: string
): TelemetryEventPayload {
  return {
    eventId: randomUuid(),
    timestamp: new Date().toISOString(),
    sessionId: getSessionId(),
    userId: getSessionUserId(),
    event_type: eventType,
    schemaVersion: EVENT_SCHEMA_VERSIONS[eventType] ?? SCHEMA_VERSION,
    requestId,
    source: TELEMETRY_SOURCE,
    properties,
  };
}

export function track(
  eventType: string,
  properties: Record<string, unknown>
): void {
  trackWithRequestId(eventType, properties, createRequestId());
}

export function trackWithRequestId(
  eventType: string,
  properties: Record<string, unknown>,
  requestId: string
): void {
  if (typeof window === "undefined" || !isSupportedFrontendEvent(eventType)) {
    return;
  }

  const filtered = allowedProperties(eventType, properties);
  if (filtered.rejected.length > 0) {
    console.warn(
      `Telemetry dropped disallowed properties for ${eventType}: ${filtered.rejected.join(", ")}`
    );
  }
  if (!hasRequiredProperties(eventType, filtered.allowed)) {
    console.warn(`Telemetry dropped incomplete event: ${eventType}`);
    return;
  }

  queue.push(buildEvent(eventType, filtered.allowed, requestId));

  if (queue.length >= DEFAULT_BATCH_SIZE) {
    void flushTelemetry("threshold");
    return;
  }

  scheduleFlush();
}

function beaconBatch(batch: TelemetryEventPayload[]): boolean {
  const endpoint = telemetryEndpoint();
  if (!endpoint) {
    return true;
  }

  if (
    typeof navigator === "undefined" ||
    typeof navigator.sendBeacon !== "function"
  ) {
    return false;
  }

  const body = new Blob([JSON.stringify({ events: batch })], {
    type: "application/json",
  });
  return navigator.sendBeacon(endpoint, body);
}

function delay(milliseconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function sendBatch(
  batch: TelemetryEventPayload[],
  keepalive: boolean
): Promise<void> {
  const endpoint = telemetryEndpoint();
  if (!endpoint) {
    if (!warnedMissingEndpoint) {
      warnedMissingEndpoint = true;
      console.warn(
        "NEXT_PUBLIC_TELEMETRY_ENDPOINT is not configured; telemetry is disabled."
      );
    }
    return;
  }

  for (let attempt = 0; attempt <= MAX_RETRIES; attempt += 1) {
    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ events: batch }),
        cache: "no-store",
        keepalive,
      });
      if (response.ok) {
        return;
      }
    } catch {
      // Retries below are deliberate; delivery failures never emit telemetry.
    }

    if (attempt < MAX_RETRIES) {
      await delay(RETRY_BASE_MS * 2 ** attempt);
    }
  }
}

export async function flushTelemetry(
  reason: "timer" | "threshold" | "hidden" | "manual" = "manual"
): Promise<void> {
  clearFlushTimer();

  if (queue.length === 0) {
    return;
  }

  const batch = queue;
  queue = [];

  if (reason === "hidden" && beaconBatch(batch)) {
    return;
  }

  await sendBatch(batch, reason === "hidden");
}

export function installTelemetryLifecycle(): () => void {
  if (typeof window === "undefined") {
    return () => undefined;
  }

  const onVisibilityChange = () => {
    if (document.visibilityState === "hidden") {
      void flushTelemetry("hidden");
    }
  };
  const onPageHide = () => {
    void flushTelemetry("hidden");
  };

  window.addEventListener("visibilitychange", onVisibilityChange);
  window.addEventListener("pagehide", onPageHide);

  return () => {
    window.removeEventListener("visibilitychange", onVisibilityChange);
    window.removeEventListener("pagehide", onPageHide);
  };
}

export function resetTelemetryForTests(): void {
  clearFlushTimer();
  queue = [];
  warnedMissingEndpoint = false;
  resetCatalogForTests();
  resetTelemetrySessionForTests();
}

export function pendingTelemetryCount(): number {
  return queue.length;
}
