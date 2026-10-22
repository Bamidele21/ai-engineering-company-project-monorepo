import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  jest,
} from "@jest/globals";
import {
  flushTelemetry,
  pendingTelemetryCount,
  resetTelemetryForTests,
  track,
} from "../telemetry/telemetry";

const fetchMock = jest.fn();
const sendBeaconMock = jest.fn();

function jsonResponse(status: number): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
  } as unknown as Response;
}

function setupBrowser(): void {
  const storage = new Map<string, string>();
  (globalThis as unknown as { window: unknown }).window = {
    location: { pathname: "/inventory/products" },
    addEventListener: jest.fn(),
    removeEventListener: jest.fn(),
    localStorage: {
      getItem: (key: string) => storage.get(key) ?? null,
      setItem: (key: string, value: string) => storage.set(key, value),
      removeItem: (key: string) => storage.delete(key),
    },
  };
  Object.defineProperty(globalThis, "navigator", {
    value: { sendBeacon: sendBeaconMock },
    configurable: true,
    writable: true,
  });
}

function sentBatch(callIndex = 0): {
  url: string;
  init: RequestInit;
  events: Array<Record<string, unknown>>;
} {
  const [url, init] = fetchMock.mock.calls[callIndex] as [string, RequestInit];
  return {
    url,
    init,
    events: JSON.parse(init.body as string).events,
  };
}

beforeEach(() => {
  jest.useRealTimers();
  resetTelemetryForTests();
  process.env.NEXT_PUBLIC_TELEMETRY_ENDPOINT =
    "http://localhost:8001/telemetry/events";
  fetchMock.mockReset();
  sendBeaconMock.mockReset();
  global.fetch = fetchMock as unknown as typeof fetch;
  setupBrowser();
});

afterEach(() => {
  jest.useRealTimers();
  resetTelemetryForTests();
  delete (globalThis as unknown as { window?: unknown }).window;
});

describe("track envelope", () => {
  it("adds the envelope fields automatically", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200));

    track("page_view", {
      page_path: "/inventory/products",
      load_duration_ms: 812,
    });
    await flushTelemetry("manual");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const batch = sentBatch();
    expect(batch.url).toBe("http://localhost:8001/telemetry/events");
    expect(batch.events).toHaveLength(1);
    const event = batch.events[0];
    expect(event.event_type).toBe("page_view");
    expect(event.source).toBe("web");
    expect(event.schemaVersion).toBe("1.0");
    expect(event.userId).toBeNull();
    expect(event.eventId).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
    );
    expect(event.sessionId).toBeTruthy();
    expect(event.requestId).toBeTruthy();
    expect(String(event.timestamp)).toMatch(/Z$/);
  });

  it("drops disallowed properties and unsupported events", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200));
    const warn = jest.spyOn(console, "warn").mockImplementation(() => undefined);

    track("page_view", {
      page_path: "/inventory/products",
      email: "elena@nexova.com",
    });
    track("page_view", { load_duration_ms: 100 });
    track("login_succeeded", { role: "admin" });
    await flushTelemetry("manual");

    const batch = sentBatch();
    expect(batch.events).toHaveLength(1);
    expect(batch.events[0].properties).toEqual({
      page_path: "/inventory/products",
    });
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });
});

describe("batching", () => {
  it("sends immediately at 20 events", async () => {
    fetchMock.mockResolvedValue(jsonResponse(200));

    for (let index = 0; index < 20; index += 1) {
      track("page_view", { page_path: `/route-${index}` });
    }
    await new Promise((resolve) => setImmediate(resolve));

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(sentBatch().events).toHaveLength(20);
    expect(pendingTelemetryCount()).toBe(0);
  });

  it("flushes no later than 10 seconds and does not postpone the timer", async () => {
    jest.useFakeTimers();
    fetchMock.mockResolvedValue(jsonResponse(200));

    track("page_view", { page_path: "/first" });
    await jest.advanceTimersByTimeAsync(6_000);
    track("page_view", { page_path: "/second" });
    await jest.advanceTimersByTimeAsync(3_999);
    expect(fetchMock).not.toHaveBeenCalled();

    await jest.advanceTimersByTimeAsync(1);
    await Promise.resolve();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(sentBatch().events).toHaveLength(2);
  });

  it("does nothing when the queue is empty", async () => {
    await flushTelemetry("manual");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("keeps an in-flight batch separate from newly queued events", async () => {
    let resolveFetch: (response: Response) => void = () => undefined;
    fetchMock.mockImplementationOnce(
      () =>
        new Promise<Response>((resolve) => {
          resolveFetch = resolve;
        })
    );

    track("page_view", { page_path: "/first" });
    const inFlight = flushTelemetry("manual");
    expect(pendingTelemetryCount()).toBe(0);

    track("page_view", { page_path: "/second" });
    expect(pendingTelemetryCount()).toBe(1);

    resolveFetch(jsonResponse(200));
    await inFlight;
  });
});

describe("delivery failures", () => {
  it("retries an initial send plus three times, then drops", async () => {
    jest.useFakeTimers();
    fetchMock.mockRejectedValue(new Error("network down"));

    track("page_view", { page_path: "/inventory/products" });
    const flush = flushTelemetry("manual");

    await jest.advanceTimersByTimeAsync(500);
    await jest.advanceTimersByTimeAsync(1_000);
    await jest.advanceTimersByTimeAsync(2_000);
    await flush;

    expect(fetchMock).toHaveBeenCalledTimes(4);
    expect(pendingTelemetryCount()).toBe(0);
  });

  it("stops retrying after the first successful send", async () => {
    jest.useFakeTimers();
    fetchMock
      .mockRejectedValueOnce(new Error("network down"))
      .mockResolvedValueOnce(jsonResponse(200));

    track("page_view", { page_path: "/inventory/products" });
    const flush = flushTelemetry("manual");

    await jest.advanceTimersByTimeAsync(500);
    await flush;

    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});

describe("visibility lifecycle", () => {
  it("uses sendBeacon when the page becomes hidden", async () => {
    sendBeaconMock.mockReturnValue(true);

    track("page_view", { page_path: "/inventory/products" });
    await flushTelemetry("hidden");

    expect(sendBeaconMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).not.toHaveBeenCalled();
    const body = sendBeaconMock.mock.calls[0][1] as Blob;
    expect(body.type).toBe("application/json");
  });

  it("falls back to a keepalive send when Beacon is refused", async () => {
    sendBeaconMock.mockReturnValue(false);
    fetchMock.mockResolvedValueOnce(jsonResponse(200));

    track("page_view", { page_path: "/inventory/products" });
    await flushTelemetry("hidden");

    expect(sendBeaconMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.keepalive).toBe(true);
  });

  it("does not duplicate an already-flushed lifecycle batch", async () => {
    sendBeaconMock.mockReturnValue(true);

    track("page_view", { page_path: "/inventory/products" });
    await flushTelemetry("hidden");
    await flushTelemetry("hidden");

    expect(sendBeaconMock).toHaveBeenCalledTimes(1);
  });
});

describe("non-browser environments", () => {
  it("does not queue events without a window", () => {
    delete (globalThis as unknown as { window?: unknown }).window;

    track("page_view", { page_path: "/inventory/products" });

    expect(pendingTelemetryCount()).toBe(0);
  });
});
