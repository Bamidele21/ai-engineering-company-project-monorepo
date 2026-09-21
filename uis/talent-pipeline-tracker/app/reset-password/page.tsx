"use client";

import { FormEvent, Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
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
  const [formError, setFormError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFormError("");

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

    setIsSubmitting(true);

    try {
      await resetPassword({ token, newPassword: password });
      router.replace("/login?reset=success");
    } catch (resetError) {
      setFormError(
        resetError instanceof Error
          ? resetError.message
          : "This reset link is invalid or has expired. Request a new one."
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  const inputClass =
    "rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-slate-900 focus:outline-none";

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-md flex-col justify-center px-4 py-12">
      <div className="rounded-xl border border-slate-200 bg-white p-8">
        <p className="text-sm font-medium uppercase tracking-wide text-slate-500">
          Nexova People and Talent
        </p>
        <h1 className="mt-2 text-2xl font-semibold text-slate-900">
          Choose a new password
        </h1>
        <p className="mt-2 text-sm text-slate-600">
          Pick a password with at least 8 characters.
        </p>

        {!token ? (
          <div className="mt-6 grid gap-4">
            <p
              className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
              role="alert"
            >
              This reset link is missing its token. Request a new link.
            </p>
            <Link
              href="/forgot-password"
              className="justify-self-start font-medium text-slate-900"
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
                className={inputClass}
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
              <div className="grid gap-1">
                <p
                  className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
                  role="alert"
                >
                  {formError}
                </p>
                <Link
                  href="/forgot-password"
                  className="text-sm font-medium text-slate-900"
                >
                  Request a new reset link
                </Link>
              </div>
            ) : null}

            <button
              type="submit"
              disabled={isSubmitting}
              className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-70"
            >
              {isSubmitting ? "Updating..." : "Set new password"}
            </button>
          </form>
        )}
      </div>
    </main>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center text-sm text-slate-500">
          Loading reset form...
        </div>
      }
    >
      <ResetPasswordForm />
    </Suspense>
  );
}
