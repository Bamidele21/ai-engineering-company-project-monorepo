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
  resetTelemetryForTests,
} from "../telemetry/telemetry";
import { trackValidationFailure } from "../telemetry/validation";

const fetchMock = jest.fn();

function jsonResponse(status: number): Response {
  return { ok: status >= 200 && status < 300, status } as Response;
}

function setupBrowser(): void {
  (globalThis as unknown as { window: unknown }).window = {
    location: { pathname: "/inventory/orders/inbound" },
    addEventListener: jest.fn(),
    removeEventListener: jest.fn(),
    localStorage: {
      getItem: () => null,
      setItem: () => undefined,
      removeItem: () => undefined,
    },
  };
}

function validationEvents(): Array<Record<string, unknown>> {
  const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
  return JSON.parse(init.body as string).events;
}

beforeEach(() => {
  resetTelemetryForTests();
  process.env.NEXT_PUBLIC_TELEMETRY_ENDPOINT =
    "http://localhost:8001/telemetry/events";
  fetchMock.mockReset();
  fetchMock.mockResolvedValue(jsonResponse(200));
  global.fetch = fetchMock as unknown as typeof fetch;
  setupBrowser();
});

afterEach(() => {
  resetTelemetryForTests();
  delete (globalThis as unknown as { window?: unknown }).window;
});

describe("trackValidationFailure", () => {
  it("emits only field names and rule codes", async () => {
    trackValidationFailure(
      "inbound_order_form",
      "quantity",
      "quantity_gt_0",
      "/inventory/orders/inbound?asset_id=4"
    );
    await flushTelemetry("manual");

    const event = validationEvents()[0];
    expect(event.event_type).toBe("validation_failed");
    expect(event.properties).toEqual({
      source: "client",
      context: "inbound_order_form",
      field: "quantity",
      reason: "quantity_gt_0",
      page_path: "/inventory/orders/inbound",
    });
  });

  it("throttles the same context and reason for one minute", async () => {
    trackValidationFailure("outbound_order_form", "quantity", "quantity_gt_0", "/x");
    trackValidationFailure("outbound_order_form", "quantity", "quantity_gt_0", "/x");
    await flushTelemetry("manual");

    expect(validationEvents()).toHaveLength(1);
  });

  it("allows a different reason in the same context", async () => {
    trackValidationFailure("outbound_order_form", "quantity", "quantity_gt_0", "/x");
    trackValidationFailure("outbound_order_form", "assigned_to", "assigned_to_required", "/x");
    await flushTelemetry("manual");

    expect(validationEvents()).toHaveLength(2);
  });
});
