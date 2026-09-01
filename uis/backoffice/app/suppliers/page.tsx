"use client";
/* eslint-disable react-hooks/set-state-in-effect */

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

type SupplierCountry = "Spain" | "USA";
type SupplierStatus = "active" | "suspended";
type SupplierCategory =
  | "job_boards"
  | "ats_software"
  | "assessment_tools"
  | "training_platforms"
  | "payroll_and_hr_software"
  | "video_interview"
  | "background_check"
  | "office_and_facilities"
  | "it_and_software_licenses";

type SupplierRecord = {
  id: number;
  name: string;
  country: SupplierCountry;
  categories: SupplierCategory[];
  monthly_rate: number;
  currency: "EUR" | "USD";
  updated_at: string;
  status: SupplierStatus;
  contract_renewal_date: string | null;
  contact_email: string | null;
  notes: string | null;
};

type SupplierCreatePayload = {
  name: string;
  country: SupplierCountry;
  categories: SupplierCategory[];
  monthly_rate: number;
  currency: "EUR" | "USD";
  status: SupplierStatus;
  contract_renewal_date?: string;
  contact_email?: string;
  notes?: string;
};

type ApiError = {
  detail?: string | Array<{ msg?: string }>;
};

const SUPPLIERS_API_URL =
  process.env.NEXT_PUBLIC_SUPPLIERS_API_URL ?? "http://localhost:8000";

const CATEGORY_OPTIONS: Array<{ value: SupplierCategory; label: string }> = [
  { value: "job_boards", label: "Job boards" },
  { value: "ats_software", label: "ATS software" },
  { value: "assessment_tools", label: "Assessment tools" },
  { value: "training_platforms", label: "Training platforms" },
  {
    value: "payroll_and_hr_software",
    label: "Payroll and HR software",
  },
  { value: "video_interview", label: "Video interview" },
  { value: "background_check", label: "Background check" },
  { value: "office_and_facilities", label: "Office and facilities" },
  {
    value: "it_and_software_licenses",
    label: "IT and software licenses",
  },
];

type NewSupplierForm = {
  name: string;
  country: SupplierCountry;
  categories: SupplierCategory[];
  monthly_rate: string;
  status: SupplierStatus;
  contract_renewal_date: string;
  contact_email: string;
  notes: string;
};

const INITIAL_FORM: NewSupplierForm = {
  name: "",
  country: "Spain",
  categories: [],
  monthly_rate: "",
  status: "active",
  contract_renewal_date: "",
  contact_email: "",
  notes: "",
};

function parseApiError(errorPayload: unknown, fallback: string): string {
  if (!errorPayload || typeof errorPayload !== "object") {
    return fallback;
  }

  const payload = errorPayload as ApiError;
  if (typeof payload.detail === "string") {
    return payload.detail;
  }

  if (Array.isArray(payload.detail)) {
    const collected = payload.detail
      .map((entry) => entry.msg)
      .filter((entry): entry is string => Boolean(entry));
    if (collected.length > 0) {
      return collected.join(". ");
    }
  }

  return fallback;
}

function isRenewalWithin60Days(value: string | null): boolean {
  if (!value) {
    return false;
  }

  const renewal = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(renewal.getTime())) {
    return false;
  }

  const now = new Date();
  const today = new Date(
    Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate())
  );
  const diffDays = Math.ceil(
    (renewal.getTime() - today.getTime()) / (1000 * 60 * 60 * 24)
  );

  return diffDays >= 0 && diffDays <= 60;
}

