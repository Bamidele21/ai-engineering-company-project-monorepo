"use client";
/* eslint-disable react-hooks/set-state-in-effect */

import { useCallback, useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import { BackofficeShell } from "@/components/backoffice/BackofficeShell";
import { authorizedFetch } from "@/lib/auth/client";
import { parseApiError } from "@/lib/api/errors";
import {
  CATEGORY_OPTIONS,
  SUPPLIERS_API_URL,
  isRenewalWithin60Days,
  type SupplierCategory,
  type SupplierCountry,
  type SupplierRecord,
} from "@/lib/suppliers";

const SupplierRegistrationForm = dynamic(
  () => import("@/components/suppliers/SupplierRegistrationForm"),
  {
    loading: () => (
      <p className="supplier-success" role="status">
        Loading the supplier registration form...
      </p>
    ),
  }
);

const moneyFormatter = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export default function SuppliersPage() {
  const [suppliers, setSuppliers] = useState<SupplierRecord[]>([]);
  const [countryFilter, setCountryFilter] = useState<"" | SupplierCountry>("");
  const [categoryFilter, setCategoryFilter] = useState<"" | SupplierCategory>("");
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  const [rateDrafts, setRateDrafts] = useState<Record<number, string>>({});
  const [rowBusy, setRowBusy] = useState<Record<number, boolean>>({});

  const renewalSoonById = useMemo(() => {
    const map: Record<number, boolean> = {};
    for (const supplier of suppliers) {
      map[supplier.id] = isRenewalWithin60Days(supplier.contract_renewal_date);
    }
    return map;
  }, [suppliers]);

  const loadSuppliers = useCallback(async () => {
    setIsLoading(true);
    setLoadError("");

    try {
      const params = new URLSearchParams();
      if (countryFilter) {
        params.set("country", countryFilter);
      }
      if (categoryFilter) {
        params.set("category", categoryFilter);
      }

      const query = params.toString();
      const response = await authorizedFetch(
        `${SUPPLIERS_API_URL}/suppliers${query ? `?${query}` : ""}`,
        { cache: "no-store" }
      );
      const payload = (await response.json().catch(() => null)) as unknown;

      if (!response.ok) {
        throw new Error(
          parseApiError(payload, "Unable to load suppliers from the API.")
        );
      }

      const rows = (payload as SupplierRecord[]) ?? [];
      setSuppliers(rows);
      setRateDrafts(
        Object.fromEntries(
          rows.map((supplier) => [supplier.id, supplier.monthly_rate.toString()])
        )
      );
    } catch (error) {
      setLoadError(
        error instanceof Error
          ? error.message
          : "Unable to load suppliers from the API."
      );
    } finally {
      setIsLoading(false);
    }
  }, [countryFilter, categoryFilter]);

  // Initial and filter-driven API sync for the supplier list.
  useEffect(() => {
    void loadSuppliers();
  }, [loadSuppliers]);

  const updateRate = async (supplier: SupplierRecord) => {
    const rateValue = rateDrafts[supplier.id] ?? supplier.monthly_rate.toString();
    const parsedRate = Number(rateValue);

    if (!Number.isFinite(parsedRate) || parsedRate <= 0) {
      setLoadError("Monthly rate must be a number greater than zero.");
      return;
    }

    setRowBusy((current) => ({ ...current, [supplier.id]: true }));
    setLoadError("");

    try {
      const response = await authorizedFetch(
        `${SUPPLIERS_API_URL}/suppliers/${supplier.id}/rate`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ monthly_rate: parsedRate }),
        }
      );
      const payload = (await response.json().catch(() => null)) as unknown;

      if (!response.ok) {
        throw new Error(
          parseApiError(payload, "Unable to update monthly rate for supplier.")
        );
      }

      const updated = payload as SupplierRecord;
      setSuppliers((current) =>
        current.map((item) => (item.id === updated.id ? updated : item))
      );
      setRateDrafts((current) => ({
        ...current,
        [supplier.id]: updated.monthly_rate.toString(),
      }));
    } catch (error) {
      setLoadError(
        error instanceof Error
          ? error.message
          : "Unable to update monthly rate for supplier."
      );
    } finally {
      setRowBusy((current) => ({ ...current, [supplier.id]: false }));
    }
  };

  const toggleStatus = async (supplier: SupplierRecord) => {
    const nextStatus: SupplierRecord["status"] =
      supplier.status === "active" ? "suspended" : "active";

    setRowBusy((current) => ({ ...current, [supplier.id]: true }));
    setLoadError("");

    try {
      const response = await authorizedFetch(
        `${SUPPLIERS_API_URL}/suppliers/${supplier.id}/status`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status: nextStatus }),
        }
      );
      const payload = (await response.json().catch(() => null)) as unknown;

      if (!response.ok) {
        throw new Error(
          parseApiError(payload, "Unable to update supplier status.")
        );
      }

      const updated = payload as SupplierRecord;
      setSuppliers((current) =>
        current.map((item) => (item.id === updated.id ? updated : item))
      );
    } catch (error) {
      setLoadError(
        error instanceof Error ? error.message : "Unable to update supplier status."
      );
    } finally {
      setRowBusy((current) => ({ ...current, [supplier.id]: false }));
    }
  };

  return (
    <BackofficeShell
      eyebrow="Human resources operations / Nexova"
      title="Supplier directory"
      initials="PS"
      connectedLabel="Supplier API connected locally"
      pageClassName="supplier-page"
    >
        <section className="supplier-hero" id="list">
            <div>
              <p>01 / Directory</p>
              <h2>Single source of truth for recurrent supplier contracts.</h2>
              <span>
                Review all suppliers, filter by country and category, and update
                monthly rates.
              </span>
            </div>
            <b>
              NEX
              <br />
              VENDOR
            </b>
          </section>

          <section className="supplier-filters" aria-label="Supplier filters">
            <div>
              <label htmlFor="country-filter">Country</label>
              <select
                id="country-filter"
                value={countryFilter}
                onChange={(event) =>
                  setCountryFilter(event.target.value as "" | SupplierCountry)
                }
              >
                <option value="">All countries</option>
                <option value="Spain">Spain</option>
                <option value="USA">USA</option>
              </select>
            </div>

            <div>
              <label htmlFor="category-filter">Category</label>
              <select
                id="category-filter"
                value={categoryFilter}
                onChange={(event) =>
                  setCategoryFilter(event.target.value as "" | SupplierCategory)
                }
              >
                <option value="">All categories</option>
                {CATEGORY_OPTIONS.map((category) => (
                  <option key={category.value} value={category.value}>
                    {category.label}
                  </option>
                ))}
              </select>
            </div>

            <button
              type="button"
              onClick={() => {
                setCountryFilter("");
                setCategoryFilter("");
              }}
            >
              Reset filters
            </button>
          </section>

          {loadError ? (
            <p className="supplier-error" role="alert">
              {loadError}{" "}
              <button type="button" onClick={() => void loadSuppliers()}>
                Try again
              </button>
            </p>
          ) : null}

          <section className="supplier-table-wrapper">
            <table className="supplier-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Country</th>
                  <th>Categories</th>
                  <th>Monthly rate</th>
                  <th>Status</th>
                  <th>Renewal</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr>
                    <td colSpan={7}>Loading suppliers from API...</td>
                  </tr>
                ) : suppliers.length === 0 ? (
                  <tr>
                    <td colSpan={7}>No suppliers match the current filters.</td>
                  </tr>
                ) : (
                  suppliers.map((supplier) => {
                    const isBusy = Boolean(rowBusy[supplier.id]);
                    const renewalSoon = renewalSoonById[supplier.id] ?? false;

                    return (
                      <tr key={supplier.id}>
                        <td>
                          <strong>{supplier.name}</strong>
                          <small>
                            {supplier.contact_email ?? "No contact email"}
                          </small>
                        </td>
                        <td>{supplier.country}</td>
                        <td>{supplier.categories.join(", ")}</td>
                        <td>
                          <div className="rate-control">
                            <input
                              type="number"
                              min="0"
                              step="0.01"
                              value={
                                rateDrafts[supplier.id] ??
                                supplier.monthly_rate.toString()
                              }
                              onChange={(event) =>
                                setRateDrafts((current) => ({
                                  ...current,
                                  [supplier.id]: event.target.value,
                                }))
                              }
                              aria-label={`Monthly rate for ${supplier.name}`}
                            />
                            <span>
                              {supplier.currency} {moneyFormatter.format(supplier.monthly_rate)}
                            </span>
                          </div>
                        </td>
                        <td>
                          <span
                            className={`supplier-status supplier-status-${supplier.status}`}
                          >
                            {supplier.status}
                          </span>
                        </td>
                        <td>
                          <span
                            className={`renewal-pill ${
                              renewalSoon ? "renewal-pill-soon" : ""
                            }`}
                          >
                            {supplier.contract_renewal_date ?? "-"}
                          </span>
                        </td>
                        <td>
                          <div className="row-actions">
                            <button
                              type="button"
                              onClick={() => void updateRate(supplier)}
                              disabled={isBusy}
                            >
                              Save rate
                            </button>
                            <button
                              type="button"
                              onClick={() => void toggleStatus(supplier)}
                              disabled={isBusy}
                            >
                              {supplier.status === "active"
                                ? "Suspend"
                                : "Activate"}
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </section>

          <SupplierRegistrationForm onCreated={() => void loadSuppliers()} />
    </BackofficeShell>
  );
}
