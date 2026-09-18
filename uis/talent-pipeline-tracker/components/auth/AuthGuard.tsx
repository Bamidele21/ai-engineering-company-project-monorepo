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

  if (!isReady) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-slate-500">
        Checking your Nexova session...
      </div>
    );
  }

  return <>{children}</>;
}
