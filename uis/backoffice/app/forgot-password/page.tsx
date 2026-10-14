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
import { requestPasswordReset } from "@/lib/auth/session";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [isSubmitted, setIsSubmitted] = useState(false);

  const { formError, isSubmitting, run } = useAuthSubmit();

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    const succeeded = await run({
      validate: () => (!email.trim() ? "Enter your work email to continue." : null),
      // Only a completed 200 confirms the request was accepted. Network and
      // server failures show a generic retry message that reveals nothing
      // about whether the address is registered.
      fallback: "Something went wrong — please try again.",
      useFallbackOnly: true,
      action: async () => {
        await requestPasswordReset({ email: email.trim() });
      },
    });

    if (succeeded) {
      setIsSubmitted(true);
    }
  };

  return (
    <AuthCard
      title="Reset your password"
      subtitle="Enter your work email and we will send you a link to choose a new password."
    >
      {isSubmitted ? (
        <AuthAlert tone="success" className="mt-6">
          If that address is registered, you&apos;ll receive a reset link shortly.
        </AuthAlert>
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
            className={`${AUTH_INPUT_CLASS} disabled:bg-slate-100 disabled:text-slate-500`}
            required
          />
        </label>

        {formError ? <AuthAlert>{formError}</AuthAlert> : null}

        <button
          type="submit"
          disabled={isSubmitted || isSubmitting}
          className={AUTH_SUBMIT_CLASS}
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
    </AuthCard>
  );
}
