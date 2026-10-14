"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  AUTH_INPUT_CLASS,
  AUTH_SUBMIT_CLASS,
  AuthAlert,
  AuthCard,
} from "@/components/auth/AuthCard";
import { useAuthSubmit } from "@/hooks/useAuthSubmit";
import { register } from "@/lib/auth/session";

interface FieldErrors {
  email?: string;
  password?: string;
  confirmPassword?: string;
}

export default function RegisterPage() {
  const router = useRouter();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [address, setAddress] = useState("");

  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const { formError, isSubmitting, run } = useAuthSubmit();

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    const nextErrors: FieldErrors = {};
    if (!email.trim()) {
      nextErrors.email = "Work email is required.";
    }
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
      fallback: "Unable to create your account.",
      action: async () => {
        await register({
          email: email.trim(),
          password,
          name: name.trim(),
          phone: phone.trim(),
          address: address.trim(),
        });
        router.replace("/");
      },
    });
  };

  return (
    <AuthCard
      maxWidth="lg"
      title="Create your operations account"
      subtitle="Contact details are optional and can be updated later in your profile."
    >
      <form className="mt-6 grid gap-4" onSubmit={handleSubmit} noValidate>
        <label className="grid gap-1.5 text-sm font-medium text-slate-700">
          Work email *
          <input
            type="email"
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            className={AUTH_INPUT_CLASS}
            required
          />
          {fieldErrors.email ? (
            <span className="text-xs font-normal text-red-600">
              {fieldErrors.email}
            </span>
          ) : null}
        </label>

        <div className="grid gap-4 sm:grid-cols-2">
          <label className="grid gap-1.5 text-sm font-medium text-slate-700">
            Password *
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
            Confirm password *
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
        </div>

        <label className="grid gap-1.5 text-sm font-medium text-slate-700">
          Full name
          <input
            type="text"
            autoComplete="name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            className={AUTH_INPUT_CLASS}
          />
        </label>

        <div className="grid gap-4 sm:grid-cols-2">
          <label className="grid gap-1.5 text-sm font-medium text-slate-700">
            Phone
            <input
              type="tel"
              autoComplete="tel"
              value={phone}
              onChange={(event) => setPhone(event.target.value)}
              className={AUTH_INPUT_CLASS}
            />
          </label>

          <label className="grid gap-1.5 text-sm font-medium text-slate-700">
            Address
            <input
              type="text"
              autoComplete="street-address"
              value={address}
              onChange={(event) => setAddress(event.target.value)}
              className={AUTH_INPUT_CLASS}
            />
          </label>
        </div>

        {formError ? <AuthAlert>{formError}</AuthAlert> : null}

        <button type="submit" disabled={isSubmitting} className={AUTH_SUBMIT_CLASS}>
          {isSubmitting ? "Creating account..." : "Create account"}
        </button>
      </form>

      <p className="mt-6 text-sm text-slate-600">
        Already have an account?{" "}
        <Link href="/login" className="font-semibold text-teal-700">
          Sign in
        </Link>
      </p>
    </AuthCard>
  );
}
