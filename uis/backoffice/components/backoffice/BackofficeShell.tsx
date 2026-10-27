"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

interface NavItem {
  href: string;
  label: string;
  icon: string;
  match: string;
}

const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Overview", icon: "01", match: "/" },
  { href: "/suppliers", label: "Supplier directory", icon: "02", match: "/suppliers" },
  { href: "/incidents", label: "Incident analyzer", icon: "03", match: "/incidents" },
  {
    href: "/inventory/products",
    label: "Inventory",
    icon: "04",
    match: "/inventory",
  },
  { href: "/telemetry", label: "Telemetry", icon: "05", match: "/telemetry" },
  { href: "/reporting", label: "Reporting", icon: "06", match: "/reporting" },
];

function isActive(pathname: string, match: string): boolean {
  if (match === "/") {
    return pathname === "/";
  }

  return pathname === match || pathname.startsWith(`${match}/`);
}

interface BackofficeShellProps {
  eyebrow: string;
  title: string;
  initials: string;
  connectedLabel?: string;
  pageClassName?: string;
  children: React.ReactNode;
}

export function BackofficeShell({
  eyebrow,
  title,
  initials,
  connectedLabel,
  pageClassName,
  children,
}: BackofficeShellProps) {
  const pathname = usePathname();
  const rootClassName = pageClassName
    ? `bo-shell ${pageClassName}`
    : "bo-shell";

  return (
    <main className={rootClassName}>
      <aside className="bo-nav">
        <Link className="bo-brand" href="/">
          <b>N</b>
          <span>
            <strong>Nexova</strong>
            <small>Operations studio</small>
          </span>
        </Link>
        <nav aria-label="Backoffice navigation">
          {NAV_ITEMS.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`bo-nav-link${
                isActive(pathname, item.match) ? " active" : ""
              }`}
            >
              {item.icon}&nbsp;&nbsp;{item.label}
            </Link>
          ))}
        </nav>
        {connectedLabel ? (
          <small className="bo-connected">● {connectedLabel}</small>
        ) : null}
      </aside>

      <section className="bo-main">
        <header className="bo-header">
          <div>
            <p>{eyebrow}</p>
            <h1>{title}</h1>
          </div>
          <span>{initials}</span>
        </header>
        <div className="bo-content">{children}</div>
      </section>
    </main>
  );
}
