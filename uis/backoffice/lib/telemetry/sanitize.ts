const MAX_MESSAGE_LENGTH = 300;
const EMAIL_PATTERN = /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi;
const URL_PATTERN = /https?:\/\/[^\s]+/gi;
const SENSITIVE_QUERY_PATTERN =
  /([?&](?:token|next|email|password|reset_token)=)[^\s&#]+/gi;

const SERVICE_URLS = [
  {
    name: "inventory-api",
    value: process.env.NEXT_PUBLIC_INVENTORY_API_URL ?? "http://localhost:8001",
  },
  {
    name: "supply-directory-api",
    value: process.env.NEXT_PUBLIC_SUPPLIERS_API_URL ?? "http://localhost:8000",
  },
  {
    name: "analyzer-api",
    value: process.env.NEXT_PUBLIC_ANALYZER_API_URL ?? "http://localhost:8000",
  },
];

export function stripQuery(value: string): string {
  return value.split("?")[0].split("#")[0];
}

export function pagePath(pathname: string): string {
  return stripQuery(pathname) || "/";
}

export function sanitizeMessage(message: string): string {
  return message
    .replace(EMAIL_PATTERN, "[email]")
    .replace(URL_PATTERN, "[url]")
    .replace(SENSITIVE_QUERY_PATTERN, "$1[redacted]")
    .slice(0, MAX_MESSAGE_LENGTH);
}

export function firstStackFrame(stack: string | undefined): string | null {
  if (!stack) {
    return null;
  }
  const frame = stack
    .split("\n")
    .map((line) => line.trim())
    .find((line) => line.startsWith("at "));
  if (!frame) {
    return null;
  }
  const location = frame.match(/\(([^)]+)\)/)?.[1];
  if (location) {
    return location.split(" ")[0].slice(0, 200);
  }
  return frame.replace(/^at\s+/, "").split(" ")[0].slice(0, 200);
}

export function normalizeNetworkTarget(url: string): string {
  let parsed: URL;
  try {
    parsed = new URL(url, "http://localhost");
  } catch {
    return `api:${stripQuery(url)}`;
  }

  const match = SERVICE_URLS.find((service) => parsed.origin === service.value);
  const path = stripQuery(parsed.pathname);
  return match ? `${match.name}:${path}` : `api:${path}`;
}
