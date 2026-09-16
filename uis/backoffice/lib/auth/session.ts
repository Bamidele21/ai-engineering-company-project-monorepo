import { AUTH_API_URL, authorizedFetch } from "./client";
import { clearToken, setToken } from "./storage";
import type {
  Profile,
  ProfileUpdatePayload,
  RegisterPayload,
  TokenResponse,
  UserWithProfile,
} from "./types";

interface ApiErrorPayload {
  detail?: string | Array<{ msg?: string }>;
}

function parseApiError(payload: unknown, fallback: string): string {
  if (!payload || typeof payload !== "object") {
    return fallback;
  }

  const errorPayload = payload as ApiErrorPayload;
  if (typeof errorPayload.detail === "string") {
    return errorPayload.detail;
  }

  if (Array.isArray(errorPayload.detail)) {
    const messages = errorPayload.detail
      .map((entry) => entry.msg)
      .filter((entry): entry is string => Boolean(entry));

    if (messages.length > 0) {
      return messages.join(". ");
    }
  }

  return fallback;
}

async function readJson(response: Response): Promise<unknown> {
  return response.json().catch(() => null);
}

export async function login(email: string, password: string): Promise<void> {
  const response = await fetch(`${AUTH_API_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
    cache: "no-store",
  });

  if (!response.ok) {
    const payload = await readJson(response);
    throw new Error(
      parseApiError(payload, "Unable to sign in with those credentials.")
    );
  }

  const payload = (await response.json()) as TokenResponse;
  setToken(payload.access_token);
}

export async function register(payload: RegisterPayload): Promise<void> {
  const response = await fetch(`${AUTH_API_URL}/users`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email: payload.email,
      password: payload.password,
      name: payload.name ?? "",
      phone: payload.phone || null,
      address: payload.address || null,
    }),
    cache: "no-store",
  });

  if (!response.ok) {
    const errorPayload = await readJson(response);
    throw new Error(
      parseApiError(errorPayload, "Unable to create your account.")
    );
  }

  await login(payload.email, payload.password);
}

export function logout(): void {
  clearToken();
}

export async function fetchMe(): Promise<UserWithProfile> {
  const response = await authorizedFetch(`${AUTH_API_URL}/auth/me`);

  if (!response.ok) {
    const payload = await readJson(response);
    throw new Error(parseApiError(payload, "Unable to load your account."));
  }

  return (await response.json()) as UserWithProfile;
}

export async function saveProfile(
  payload: ProfileUpdatePayload
): Promise<Profile> {
  const response = await authorizedFetch(`${AUTH_API_URL}/profiles/me`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorPayload = await readJson(response);
    throw new Error(
      parseApiError(errorPayload, "Unable to save your profile.")
    );
  }

  return (await response.json()) as Profile;
}
