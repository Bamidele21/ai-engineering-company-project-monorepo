import { getToken } from "../auth/storage";

interface SessionState {
  id: string;
  userId: string | null;
}

let session: SessionState | null = null;

export function randomUuid(): string {
  const cryptoApi = globalThis.crypto;
  if (cryptoApi && typeof cryptoApi.randomUUID === "function") {
    return cryptoApi.randomUUID();
  }

  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (character) => {
    const random = Math.floor(Math.random() * 16);
    const value = character === "x" ? random : (random & 0x3) | 0x8;
    return value.toString(16);
  });
}

function decodeTokenClaims(token: string | null): { sub?: string } | null {
  if (!token) {
    return null;
  }

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
    return JSON.parse(atob(padded)) as { sub?: string };
  } catch {
    return null;
  }
}

function tokenUserId(): string | null {
  const claims = decodeTokenClaims(getToken());
  if (!claims?.sub || !/^\d+$/.test(claims.sub)) {
    return null;
  }
  return claims.sub;
}

export function getSessionId(): string {
  if (!session) {
    session = { id: randomUuid(), userId: tokenUserId() };
  }
  return session.id;
}

export function getSessionUserId(): string | null {
  if (!session) {
    getSessionId();
  }
  return session?.userId ?? null;
}

export function startAuthenticatedSession(): void {
  session = { id: randomUuid(), userId: tokenUserId() };
}

export function endSession(): void {
  session = { id: randomUuid(), userId: null };
}

export function createRequestId(): string {
  return randomUuid();
}

export function resetTelemetrySessionForTests(): void {
  session = null;
}
