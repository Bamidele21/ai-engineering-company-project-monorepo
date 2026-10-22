"use client";
/* eslint-disable react-hooks/set-state-in-effect */

import { FormEvent, Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { BackofficeShell } from "@/components/backoffice/BackofficeShell";
import {
  CURRENCY_BY_OFFICE,
  createInboundOrder,
  listAssets,
  type Asset,
  type Office,
} from "@/lib/inventory";
import { trackValidationFailure } from "@/lib/telemetry/validation";

interface InboundFormState {
  asset_id: string;
  quantity: string;
  supplier: string;
  unit_cost: string;
  office: Office;
}

const INITIAL_FORM: InboundFormState = {
  asset_id: "",
  quantity: "",
  supplier: "",
  unit_cost: "",
  office: "Valencia",
};

function InboundOrderForm() {
  const searchParams = useSearchParams();
  const preselectedAsset = searchParams.get("asset_id") ?? "";

  const [assets, setAssets] = useState<Asset[]>([]);
  const [isLoadingAssets, setIsLoadingAssets] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [form, setForm] = useState<InboundFormState>(INITIAL_FORM);
  const [formError, setFormError] = useState("");
  const [formSuccess, setFormSuccess] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const loadAssets = useCallback(async () => {
    setIsLoadingAssets(true);
    setLoadError("");

    try {
      const loaded = await listAssets();
      setAssets(loaded);
      setForm((current) => {
        if (current.asset_id) {
          return current;
        }

        const hasPreselected = loaded.some(
          (asset) => asset.id.toString() === preselectedAsset
        );
        return hasPreselected
          ? { ...current, asset_id: preselectedAsset }
          : current;
      });
    } catch (error) {
      setLoadError(
        error instanceof Error
          ? error.message
          : "Unable to load assets from the inventory API."
      );
    } finally {
      setIsLoadingAssets(false);
    }
  }, [preselectedAsset]);

  useEffect(() => {
    void loadAssets();
  }, [loadAssets]);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFormError("");
    setFormSuccess("");

    const currentPath =
      typeof window === "undefined" ? "/" : window.location.pathname;

    const assetId = Number(form.asset_id);
    if (!Number.isInteger(assetId) || assetId <= 0) {
      trackValidationFailure(
        "inbound_order_form",
        "asset_id",
        "asset_required",
        currentPath
      );
      setFormError("Select the asset that was received.");
      return;
    }

    const quantity = Number(form.quantity);
    if (!Number.isInteger(quantity) || quantity <= 0) {
      trackValidationFailure(
        "inbound_order_form",
        "quantity",
        "quantity_gt_0",
        currentPath
      );
      setFormError("Quantity must be a whole number greater than zero.");
      return;
    }

    const unitCost = Number(form.unit_cost);
    if (!Number.isFinite(unitCost) || unitCost <= 0) {
      trackValidationFailure(
        "inbound_order_form",
        "unit_cost",
        "unit_cost_gt_0",
        currentPath
      );
      setFormError("Unit cost must be greater than zero.");
      return;
    }

    if (!form.supplier.trim()) {
      trackValidationFailure(
        "inbound_order_form",
        "supplier",
        "supplier_required",
        currentPath
      );
      setFormError("Supplier is required.");
      return;
    }

    setIsSubmitting(true);

    try {
      await createInboundOrder({
        asset_id: assetId,
        quantity,
        supplier: form.supplier.trim(),
        office: form.office,
        unit_cost: unitCost,
        currency: CURRENCY_BY_OFFICE[form.office],
      });

      setFormSuccess("Inbound order registered successfully.");
      setForm(INITIAL_FORM);
    } catch (error) {
      setFormError(
        error instanceof Error
          ? error.message
          : "The inventory API rejected the inbound order."
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <section className="inventory-card inventory-form-card" id="inbound">
      <header>
        <div>
          <p>01 / Inbound order</p>
          <h2>Register an inbound order</h2>
        </div>
        <small>POST /inventory/orders/inbound</small>
      </header>

      {loadError ? (
        <p className="inventory-error" role="alert">
          {loadError}{" "}
          <button type="button" onClick={() => void loadAssets()}>
            Try again
          </button>
        </p>
      ) : null}

      <form onSubmit={handleSubmit} noValidate>
        <div className="inventory-form-grid">
          <label>
            Asset *
            <select
              value={form.asset_id}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  asset_id: event.target.value,
                }))
              }
              disabled={isLoadingAssets}
              required
            >
              <option value="">
                {isLoadingAssets ? "Loading assets..." : "Select an asset"}
              </option>
              {assets.map((asset) => (
                <option key={asset.id} value={asset.id}>
                  {asset.name} ({asset.sku})
                </option>
              ))}
            </select>
          </label>

          <label>
            Quantity received *
            <input
              type="number"
              min="1"
              step="1"
              value={form.quantity}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  quantity: event.target.value,
                }))
              }
              required
            />
          </label>

          <label>
            Unit cost *
            <input
              type="number"
              min="0.01"
              step="0.01"
              value={form.unit_cost}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  unit_cost: event.target.value,
                }))
              }
              required
            />
          </label>

          <label>
            Supplier *
            <input
              type="text"
              value={form.supplier}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  supplier: event.target.value,
                }))
              }
              placeholder="PrintWorks Valencia S.L."
              required
            />
          </label>

          <label>
            Receiving office *
            <select
              value={form.office}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  office: event.target.value as Office,
                }))
              }
            >
              <option value="Valencia">Valencia</option>
              <option value="Miami">Miami</option>
            </select>
          </label>
        </div>

        <p className="inventory-stock-hint">
          Currency: <strong>{CURRENCY_BY_OFFICE[form.office]}</strong> — amounts
          stay in the receiving office&apos;s local currency.
        </p>

        {formError ? (
          <p className="inventory-error" role="alert">
            {formError}
          </p>
        ) : null}
        {formSuccess ? (
          <p className="inventory-success" role="status">
            {formSuccess}
          </p>
        ) : null}

        <div className="inventory-form-actions">
          <button type="submit" disabled={isSubmitting || isLoadingAssets}>
            {isSubmitting ? "Registering..." : "Register inbound order"}
          </button>
        </div>
      </form>
    </section>
  );
}

export default function InventoryInboundPage() {
  return (
    <BackofficeShell
      eyebrow="IT and operations / Nexova"
      title="Register inbound order"
      initials="IN"
      connectedLabel="Inventory API connected locally"
    >
      <section className="inventory-hero">
        <div>
          <p>Inbound / Delivery</p>
          <h2>Log a purchase or supplier delivery into Nexova stock.</h2>
          <span>
            An inbound order records units received. Stock increases by exactly
            what you register here.
          </span>
        </div>
        <b>
          NEX
          <br />
          ENTRY
        </b>
      </section>

      <Suspense
        fallback={
          <p className="inventory-stock-hint">Loading the inbound order form...</p>
        }
      >
        <InboundOrderForm />
      </Suspense>
    </BackofficeShell>
  );
}
