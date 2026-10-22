import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  jest,
} from "@jest/globals";

jest.mock("../auth/storage", () => ({
  getToken: jest.fn(),
  clearToken: jest.fn(),
}));

import { getToken } from "../auth/storage";
import { authorizedFetch } from "../auth/client";
import {
  flushTelemetry,
  resetTelemetryForTests,
} from "../telemetry/telemetry";

const getTokenMock = getToken as jest.MockedFunction<typeof getToken>;
const fetchMock = jest.fn();
const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function jsonResponse(status: number): Response {
  return { ok: status >= 200 && status < 300, status } as Response;
}

function setupBrowser(): void {
  (globalThis as unknown as { window: unknown }).window = {
    location: {
      pathname: "/inventory/products",
      search: "",
      assign: jest.fn(),
    },
    addEventListener: jest.fn(),
    removeEventListener: jest.fn(),
  };
}

function telemetryBatch(callIndex: number): Array<Record<string, unknown>> {
  const [, init] = fetchMock.mock.calls[callIndex] as [string, RequestInit];
  return JSON.parse(init.body as string).events;
}

beforeEach(() => {
  resetTelemetryForTests();
  process.env.NEXT_PUBLIC_TELEMETRY_ENDPOINT =
    "http://localhost:8001/telemetry/events";
  getTokenMock.mockReset();
  getTokenMock.mockReturnValue(null);
  fetchMock.mockReset();
  global.fetch = fetchMock as unknown as typeof fetch;
  setupBrowser();
});

afterEach(() => {
  resetTelemetryForTests();
  delete (globalThis as unknown as { window?: unknown }).window;
});

describe("authorizedFetch telemetry correlation", () => {
  it("adds request and session headers to API calls", async () => {
    getTokenMock.mockReturnValue("token-123");
    fetchMock.mockResolvedValueOnce(jsonResponse(200));

    await authorizedFetch("http://localhost:8001/inventory/products");

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Headers;
    expect(headers.get("X-Request-Id")).toMatch(UUID_PATTERN);
    expect(headers.get("X-Session-Id")).toMatch(UUID_PATTERN);
    expect(headers.get("Authorization")).toBe("Bearer token-123");
  });

  it("captures a network failure with the failed request id", async () => {
    fetchMock
      .mockRejectedValueOnce(new Error("connection refused"))
      .mockResolvedValueOnce(jsonResponse(200));

    await expect(
      authorizedFetch("http://localhost:8001/inventory/orders?asset_id=4")
    ).rejects.toThrow("Network error");

    await flushTelemetry("manual");
    const event = telemetryBatch(1)[0];
    expect(event.event_type).toBe("network_request_failed");
    expect(event.properties).toEqual({
      target: "inventory-api:/inventory/orders",
      page_path: "/inventory/products",
    });
  });

  it("throttles the same target and page for one minute", async () => {
    fetchMock
      .mockRejectedValueOnce(new Error("connection refused"))
      .mockRejectedValueOnce(new Error("connection refused"))
      .mockResolvedValueOnce(jsonResponse(200));

    await expect(
      authorizedFetch("http://localhost:8001/inventory/orders")
    ).rejects.toThrow("Network error");
    await expect(
      authorizedFetch("http://localhost:8001/inventory/orders")
    ).rejects.toThrow("Network error");

    await flushTelemetry("manual");
    expect(telemetryBatch(2)).toHaveLength(1);
  });
});
