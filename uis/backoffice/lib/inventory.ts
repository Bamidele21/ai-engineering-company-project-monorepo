import { parseApiError } from "./api/errors";
import { authorizedFetch } from "./auth/client";

// Base URL of the Nexova Inventory API (a service separate from the auth /
// supplier directory API). Defaults to the local service port.
export const INVENTORY_API_URL =
  process.env.NEXT_PUBLIC_INVENTORY_API_URL ?? "http://localhost:8001";

export type AssetCategory =
  | "training_kit"
  | "certification"
  | "onboarding_equipment";

export type Office = "Valencia" | "Miami";
export type Currency = "EUR" | "USD";

export type ExitType = "allocation" | "consumption";

export const CURRENCY_BY_OFFICE: Record<Office, Currency> = {
  Valencia: "EUR",
  Miami: "USD",
};

export interface Asset {
  id: number;
  name: string;
  sku: string;
  category: AssetCategory;
  office: Office;
  programme_id: number | null;
  min_stock: number;
  current_stock: number;
}

export interface Order {
  id: number;
  kind: "inbound" | "outbound";
  asset_id: number;
  asset_name: string;
  asset_sku: string;
  quantity: number;
  office: Office;
  created_at: string;
  user_uuid: string;
  supplier: string | null;
  unit_cost: number | null;
  currency: Currency | null;
  exit_type: ExitType | null;
  assigned_to: string | null;
}

export interface InboundOrder {
  id: number;
  asset_id: number;
  quantity: number;
  supplier: string;
  office: Office;
  unit_cost: number;
  currency: Currency;
  created_at: string;
  user_uuid: string;
}

export interface OutboundOrder {
  id: number;
  asset_id: number;
  quantity: number;
  exit_type: ExitType;
  assigned_to: string | null;
  office: Office;
  created_at: string;
  user_uuid: string;
}

export interface InboundOrderPayload {
  asset_id: number;
  quantity: number;
  supplier: string;
  office: Office;
  unit_cost: number;
  currency: Currency;
}

export interface OutboundOrderPayload {
  asset_id: number;
  quantity: number;
  exit_type: ExitType;
  assigned_to: string | null;
  office: Office;
}

export const DEFAULT_MIN_STOCK = 10;

export type StockLevel = "out" | "low" | "healthy";

export const CATEGORY_LABELS: Record<AssetCategory, string> = {
  training_kit: "Training kit",
  certification: "Certification",
  onboarding_equipment: "Onboarding equipment",
};

export const STOCK_LEVEL_LABELS: Record<StockLevel, string> = {
  out: "Out of stock",
  low: "Low stock",
  healthy: "In stock",
};

export function stockLevel(
  stock: number,
  minStock: number = DEFAULT_MIN_STOCK
): StockLevel {
  if (stock <= 0) {
    return "out";
  }

  if (stock < minStock) {
    return "low";
  }

  return "healthy";
}

async function readJson(response: Response): Promise<unknown> {
  return response.json().catch(() => null);
}

export async function listAssets(): Promise<Asset[]> {
  const response = await authorizedFetch(`${INVENTORY_API_URL}/inventory/products`);
  const payload = await readJson(response);

  if (!response.ok) {
    throw new Error(
      parseApiError(payload, "Unable to load assets from the inventory API.")
    );
  }

  return Array.isArray(payload) ? (payload as Asset[]) : [];
}

export async function listOrders(): Promise<Order[]> {
  const response = await authorizedFetch(`${INVENTORY_API_URL}/inventory/orders`);
  const payload = await readJson(response);

  if (!response.ok) {
    throw new Error(
      parseApiError(payload, "Unable to load orders from the inventory API.")
    );
  }

  return Array.isArray(payload) ? (payload as Order[]) : [];
}

export async function createInboundOrder(
  payload: InboundOrderPayload
): Promise<InboundOrder> {
  const response = await authorizedFetch(
    `${INVENTORY_API_URL}/inventory/orders/inbound`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
  const body = await readJson(response);

  if (!response.ok) {
    throw new Error(
      parseApiError(body, "The inventory API rejected the inbound order.")
    );
  }

  return body as InboundOrder;
}

export async function createOutboundOrder(
  payload: OutboundOrderPayload
): Promise<OutboundOrder> {
  const response = await authorizedFetch(
    `${INVENTORY_API_URL}/inventory/orders/outbound`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
  const body = await readJson(response);

  if (!response.ok) {
    throw new Error(
      parseApiError(body, "The inventory API rejected the outbound order.")
    );
  }

  return body as OutboundOrder;
}