export default function SuppliersPage() {
  const [suppliers, setSuppliers] = useState<SupplierRecord[]>([]);
  const [countryFilter, setCountryFilter] = useState<"" | SupplierCountry>("");
  const [categoryFilter, setCategoryFilter] = useState<"" | SupplierCategory>("");
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  const [newSupplier, setNewSupplier] = useState<NewSupplierForm>(INITIAL_FORM);
  const [formError, setFormError] = useState("");
  const [formSuccess, setFormSuccess] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const [rateDrafts, setRateDrafts] = useState<Record<number, string>>({});
  const [rowBusy, setRowBusy] = useState<Record<number, boolean>>({});

  const moneyFormatter = useMemo(
    () =>
      new Intl.NumberFormat("en-US", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }),
    []
  );

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
      const response = await fetch(
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

  const handleCategoryToggle = (category: SupplierCategory) => {
    setNewSupplier((current) => {
      const exists = current.categories.includes(category);
      const nextCategories = exists
        ? current.categories.filter((value) => value !== category)
        : [...current.categories, category];

      return { ...current, categories: nextCategories };
    });
  };

  const handleCreateSupplier = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFormError("");
    setFormSuccess("");

    if (!newSupplier.name.trim()) {
      setFormError("Supplier name is required.");
      return;
    }

    if (newSupplier.categories.length === 0) {
      setFormError("Select at least one category.");
      return;
    }

    const parsedRate = Number(newSupplier.monthly_rate);
    if (!Number.isFinite(parsedRate) || parsedRate <= 0) {
      setFormError("Monthly rate must be a number greater than zero.");
      return;
    }

    setIsSubmitting(true);

    const payload: SupplierCreatePayload = {
      name: newSupplier.name.trim(),
      country: newSupplier.country,
      categories: newSupplier.categories,
      monthly_rate: parsedRate,
      currency: newSupplier.country === "Spain" ? "EUR" : "USD",
      status: newSupplier.status,
      contract_renewal_date: newSupplier.contract_renewal_date || undefined,
      contact_email: newSupplier.contact_email.trim() || undefined,
      notes: newSupplier.notes.trim() || undefined,
    };

    try {
      const response = await fetch(`${SUPPLIERS_API_URL}/suppliers`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const responsePayload = (await response
        .json()
        .catch(() => null)) as unknown;

      if (!response.ok) {
        throw new Error(
          parseApiError(
            responsePayload,
            "The API rejected the supplier registration request."
          )
        );
      }

      setFormSuccess("Supplier registered successfully.");
      setNewSupplier(INITIAL_FORM);
      await loadSuppliers();
    } catch (error) {
      setFormError(
        error instanceof Error
          ? error.message
          : "The API rejected the supplier registration request."
      );
    } finally {
      setIsSubmitting(false);
    }
  };

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
      const response = await fetch(
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
    const nextStatus: SupplierStatus =
      supplier.status === "active" ? "suspended" : "active";

    setRowBusy((current) => ({ ...current, [supplier.id]: true }));
    setLoadError("");

    try {
      const response = await fetch(
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
    <main className="supplier-page">
      <aside className="supplier-nav">
        <Link className="supplier-brand" href="/">
          <b>N</b>
          <span>
            <strong>Nexova</strong>
            <small>Operations studio</small>
          </span>
        </Link>
        <nav aria-label="Backoffice navigation">
          <Link href="/" className="supplier-nav-link">
            01  Overview
          </Link>
          <Link href="/suppliers" className="supplier-nav-link active">
            02  Supplier directory
          </Link>
          <Link href="/incidents" className="supplier-nav-link">
            03  Incident analyzer
          </Link>
        </nav>
        <small className="supplier-connected">● Supplier API connected locally</small>
      </aside>

      <section className="supplier-main">
        <header className="supplier-header">
          <div>
            <p>Human resources operations / Nexova</p>
            <h1>Supplier directory</h1>
          </div>
          <span>PS</span>
        </header>

        <div className="supplier-content">
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
              {loadError}
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
                    const renewalSoon = isRenewalWithin60Days(
                      supplier.contract_renewal_date
                    );

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

          <section className="supplier-form-card" id="new-supplier">
            <header>
              <div>
                <p>02 / Registration</p>
                <h2>Register new supplier</h2>
              </div>
              <small>POST /suppliers</small>
            </header>

            <form onSubmit={handleCreateSupplier} noValidate>
              <div className="supplier-form-grid">
                <label>
                  Supplier name *
                  <input
                    type="text"
                    value={newSupplier.name}
                    onChange={(event) =>
                      setNewSupplier((current) => ({
                        ...current,
                        name: event.target.value,
                      }))
                    }
                    required
                  />
                </label>

                <label>
                  Country *
                  <select
                    value={newSupplier.country}
                    onChange={(event) =>
                      setNewSupplier((current) => ({
                        ...current,
                        country: event.target.value as SupplierCountry,
                      }))
                    }
                  >
                    <option value="Spain">Spain</option>
                    <option value="USA">USA</option>
                  </select>
                </label>

                <label>
                  Currency
                  <input
                    type="text"
                    value={newSupplier.country === "Spain" ? "EUR" : "USD"}
                    readOnly
                  />
                </label>

                <label>
                  Monthly rate *
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    value={newSupplier.monthly_rate}
                    onChange={(event) =>
                      setNewSupplier((current) => ({
                        ...current,
                        monthly_rate: event.target.value,
                      }))
                    }
                    required
                  />
                </label>

                <label>
                  Status *
                  <select
                    value={newSupplier.status}
                    onChange={(event) =>
                      setNewSupplier((current) => ({
                        ...current,
                        status: event.target.value as SupplierStatus,
                      }))
                    }
                  >
                    <option value="active">active</option>
                    <option value="suspended">suspended</option>
                  </select>
                </label>

                <label>
                  Contract renewal date
                  <input
                    type="date"
                    value={newSupplier.contract_renewal_date}
                    onChange={(event) =>
                      setNewSupplier((current) => ({
                        ...current,
                        contract_renewal_date: event.target.value,
                      }))
                    }
                  />
                </label>

                <label>
                  Contact email
                  <input
                    type="email"
                    value={newSupplier.contact_email}
                    onChange={(event) =>
                      setNewSupplier((current) => ({
                        ...current,
                        contact_email: event.target.value,
                      }))
                    }
                  />
                </label>

                <label>
                  Notes
                  <input
                    type="text"
                    value={newSupplier.notes}
                    onChange={(event) =>
                      setNewSupplier((current) => ({
                        ...current,
                        notes: event.target.value,
                      }))
                    }
                  />
                </label>
              </div>

              <fieldset className="category-group">
                <legend>Categories *</legend>
                <div>
                  {CATEGORY_OPTIONS.map((category) => (
                    <label key={category.value}>
                      <input
                        type="checkbox"
                        checked={newSupplier.categories.includes(category.value)}
                        onChange={() => handleCategoryToggle(category.value)}
                      />
                      <span>{category.label}</span>
                    </label>
                  ))}
                </div>
              </fieldset>

              {formError ? (
                <p className="supplier-error" role="alert">
                  {formError}
                </p>
              ) : null}
              {formSuccess ? (
                <p className="supplier-success" role="status">
                  {formSuccess}
                </p>
              ) : null}

              <button type="submit" disabled={isSubmitting}>
                {isSubmitting ? "Registering..." : "Register supplier"}
              </button>
            </form>
          </section>
        </div>
      </section>
    </main>
  );
}
