"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { changePassword } from "@/lib/auth/session";

export default function ChangePasswordPage() {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  const [fieldErrors, setFieldErrors] = useState<{
    newPassword?: string;
    confirmPassword?: string;
  }>({});
  const [formError, setFormError] = useState("");
  const [success, setSuccess] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFormError("");
    setSuccess("");

    const nextErrors: { newPassword?: string; confirmPassword?: string } = {};
    if (newPassword.length < 8) {
      nextErrors.newPassword = "Password must be at least 8 characters.";
    }
    if (confirmPassword !== newPassword) {
      nextErrors.confirmPassword = "Passwords do not match.";
    }

    setFieldErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) {
      return;
    }

    setIsSubmitting(true);

    try {
      await changePassword({ currentPassword, newPassword });
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setSuccess("Your password has been updated.");
    } catch (error) {
      setFormError(
        error instanceof Error
          ? error.message
          : "Unable to change your password."
      );
    } finally {
      setIsSubmitting(false);
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
              Change password
            </h1>
          </div>
          <Link
            href="/account/profile"
            className="rounded-md border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-100"
          >
            Back to profile
          </Link>
        </div>

        <p className="mt-2 text-sm text-slate-600">
          Enter your current password and choose a new one with at least 8
          characters.
        </p>

        <form className="mt-6 grid gap-4" onSubmit={handleSubmit} noValidate>
          <label className="grid gap-1.5 text-sm font-medium text-slate-700">
            Current password
            <input
              type="password"
              autoComplete="current-password"
              value={currentPassword}
              onChange={(event) => setCurrentPassword(event.target.value)}
              className={inputClass}
              required
            />
          </label>

          <label className="grid gap-1.5 text-sm font-medium text-slate-700">
            New password
            <input
              type="password"
              autoComplete="new-password"
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
              className={inputClass}
              required
            />
            {fieldErrors.newPassword ? (
              <span className="text-xs font-normal text-red-600">
                {fieldErrors.newPassword}
              </span>
            ) : null}
          </label>

          <label className="grid gap-1.5 text-sm font-medium text-slate-700">
            Confirm new password
            <input
              type="password"
              autoComplete="new-password"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              className={inputClass}
              required
            />
            {fieldErrors.confirmPassword ? (
              <span className="text-xs font-normal text-red-600">
                {fieldErrors.confirmPassword}
              </span>
            ) : null}
          </label>

          {formError ? (
            <p
              className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
              role="alert"
            >
              {formError}
            </p>
          ) : null}
          {success ? (
            <p
              className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700"
              role="status"
            >
              {success}
            </p>
          ) : null}

          <button
            type="submit"
            disabled={isSubmitting}
            className="justify-self-start rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-70"
          >
            {isSubmitting ? "Updating..." : "Update password"}
          </button>
        </form>
      </div>
    </main>
  );
}
