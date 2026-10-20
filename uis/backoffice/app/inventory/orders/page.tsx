"use client";
/* eslint-disable react-hooks/set-state-in-effect */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { BackofficeShell } from "@/components/backoffice/BackofficeShell";
import { listOrders, type Order } from "@/lib/inventory";

const dateFormatter = new Intl.DateTimeFormat("en-GB", {
  dateStyle: "medium",
  timeStyle: "short",
});

function formatDate(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : dateFormatter.format(parsed);
}

function orderDetail(order: Order): string {
  if (order.kind === "inbound") {
    return order.supplier ? `Supplier: ${order.supplier}` : "Inbound delivery";
  }

  if (order.exit_type === "allocation") {
    return order.assigned_to
      ? `Allocation to ${order.assigned_to}`
      : "Allocation";
  }

  return "Consumption";
}

export default function InventoryOrdersPage() {
  const [orders, setOrders] = useState<Order[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  const loadOrders = useCallback(async () => {
    setIsLoading(true);
    setLoadError("");

    try {
      setOrders(await listOrders());
    } catch (error) {
      setLoadError(
        error instanceof Error
          ? error.message
          : "Unable to load orders from the inventory API."
      );
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadOrders();
  }, [loadOrders]);

  return (
    <BackofficeShell
      eyebrow="IT and operations / Nexova"
      title="Inventory order history"
      initials="IN"
      connectedLabel="Inventory API connected locally"
    >
      <section className="inventory-hero">
        <div>
          <p>02 / Order history</p>
          <h2>Every inbound and outbound order, in one read-only ledger.</h2>
          <span>
            Each row records the asset, quantity, office, date, and the IT
            manager who registered it.
          </span>
        </div>
        <b>
          NEX
          <br />
          LEDGER
        </b>
      </section>

      <section className="inventory-toolbar" aria-label="Inventory actions">
        <Link href="/inventory/orders/inbound">Register inbound order</Link>
        <Link href="/inventory/orders/outbound">Register outbound order</Link>
        <Link className="secondary" href="/inventory/products">
          View assets
        </Link>
      </section>

      {loadError ? (
        <p className="inventory-error" role="alert">
          {loadError}{" "}
          <button type="button" onClick={() => void loadOrders()}>
            Try again
          </button>
        </p>
      ) : null}

      <section className="inventory-table-wrapper">
        <table className="inventory-table">
          <thead>
            <tr>
              <th>Asset</th>
              <th>Type</th>
              <th>Quantity</th>
              <th>Detail</th>
              <th>Office</th>
              <th>Date</th>
              <th>Created by</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={7}>Loading orders from the inventory API...</td>
              </tr>
            ) : orders.length === 0 ? (
              <tr>
                <td colSpan={7}>No inbound or outbound orders have been recorded.</td>
              </tr>
            ) : (
              orders.map((order) => (
                <tr key={`${order.kind}-${order.id}`}>
                  <td>
                    <strong>{order.asset_name || "Unknown asset"}</strong>
                    <small>{order.asset_sku}</small>
                  </td>
                  <td>
                    <span
                      className={`inventory-kind inventory-kind-${order.kind}`}
                    >
                      {order.kind === "inbound" ? "Inbound order" : "Outbound order"}
                    </span>
                  </td>
                  <td>{order.quantity}</td>
                  <td>{orderDetail(order)}</td>
                  <td>{order.office}</td>
                  <td>{formatDate(order.created_at)}</td>
                  <td>
                    <small>{order.user_uuid}</small>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </section>
    </BackofficeShell>
  );
}
