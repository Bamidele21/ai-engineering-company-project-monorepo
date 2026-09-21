"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { requestPasswordReset } from "@/lib/auth/session";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSubmitted, setIsSubmitted] = useState(false);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError("");

    if (!email.trim()) {
      setError("Enter your work email to continue.");
      return;
    }

    setIsSubmitting(true);

    try {
      await requestPasswordReset({ email: email.trim() });
      setIsSubmitted(true);
    } catch {
      // Only a completed 200 confirms the request was accepted. Network and
      // server failures show a generic retry message that reveals nothing
      // about whether the address is registered.
      setError("Something went wrong — please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-12">
      <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
        <p className="text-xs font-semibold uppercase tracking-wide text-teal-700">
          Nexova backoffice
        </p>
        <h1 className="mt-2 text-2xl font-semibold text-slate-900">
          Reset your password
        </h1>
        <p className="mt-2 text-sm text-slate-600">
          Enter your work email and we will send you a link to choose a new
          password.
        </p>

        {isSubmitted ? (
          <p
            className="mt-6 rounded-md border-l-4 border-emerald-500 bg-emerald-50 px-3 py-2 text-sm text-emerald-700"
            role="status"
          >
            If that address is registered, you&apos;ll receive a reset link
            shortly.
          </p>
        ) : null}

        <form className="mt-6 grid gap-4" onSubmit={handleSubmit} noValidate>
          <label className="grid gap-1.5 text-sm font-medium text-slate-700">
            Work email
            <input
              type="email"
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              disabled={isSubmitted || isSubmitting}
              className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-teal-600 focus:outline-none disabled:bg-slate-100 disabled:text-slate-500"
              required
            />
          </label>

          {error ? (
            <p
              className="rounded-md border-l-4 border-red-500 bg-red-50 px-3 py-2 text-sm text-red-700"
              role="alert"
            >
              {error}
            </p>
          ) : null}

          <button
            type="submit"
            disabled={isSubmitted || isSubmitting}
            className="rounded-md bg-teal-700 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-70"
          >
            {isSubmitting
              ? "Sending..."
              : isSubmitted
                ? "Request sent"
                : "Send reset link"}
          </button>
        </form>

        <p className="mt-6 text-sm text-slate-600">
          Remembered it?{" "}
          <Link href="/login" className="font-semibold text-teal-700">
            Back to sign in
          </Link>
        </p>
      </div>
    </main>
  );
}
