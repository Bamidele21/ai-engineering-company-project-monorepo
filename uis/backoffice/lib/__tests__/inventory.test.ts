import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  jest,
} from "@jest/globals";
import {
  INVENTORY_API_URL,
  createInboundOrder,
  createOutboundOrder,
  listAssets,
  parseApiError,
  stockLevel,
} from "../inventory";

const fetchMock = jest.fn();

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response;
}

beforeEach(() => {
  global.fetch = fetchMock as unknown as typeof fetch;
});

afterEach(() => {
  fetchMock.mockReset();
});

describe("stockLevel", () => {
  it("classifies 10 units or more as healthy", () => {
    expect(stockLevel(10)).toBe("healthy");
    expect(stockLevel(38)).toBe("healthy");
  });

  it("classifies 1-9 units as low and 0 as out", () => {
    expect(stockLevel(9)).toBe("low");
    expect(stockLevel(1)).toBe("low");
    expect(stockLevel(0)).toBe("out");
  });

  it("treats negative stock defensively as out", () => {
    expect(stockLevel(-3)).toBe("out");
  });
});

describe("parseApiError", () => {
  it("returns a string detail verbatim", () => {
    expect(parseApiError({ detail: "Insufficient stock" }, "fallback")).toBe(
      "Insufficient stock"
    );
  });

  it("joins an array of validation messages", () => {
    expect(
      parseApiError(
        { detail: [{ msg: "field required" }, { msg: "bad value" }] },
        "fallback"
      )
    ).toBe("field required. bad value");
  });

  it("falls back for null, empty, and non-object payloads", () => {
    expect(parseApiError(null, "fallback")).toBe("fallback");
    expect(parseApiError({}, "fallback")).toBe("fallback");
    expect(parseApiError("oops", "fallback")).toBe("fallback");
  });
});

describe("listAssets", () => {
  it("returns the asset array from the API", async () => {
    const assets = [
      {
        id: 1,
        name: "Laptop 14\" Business",
        sku: "NXV-IT-001",
        category: "hardware",
        office: "Valencia",
        current_stock: 12,
      },
    ];
    fetchMock.mockResolvedValueOnce(jsonResponse(200, assets));

    await expect(listAssets()).resolves.toEqual(assets);
    expect(fetchMock).toHaveBeenCalledWith(
      `${INVENTORY_API_URL}/inventory/products`,
      expect.any(Object)
    );
  });

  it("throws the API detail when the request fails", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(500, { detail: "Inventory is unavailable." })
    );

    await expect(listAssets()).rejects.toThrow("Inventory is unavailable.");
  });
});

describe("createInboundOrder", () => {
  it("posts the entry payload and returns the created record", async () => {
    const created = {
      id: 5,
      asset_id: 1,
      quantity: 10,
      supplier: "TechDistrib Valencia S.L.",
      office: "Valencia",
      created_at: "2026-10-08T09:00:00Z",
      user_uuid: "uuid-1",
    };
    fetchMock.mockResolvedValueOnce(jsonResponse(201, created));

    const result = await createInboundOrder({
      asset_id: 1,
      quantity: 10,
      supplier: "TechDistrib Valencia S.L.",
      office: "Valencia",
    });

    expect(result).toEqual(created);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${INVENTORY_API_URL}/inventory/orders/inbound`);
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({
      asset_id: 1,
      quantity: 10,
      supplier: "TechDistrib Valencia S.L.",
      office: "Valencia",
    });
  });
});

describe("createOutboundOrder", () => {
  it("posts the allocation payload and returns the created exit", async () => {
    const created = {
      id: 7,
      asset_id: 3,
      quantity: 2,
      exit_type: "allocation",
      assigned_to: "Ana Torres",
      office: "Valencia",
      created_at: "2026-10-08T10:00:00Z",
      user_uuid: "uuid-2",
    };
    fetchMock.mockResolvedValueOnce(jsonResponse(201, created));

    const result = await createOutboundOrder({
      asset_id: 3,
      quantity: 2,
      exit_type: "allocation",
      assigned_to: "Ana Torres",
      office: "Valencia",
    });

    expect(result).toEqual(created);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${INVENTORY_API_URL}/inventory/orders/outbound`);
    expect(JSON.parse(init.body as string)).toEqual({
      asset_id: 3,
      quantity: 2,
      exit_type: "allocation",
      assigned_to: "Ana Torres",
      office: "Valencia",
    });
  });

  it("surfaces the 400 insufficient-stock message", async () => {
    const detail =
      "Insufficient stock for asset 'Laptop'. Available: 1, requested: 5.";
    fetchMock.mockResolvedValueOnce(jsonResponse(400, { detail }));

    await expect(
      createOutboundOrder({
        asset_id: 1,
        quantity: 5,
        exit_type: "consumption",
        assigned_to: null,
        office: "Miami",
      })
    ).rejects.toThrow(detail);
  });
});
