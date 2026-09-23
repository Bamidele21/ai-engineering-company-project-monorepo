import {
  clearToken,
  getToken,
  hasValidSession,
  setToken,
} from "../lib/auth/storage";

function makeJwt(expSecondsFromNow: number): string {
  const header = Buffer.from(
    JSON.stringify({ alg: "HS256", typ: "JWT" })
  ).toString("base64url");
  const payload = Buffer.from(
    JSON.stringify({
      exp: Math.floor(Date.now() / 1000) + expSecondsFromNow,
    })
  ).toString("base64url");
  return `${header}.${payload}.signature`;
}

// The node test environment has no `window`/`localStorage`, so install a
// minimal in-memory stand-in that mirrors the browser storage API.
const store = new Map<string, string>();

beforeEach(() => {
  store.clear();
  (globalThis as unknown as { window: unknown }).window = {
    localStorage: {
      getItem: (key: string) => (store.has(key) ? store.get(key)! : null),
      setItem: (key: string, value: string) => {
        store.set(key, value);
      },
      removeItem: (key: string) => {
        store.delete(key);
      },
    },
  };
});

describe("getToken / setToken / clearToken", () => {
  it("round-trips a token through storage", () => {
    setToken("abc.def.ghi");
    expect(getToken()).toBe("abc.def.ghi");
  });

  it("clears a stored token", () => {
    setToken("abc.def.ghi");
    clearToken();
    expect(getToken()).toBeNull();
  });

  it("returns null when window is unavailable", () => {
    delete (globalThis as unknown as { window?: unknown }).window;
    expect(getToken()).toBeNull();
  });
});

describe("hasValidSession", () => {
  it("returns true for a valid, unexpired token", () => {
    setToken(makeJwt(3600));
    expect(hasValidSession()).toBe(true);
  });

  it("returns false for an expired token", () => {
    setToken(makeJwt(-3600));
    expect(hasValidSession()).toBe(false);
  });

  it("returns false for a malformed token", () => {
    setToken("not-a-jwt");
    expect(hasValidSession()).toBe(false);
  });

  it("returns false when no token is stored", () => {
    expect(hasValidSession()).toBe(false);
  });
});
