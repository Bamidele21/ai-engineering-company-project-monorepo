"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import {
  AUTH_INPUT_CLASS,
  AUTH_SUBMIT_CLASS,
  AuthAlert,
  AuthCard,
} from "@/components/auth/AuthCard";
import { useAuthSubmit } from "@/hooks/useAuthSubmit";
import { changePassword } from "@/lib/auth/session";

export default function ChangePasswordPage() {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  const [fieldErrors, setFieldErrors] = useState<{
    newPassword?: string;
    confirmPassword?: string;
  }>({});
  const [success, setSuccess] = useState("");

  const { formError, isSubmitting, run } = useAuthSubmit();

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
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

    await run({
      fallback: "Unable to change your password.",
      action: async () => {
        await changePassword({ currentPassword, newPassword });
        setCurrentPassword("");
        setNewPassword("");
        setConfirmPassword("");
        setSuccess("Your password has been updated.");
      },
    });
  };

  return (
    <AuthCard
      maxWidth="xl"
      title="Change password"
      subtitle="Enter your current password and choose a new one with at least 8 characters."
      action={
        <Link
          href="/account/profile"
          className="rounded-md border border-slate-300 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-100"
        >
          Back to profile
        </Link>
      }
    >
      <form className="mt-6 grid gap-4" onSubmit={handleSubmit} noValidate>
        <label className="grid gap-1.5 text-sm font-medium text-slate-700">
          Current password
          <input
            type="password"
            autoComplete="current-password"
            value={currentPassword}
            onChange={(event) => setCurrentPassword(event.target.value)}
            className={AUTH_INPUT_CLASS}
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
            className={AUTH_INPUT_CLASS}
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
            className={AUTH_INPUT_CLASS}
            required
          />
          {fieldErrors.confirmPassword ? (
            <span className="text-xs font-normal text-red-600">
              {fieldErrors.confirmPassword}
            </span>
          ) : null}
        </label>

        {formError ? <AuthAlert>{formError}</AuthAlert> : null}
        {success ? <AuthAlert tone="success">{success}</AuthAlert> : null}

        <button
          type="submit"
          disabled={isSubmitting}
          className={`justify-self-start ${AUTH_SUBMIT_CLASS}`}
        >
          {isSubmitting ? "Updating..." : "Update password"}
        </button>
      </form>
    </AuthCard>
  );
}
