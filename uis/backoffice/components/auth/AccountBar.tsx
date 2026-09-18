"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { logout } from "@/lib/auth/session";
import { hasValidSession } from "@/lib/auth/storage";

const HIDDEN_PATHS = ["/login", "/register"];

export function AccountBar() {
  const pathname = usePathname();
  const router = useRouter();
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  useEffect(() => {
    const syncSession = () => setIsAuthenticated(hasValidSession());
    syncSession();
    window.addEventListener("storage", syncSession);
    return () => window.removeEventListener("storage", syncSession);
  }, [pathname]);

  const isHidden = HIDDEN_PATHS.some(
    (hiddenPath) =>
      pathname === hiddenPath || pathname.startsWith(`${hiddenPath}/`)
  );

  if (isHidden || !isAuthenticated) {
    return null;
  }

  const handleLogout = () => {
    logout();
    setIsAuthenticated(false);
    router.replace("/login");
  };

  return (
    <div className="fixed right-4 bottom-4 z-50 flex items-center gap-1 rounded-full border border-slate-200 bg-white/95 px-2 py-1.5 text-xs text-slate-700 shadow-lg backdrop-blur">
      <span className="hidden px-2 font-medium text-slate-500 sm:inline">
        Nexova session
      </span>
      <Link
        href="/account/profile"
        className="rounded-full px-3 py-1 font-medium hover:bg-slate-100"
      >
        My profile
      </Link>
      <button
        type="button"
        onClick={handleLogout}
        className="rounded-full bg-slate-900 px-3 py-1 font-medium text-white hover:bg-slate-700"
      >
        Log out
      </button>
    </div>
  );
}
