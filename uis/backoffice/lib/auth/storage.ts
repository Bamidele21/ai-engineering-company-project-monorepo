const TOKEN_KEY = "nexova.auth.token";

export function getToken(): string | null {
  if (typeof window === "undefined") {
    return null;
  }

  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string): void {
  if (typeof window === "undefined") {
    return;
  }

  try {
    window.localStorage.setItem(TOKEN_KEY, token);
  } catch {
    // Storage can be unavailable in private or restricted browsing contexts.
  }
}

export function clearToken(): void {
  if (typeof window === "undefined") {
    return;
  }

  try {
    window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    // Ignore storage access failures during cleanup.
  }
}

function decodeExpiry(token: string): number | null {
  const parts = token.split(".");
  if (parts.length !== 3) {
    return null;
  }

  try {
    const base64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = base64.padEnd(
      base64.length + ((4 - (base64.length % 4)) % 4),
      "="
    );
    const payload = JSON.parse(atob(padded)) as { exp?: number };
    return typeof payload.exp === "number" ? payload.exp : null;
  } catch {
    return null;
  }
}

export function hasValidSession(): boolean {
  const token = getToken();
  if (!token) {
    return false;
  }

  const expiry = decodeExpiry(token);
  if (expiry === null) {
    return false;
  }

  return expiry * 1000 > Date.now();
}
