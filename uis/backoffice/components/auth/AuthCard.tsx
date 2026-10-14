import type { ReactNode } from "react";

type MaxWidth = "md" | "lg" | "xl";

const MAX_WIDTH: Record<MaxWidth, string> = {
  md: "max-w-md",
  lg: "max-w-lg",
  xl: "max-w-xl",
};

export const AUTH_INPUT_CLASS =
  "rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-teal-600 focus:outline-none";

export const AUTH_SUBMIT_CLASS =
  "rounded-md bg-teal-700 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-70";

const ALERT_TONE_CLASS = {
  error: "border-red-500 bg-red-50 text-red-700",
  success: "border-emerald-500 bg-emerald-50 text-emerald-700",
} as const;

interface AuthAlertProps {
  tone?: keyof typeof ALERT_TONE_CLASS;
  className?: string;
  children: ReactNode;
}

export function AuthAlert({ tone = "error", className, children }: AuthAlertProps) {
  const classes = [
    "rounded-md border-l-4 px-3 py-2 text-sm",
    ALERT_TONE_CLASS[tone],
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <p className={classes} role={tone === "success" ? "status" : "alert"}>
      {children}
    </p>
  );
}

interface AuthCardProps {
  title: string;
  subtitle: string;
  eyebrow?: string;
  maxWidth?: MaxWidth;
  action?: ReactNode;
  children: ReactNode;
}

export function AuthCard({
  title,
  subtitle,
  eyebrow = "Nexova backoffice",
  maxWidth = "md",
  action,
  children,
}: AuthCardProps) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-12">
      <div className={`w-full ${MAX_WIDTH[maxWidth]} rounded-2xl border border-slate-200 bg-white p-8 shadow-sm`}>
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-teal-700">{eyebrow}</p>
            <h1 className="mt-2 text-2xl font-semibold text-slate-900">{title}</h1>
          </div>
          {action}
        </div>

        <p className="mt-2 text-sm text-slate-600">{subtitle}</p>

        {children}
      </div>
    </main>
  );
}
