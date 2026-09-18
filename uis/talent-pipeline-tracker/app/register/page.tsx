"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
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
  const [formError, setFormError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFormError("");

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

    setIsSubmitting(true);

    try {
      await register({
        email: email.trim(),
        password,
        name: name.trim(),
        phone: phone.trim(),
        address: address.trim(),
      });
      router.replace("/");
    } catch (registerError) {
      setFormError(
        registerError instanceof Error
          ? registerError.message
          : "Unable to create your account."
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  const inputClass =
    "rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-slate-900 focus:outline-none";

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-lg flex-col justify-center px-4 py-12">
      <div className="rounded-xl border border-slate-200 bg-white p-8">
        <p className="text-sm font-medium uppercase tracking-wide text-slate-500">
          Nexova People and Talent
        </p>
        <h1 className="mt-2 text-2xl font-semibold text-slate-900">
          Create your tracker account
        </h1>
        <p className="mt-2 text-sm text-slate-600">
          Contact details are optional and can be updated later in your profile.
        </p>

        <form className="mt-6 grid gap-4" onSubmit={handleSubmit} noValidate>
          <label className="grid gap-1.5 text-sm font-medium text-slate-700">
            Work email *
            <input
              type="email"
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className={inputClass}
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
              Confirm password *
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
          </div>

          <label className="grid gap-1.5 text-sm font-medium text-slate-700">
            Full name
            <input
              type="text"
              autoComplete="name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              className={inputClass}
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
                className={inputClass}
              />
            </label>

            <label className="grid gap-1.5 text-sm font-medium text-slate-700">
              Address
              <input
                type="text"
                autoComplete="street-address"
                value={address}
                onChange={(event) => setAddress(event.target.value)}
                className={inputClass}
              />
            </label>
          </div>

          {formError ? (
            <p
              className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
              role="alert"
            >
              {formError}
            </p>
          ) : null}

          <button
            type="submit"
            disabled={isSubmitting}
            className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-70"
          >
            {isSubmitting ? "Creating account..." : "Create account"}
          </button>
        </form>

        <p className="mt-6 text-sm text-slate-600">
          Already have an account?{" "}
          <Link href="/login" className="font-medium text-slate-900">
            Sign in
          </Link>
        </p>
      </div>
    </main>
  );
}
