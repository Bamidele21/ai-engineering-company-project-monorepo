"use client";
/* eslint-disable react-hooks/set-state-in-effect */

import { FormEvent, Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { BackofficeShell } from "@/components/backoffice/BackofficeShell";
import {
  createOutboundOrder,
  listAssets,
  type Asset,
  type ExitType,
  type Office,
} from "@/lib/inventory";
import { trackValidationFailure } from "@/lib/telemetry/validation";

interface OutboundFormState {
  asset_id: string;
  quantity: string;
  exit_type: ExitType;
  assigned_to: string;
  office: Office;
}

const INITIAL_FORM: OutboundFormState = {
  asset_id: "",
  quantity: "",
  exit_type: "allocation",
  assigned_to: "",
  office: "Valencia",
};

function OutboundOrderForm() {
  const searchParams = useSearchParams();
  const preselectedAsset = searchParams.get("asset_id") ?? "";

  const [assets, setAssets] = useState<Asset[]>([]);
  const [isLoadingAssets, setIsLoadingAssets] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [form, setForm] = useState<OutboundFormState>(INITIAL_FORM);
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

  const selectedAsset =
    assets.find((asset) => asset.id.toString() === form.asset_id) ?? null;
  const availableStock = selectedAsset ? selectedAsset.current_stock : null;
  const requestedQuantity = Number(form.quantity);
  const exceedsStock =
    selectedAsset !== null &&
    Number.isFinite(requestedQuantity) &&
    requestedQuantity > selectedAsset.current_stock;

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFormError("");
    setFormSuccess("");

    const currentPath =
      typeof window === "undefined" ? "/" : window.location.pathname;

    const assetId = Number(form.asset_id);
    if (!Number.isInteger(assetId) || assetId <= 0) {
      trackValidationFailure(
        "outbound_order_form",
        "asset_id",
        "asset_required",
        currentPath
      );
      setFormError("Select the asset for this outbound order.");
      return;
    }

    const quantity = Number(form.quantity);
    if (!Number.isInteger(quantity) || quantity <= 0) {
      trackValidationFailure(
        "outbound_order_form",
        "quantity",
        "quantity_gt_0",
        currentPath
      );
      setFormError("Quantity must be a whole number greater than zero.");
      return;
    }

    if (form.exit_type === "allocation" && !form.assigned_to.trim()) {
      trackValidationFailure(
        "outbound_order_form",
        "assigned_to",
        "assigned_to_required",
        currentPath
      );
      setFormError("Assigned to is required when the exit type is allocation.");
      return;
    }

    setIsSubmitting(true);

    try {
      await createOutboundOrder({
        asset_id: assetId,
        quantity,
        exit_type: form.exit_type,
        assigned_to:
          form.exit_type === "allocation" ? form.assigned_to.trim() : null,
        office: form.office,
      });

      setFormSuccess("Outbound order registered successfully.");
      setForm(INITIAL_FORM);
    } catch (error) {
      setFormError(
        error instanceof Error
          ? error.message
          : "The inventory API rejected the outbound order."
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <section className="inventory-card inventory-form-card" id="outbound">
      <header>
        <div>
          <p>01 / Outbound order</p>
          <h2>Register an outbound order</h2>
        </div>
        <small>POST /inventory/orders/outbound</small>
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

          <p className="inventory-stock-hint">
            {selectedAsset ? (
              <>
                Available stock for <strong>{selectedAsset.name}</strong>:{" "}
                <strong>{availableStock} units</strong>
              </>
            ) : (
              "Select an asset to see how much stock is available."
            )}
          </p>

          <label>
            Quantity allocated / consumed *
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
              aria-invalid={exceedsStock || Boolean(formError)}
              required
            />
            {exceedsStock ? (
              <span className="inventory-warning" role="status">
                Quantity exceeds the {availableStock} units currently available.
                The inventory API will reject this outbound order.
              </span>
            ) : null}
            {formError ? (
              <span className="inventory-error" role="alert">
                {formError}
              </span>
            ) : null}
          </label>

          <label>
            Exit type *
            <select
              value={form.exit_type}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  exit_type: event.target.value as ExitType,
                  assigned_to:
                    event.target.value === "consumption"
                      ? ""
                      : current.assigned_to,
                }))
              }
            >
              <option value="allocation">Allocation (to an employee)</option>
              <option value="consumption">Consumption</option>
            </select>
          </label>

          <label>
            Assigned to {form.exit_type === "allocation" ? "*" : "(consumption)"}
            <input
              type="text"
              value={form.assigned_to}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  assigned_to: event.target.value,
                }))
              }
              placeholder="Employee name or ID"
              disabled={form.exit_type === "consumption"}
              required={form.exit_type === "allocation"}
            />
          </label>

          <label>
            Office *
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

        {formSuccess ? (
          <p className="inventory-success" role="status">
            {formSuccess}
          </p>
        ) : null}

        <div className="inventory-form-actions">
          <button type="submit" disabled={isSubmitting || isLoadingAssets}>
            {isSubmitting ? "Registering..." : "Register outbound order"}
          </button>
        </div>
      </form>
    </section>
  );
}

export default function InventoryOutboundPage() {
  return (
    <BackofficeShell
      eyebrow="IT and operations / Nexova"
      title="Register outbound order"
      initials="IN"
      connectedLabel="Inventory API connected locally"
    >
      <section className="inventory-hero">
        <div>
          <p>Outbound / Allocation or consumption</p>
          <h2>Allocate equipment to a person or log a consumption.</h2>
          <span>
            The current stock for the selected asset is shown before you submit,
            so an outbound order can never exceed what Nexova has.
          </span>
        </div>
        <b>
          NEX
          <br />
          EXIT
        </b>
      </section>

      <Suspense
        fallback={
          <p className="inventory-stock-hint">Loading the outbound order form...</p>
        }
      >
        <OutboundOrderForm />
      </Suspense>
    </BackofficeShell>
  );
}
