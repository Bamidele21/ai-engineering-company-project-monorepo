"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { fetchMe, saveProfile } from "@/lib/auth/session";
import type { UserWithProfile } from "@/lib/auth/types";

export default function ProfilePage() {
  const [account, setAccount] = useState<UserWithProfile | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [address, setAddress] = useState("");

  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [saveSuccess, setSaveSuccess] = useState("");

  useEffect(() => {
    const load = async () => {
      setIsLoading(true);
      setLoadError("");

      try {
        const current = await fetchMe();
        setAccount(current);
        setName(current.profile.name ?? "");
        setPhone(current.profile.phone ?? "");
        setAddress(current.profile.address ?? "");
      } catch (error) {
        setLoadError(
          error instanceof Error
            ? error.message
            : "Unable to load your account."
        );
      } finally {
        setIsLoading(false);
      }
    };

    void load();
  }, []);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSaveError("");
    setSaveSuccess("");
    setIsSaving(true);

    try {
      const updated = await saveProfile({
        name: name.trim(),
        phone: phone.trim() || null,
        address: address.trim() || null,
      });
      setAccount((current) =>
        current ? { ...current, profile: updated } : current
      );
      setName(updated.name ?? "");
      setPhone(updated.phone ?? "");
      setAddress(updated.address ?? "");
      setSaveSuccess("Profile updated successfully.");
    } catch (error) {
      setSaveError(
        error instanceof Error ? error.message : "Unable to save your profile."
      );
    } finally {
      setIsSaving(false);
    }
  };

  const inputClass =
    "rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-slate-900 focus:outline-none";

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-xl flex-col justify-center px-4 py-12">
      <div className="rounded-xl border border-slate-200 bg-white p-8">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-sm font-medium uppercase tracking-wide text-slate-500">
              Nexova People and Talent
            </p>
            <h1 className="mt-2 text-2xl font-semibold text-slate-900">
              My profile
            </h1>
          </div>
          <Link
            href="/"
            className="rounded-md border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
          >
            Back to pipeline
          </Link>
        </div>

        {isLoading ? (
          <p className="mt-6 text-sm text-slate-600">Loading your profile...</p>
        ) : null}

        {!isLoading && loadError ? (
          <p
            className="mt-6 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
            role="alert"
          >
            {loadError}
          </p>
        ) : null}

        {!isLoading && !loadError && account ? (
          <>
            <dl className="mt-6 grid gap-3 rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm">
              <div className="flex items-center justify-between gap-4">
                <dt className="font-medium text-slate-500">Email</dt>
                <dd className="text-slate-900">{account.email}</dd>
              </div>
              <div className="flex items-center justify-between gap-4">
                <dt className="font-medium text-slate-500">Role</dt>
                <dd className="capitalize text-slate-900">{account.role}</dd>
              </div>
            </dl>

            <form className="mt-6 grid gap-4" onSubmit={handleSubmit} noValidate>
              <label className="grid gap-1.5 text-sm font-medium text-slate-700">
                Full name
                <input
                  type="text"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  className={inputClass}
                />
              </label>

              <label className="grid gap-1.5 text-sm font-medium text-slate-700">
                Phone
                <input
                  type="tel"
                  value={phone}
                  onChange={(event) => setPhone(event.target.value)}
                  className={inputClass}
                />
              </label>

              <label className="grid gap-1.5 text-sm font-medium text-slate-700">
                Address
                <input
                  type="text"
                  value={address}
                  onChange={(event) => setAddress(event.target.value)}
                  className={inputClass}
                />
              </label>

              {saveError ? (
                <p
                  className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
                  role="alert"
                >
                  {saveError}
                </p>
              ) : null}
              {saveSuccess ? (
                <p
                  className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700"
                  role="status"
                >
                  {saveSuccess}
                </p>
              ) : null}

              <button
                type="submit"
                disabled={isSaving}
                className="justify-self-start rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-70"
              >
                {isSaving ? "Saving..." : "Save profile"}
              </button>
            </form>
          </>
        ) : null}
      </div>
    </main>
  );
}
