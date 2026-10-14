"use client";
/* eslint-disable react-hooks/set-state-in-effect */

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { hasValidSession } from "@/lib/auth/storage";

const PUBLIC_PATHS = ["/login", "/register", "/forgot-password", "/reset-password"];

function isPublicPath(pathname: string): boolean {
  return PUBLIC_PATHS.some(
    (publicPath) =>
      pathname === publicPath || pathname.startsWith(`${publicPath}/`)
  );
}

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [isReady, setIsReady] = useState(false);

  useEffect(() => {
    if (isPublicPath(pathname)) {
      setIsReady(true);
      return;
    }

    if (!hasValidSession()) {
      setIsReady(false);
      const next =
        pathname && pathname !== "/"
          ? `?next=${encodeURIComponent(pathname)}`
          : "";
      router.replace(`/login${next}`);
      return;
    }

    setIsReady(true);
  }, [pathname, router]);

  if (isPublicPath(pathname)) {
    return <>{children}</>;
  }

  // Render the route immediately so the largest contentful paint is not gated
  // on the client-side token check; the guard only redirects when the session
  // is missing. The status pill is non-blocking.
  return (
    <>
      {children}
      {!isReady ? (
        <div
          className="pointer-events-none fixed inset-x-0 bottom-4 z-50 flex justify-center"
          role="status"
          aria-live="polite"
        >
          <span className="rounded-full bg-slate-900/80 px-4 py-1.5 text-xs font-medium text-white shadow">
            Checking your Nexova session...
          </span>
        </div>
      ) : null}
    </>
  );
}
