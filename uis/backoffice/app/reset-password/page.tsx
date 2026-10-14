"use client";

import { FormEvent, Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  AUTH_INPUT_CLASS,
  AUTH_SUBMIT_CLASS,
  AuthAlert,
  AuthCard,
} from "@/components/auth/AuthCard";
import { useAuthSubmit } from "@/hooks/useAuthSubmit";
import { resetPassword } from "@/lib/auth/session";

function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";

  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [fieldErrors, setFieldErrors] = useState<{
    password?: string;
    confirmPassword?: string;
  }>({});

  const { formError, isSubmitting, run } = useAuthSubmit();

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    const nextErrors: { password?: string; confirmPassword?: string } = {};
    if (password.length < 8) {
      nextErrors.password = "Password must be at least 8 characters.";
    }
    if (confirmPassword !== password) {
      nextErrors.confirmPassword = "Passwords do not match.";
    }

    setFieldErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) {
      return;
    }

    await run({
      fallback: "This reset link is invalid or has expired. Request a new one.",
      action: async () => {
        await resetPassword({ token, newPassword: password });
        router.replace("/login?reset=success");
      },
    });
  };

  return (
    <AuthCard
      title="Choose a new password"
      subtitle="Pick a password with at least 8 characters."
    >
      {!token ? (
        <div className="mt-6 grid gap-4">
          <AuthAlert>
            This reset link is missing its token. Request a new link.
          </AuthAlert>
          <Link
            href="/forgot-password"
            className="justify-self-start font-semibold text-teal-700"
          >
            Request a new reset link
          </Link>
        </div>
      ) : (
        <form className="mt-6 grid gap-4" onSubmit={handleSubmit} noValidate>
          <label className="grid gap-1.5 text-sm font-medium text-slate-700">
            New password
            <input
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className={AUTH_INPUT_CLASS}
              required
            />
            {fieldErrors.password ? (
              <span className="text-xs font-normal text-red-600">
                {fieldErrors.password}
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

          {formError ? (
            <div className="grid gap-1">
              <AuthAlert>{formError}</AuthAlert>
              <Link
                href="/forgot-password"
                className="text-sm font-semibold text-teal-700"
              >
                Request a new reset link
              </Link>
            </div>
          ) : null}

          <button type="submit" disabled={isSubmitting} className={AUTH_SUBMIT_CLASS}>
            {isSubmitting ? "Updating..." : "Set new password"}
          </button>
        </form>
      )}
    </AuthCard>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center bg-slate-50 text-sm text-slate-500">
          Loading reset form...
        </div>
      }
    >
      <ResetPasswordForm />
    </Suspense>
  );
}
