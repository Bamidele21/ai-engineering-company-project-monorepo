import { pagePath, stripQuery } from "./sanitize";

export function readNavigationDuration(): number | undefined {
  if (typeof performance === "undefined") {
    return undefined;
  }

  const entry = performance.getEntriesByType(
    "navigation"
  )[0] as PerformanceNavigationTiming | undefined;
  if (!entry || !Number.isFinite(entry.duration) || entry.duration < 0) {
    return undefined;
  }
  return Math.round(entry.duration);
}

export function sameOriginReferrer(
  referrer: string,
  origin: string
): string | undefined {
  if (!referrer) {
    return undefined;
  }
  try {
    const parsed = new URL(referrer);
    if (parsed.origin !== origin) {
      return undefined;
    }
    return pagePath(parsed.pathname) || undefined;
  } catch {
    return undefined;
  }
}

export function navigationPagePath(pathname: string): string {
  return pagePath(stripQuery(pathname));
}
