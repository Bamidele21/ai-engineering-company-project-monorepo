"use client";
/* eslint-disable react-hooks/set-state-in-effect */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { BackofficeShell } from "@/components/backoffice/BackofficeShell";
import {
  CATEGORY_LABELS,
  STOCK_LEVEL_LABELS,
  listAssets,
  stockLevel,
  type Asset,
} from "@/lib/inventory";

export default function InventoryProductsPage() {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  const loadAssets = useCallback(async () => {
    setIsLoading(true);
    setLoadError("");

    try {
      setAssets(await listAssets());
    } catch (error) {
      setLoadError(
        error instanceof Error
          ? error.message
          : "Unable to load assets from the inventory API."
      );
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadAssets();
  }, [loadAssets]);

  return (
    <BackofficeShell
      eyebrow="IT and operations / Nexova"
      title="Inventory assets"
      initials="IN"
      connectedLabel="Inventory API connected locally"
    >
      <section className="inventory-hero">
        <div>
          <p>01 / Stock</p>
          <h2>Every Nexova asset and its live stock position.</h2>
          <span>
            Stock is always the net result of inbound orders minus outbound
            orders — it can never be set directly.
          </span>
        </div>
        <b>
          NEX
          <br />
          STOCK
        </b>
      </section>

      <section className="inventory-toolbar" aria-label="Inventory actions">
        <Link href="/inventory/orders/inbound">Register inbound order</Link>
        <Link href="/inventory/orders/outbound">Register outbound order</Link>
        <Link className="secondary" href="/inventory/orders">
          View order history
        </Link>
      </section>

      {loadError ? (
        <p className="inventory-error" role="alert">
          {loadError}{" "}
          <button type="button" onClick={() => void loadAssets()}>
            Try again
          </button>
        </p>
      ) : null}

      <section className="inventory-table-wrapper">
        <table className="inventory-table">
          <thead>
            <tr>
              <th>Asset</th>
              <th>SKU</th>
              <th>Category</th>
              <th>Office</th>
              <th>Current stock</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={6}>Loading assets from the inventory API...</td>
              </tr>
            ) : assets.length === 0 ? (
              <tr>
                <td colSpan={6}>No assets have been registered yet.</td>
              </tr>
            ) : (
              assets.map((asset) => {
                const level = stockLevel(asset.current_stock);

                return (
                  <tr key={asset.id}>
                    <td>
                      <strong>{asset.name}</strong>
                    </td>
                    <td>{asset.sku}</td>
                    <td>{CATEGORY_LABELS[asset.category] ?? asset.category}</td>
                    <td>{asset.office}</td>
                    <td>
                      <span className={`inventory-stock inventory-stock-${level}`}>
                        {STOCK_LEVEL_LABELS[level]} · {asset.current_stock}
                      </span>
                    </td>
                    <td>
                      <div className="inventory-row-actions">
                        <Link
                          href={`/inventory/orders/inbound?asset_id=${asset.id}`}
                        >
                          New inbound order
                        </Link>
                        <Link
                          href={`/inventory/orders/outbound?asset_id=${asset.id}`}
                        >
                          New outbound order
                        </Link>
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </section>
    </BackofficeShell>
  );
}
