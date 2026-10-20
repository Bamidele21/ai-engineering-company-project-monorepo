"use client";

import { FormEvent, useState } from "react";
import { authorizedFetch } from "@/lib/auth/client";
import { parseApiError } from "@/lib/api/errors";
import {
  CATEGORY_OPTIONS,
  INITIAL_FORM,
  SUPPLIERS_API_URL,
  type NewSupplierForm,
  type SupplierCategory,
  type SupplierCountry,
  type SupplierCreatePayload,
} from "@/lib/suppliers";

interface SupplierRegistrationFormProps {
  onCreated: () => Promise<void> | void;
}

export default function SupplierRegistrationForm({
  onCreated,
}: SupplierRegistrationFormProps) {
  const [newSupplier, setNewSupplier] = useState<NewSupplierForm>(INITIAL_FORM);
  const [formError, setFormError] = useState("");
  const [formSuccess, setFormSuccess] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

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
      const response = await authorizedFetch(`${SUPPLIERS_API_URL}/suppliers`, {
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
      await onCreated();
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

  return (
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
                  status: event.target.value as "active" | "suspended",
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
  );
}
