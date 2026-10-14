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
import { login } from "@/lib/auth/session";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const { formError, isSubmitting, run } = useAuthSubmit();

  const resetSuccess = searchParams.get("reset") === "success";

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    await run({
      validate: () =>
        !email.trim() || !password
          ? "Enter your work email and password to continue."
          : null,
      fallback: "Unable to sign in with those credentials.",
      action: async () => {
        await login(email.trim(), password);
        const next = searchParams.get("next");
        router.replace(next && next.startsWith("/") ? next : "/");
      },
    });
  };

  return (
    <AuthCard
      title="Sign in to operations"
      subtitle="Use your Nexova account to access supplier and incident operations."
    >
      {resetSuccess ? (
        <AuthAlert tone="success" className="mt-4">
          Your password has been updated. Sign in with your new password.
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
            className={AUTH_INPUT_CLASS}
            required
          />
        </label>

        <label className="grid gap-1.5 text-sm font-medium text-slate-700">
          Password
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className={AUTH_INPUT_CLASS}
            required
          />
        </label>

        <Link
          href="/forgot-password"
          className="-mt-2 justify-self-end text-xs font-semibold text-teal-700 hover:text-teal-800"
        >
          Forgot your password?
        </Link>

        {formError ? <AuthAlert>{formError}</AuthAlert> : null}

        <button type="submit" disabled={isSubmitting} className={AUTH_SUBMIT_CLASS}>
          {isSubmitting ? "Signing in..." : "Sign in"}
        </button>
      </form>

      <p className="mt-6 text-sm text-slate-600">
        New to Nexova operations?{" "}
        <Link href="/register" className="font-semibold text-teal-700">
          Create an account
        </Link>
      </p>
    </AuthCard>
  );
}

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center bg-slate-50 text-sm text-slate-500">
          Loading sign in...
        </div>
      }
    >
      <LoginForm />
    </Suspense>
  );
}
