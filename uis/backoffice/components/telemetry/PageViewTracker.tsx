"use client";

import { useEffect, useRef } from "react";
import { usePathname } from "next/navigation";
import {
  navigationPagePath,
  readNavigationDuration,
  sameOriginReferrer,
} from "@/lib/telemetry/page-view";
import { track } from "@/lib/telemetry/telemetry";

export function PageViewTracker() {
  const pathname = usePathname();
  const isFirstView = useRef(true);
  const lastTracked = useRef<{ path: string; at: number } | null>(null);

  useEffect(() => {
    const currentPath = navigationPagePath(pathname);
    const now = Date.now();
    if (
      lastTracked.current?.path === currentPath &&
      now - lastTracked.current.at < 1_000
    ) {
      return;
    }
    lastTracked.current = { path: currentPath, at: now };

    const properties: Record<string, unknown> = {
      page_path: currentPath,
    };

    if (isFirstView.current) {
      const duration = readNavigationDuration();
      if (duration !== undefined) {
        properties.load_duration_ms = duration;
      }
      const referrer = sameOriginReferrer(
        typeof document === "undefined" ? "" : document.referrer,
        typeof window === "undefined" ? "" : window.location.origin
      );
      if (referrer) {
        properties.referrer_path = referrer;
      }
      isFirstView.current = false;
    }

    track("page_view", properties);
  }, [pathname]);

  return null;
}
