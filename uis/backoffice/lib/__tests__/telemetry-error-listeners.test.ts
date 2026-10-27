import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  jest,
} from "@jest/globals";
import {
  resetErrorListenersForTests,
  trackFrontendError,
} from "../telemetry/error-listeners";
import {
  flushTelemetry,
  resetTelemetryForTests,
} from "../telemetry/telemetry";

const fetchMock = jest.fn();

function jsonResponse(status: number): Response {
  return { ok: status >= 200 && status < 300, status } as Response;
}

function setupBrowser(): void {
  (globalThis as unknown as { window: unknown }).window = {
    location: { pathname: "/inventory/products" },
    addEventListener: jest.fn(),
    removeEventListener: jest.fn(),
    localStorage: {
      getItem: () => null,
      setItem: () => undefined,
      removeItem: () => undefined,
    },
  };
}

function errorEvents(): Array<Record<string, unknown>> {
  const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
  return JSON.parse(init.body as string).events;
}

beforeEach(() => {
  resetTelemetryForTests();
  resetErrorListenersForTests();
  process.env.NEXT_PUBLIC_TELEMETRY_ENDPOINT =
    "http://localhost:8001/telemetry/events";
  fetchMock.mockReset();
  fetchMock.mockResolvedValue(jsonResponse(200));
  global.fetch = fetchMock as unknown as typeof fetch;
  setupBrowser();
});

afterEach(() => {
  resetTelemetryForTests();
  resetErrorListenersForTests();
  delete (globalThis as unknown as { window?: unknown }).window;
});

describe("trackFrontendError", () => {
  it("captures a sanitised error with its page and source", async () => {
    trackFrontendError(
      new TypeError("Failed for elena@nexova.com at https://x.test/path"),
      "window_onerror",
      "/inventory/products?token=secret"
    );
    await flushTelemetry("manual");

    const event = errorEvents()[0];
    expect(event.event_type).toBe("frontend_error_captured");
    expect(event.properties).toMatchObject({
      error_type: "TypeError",
      message: "Failed for [email] at [url]",
      page_path: "/inventory/products",
      source: "window_onerror",
    });
  });

  it("suppresses an identical error for five minutes", async () => {
    const error = new Error("boom");
    trackFrontendError(error, "window_onerror", "/inventory");
    trackFrontendError(error, "window_onerror", "/inventory");
    await flushTelemetry("manual");

    expect(errorEvents()).toHaveLength(1);
  });

  it("caps distinct errors at ten per minute", async () => {
    for (let index = 0; index < 12; index += 1) {
      trackFrontendError(
        new Error(`boom-${index}`),
        "unhandledrejection",
        "/inventory"
      );
    }
    await flushTelemetry("manual");

    expect(errorEvents()).toHaveLength(10);
  });
});
