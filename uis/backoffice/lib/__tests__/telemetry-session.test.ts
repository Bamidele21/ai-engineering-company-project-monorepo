import { beforeEach, describe, expect, it, jest } from "@jest/globals";

jest.mock("../auth/storage", () => ({
  getToken: jest.fn(),
}));

import { getToken } from "../auth/storage";
import {
  createRequestId,
  endSession,
  getSessionId,
  getSessionUserId,
  resetTelemetrySessionForTests,
  startAuthenticatedSession,
} from "../telemetry/session";

const getTokenMock = getToken as jest.MockedFunction<typeof getToken>;

function tokenFor(subject: string): string {
  const encode = (value: object) =>
    Buffer.from(JSON.stringify(value))
      .toString("base64")
      .replace(/\+/g, "-")
      .replace(/\//g, "_")
      .replace(/=+$/, "");
  return `${encode({ alg: "HS256" })}.${encode({ sub: subject })}.signature`;
}

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

beforeEach(() => {
  resetTelemetrySessionForTests();
  getTokenMock.mockReturnValue(null);
});

describe("telemetry session", () => {
  it("starts as an anonymous session with a stable id", () => {
    const first = getSessionId();
    const second = getSessionId();

    expect(first).toMatch(UUID_PATTERN);
    expect(second).toBe(first);
    expect(getSessionUserId()).toBeNull();
  });

  it("binds an existing token subject on first use", () => {
    getTokenMock.mockReturnValue(tokenFor("7"));

    expect(getSessionUserId()).toBe("7");
  });

  it("rotates the session on login", () => {
    const anonymous = getSessionId();
    getTokenMock.mockReturnValue(tokenFor("3"));

    startAuthenticatedSession();

    expect(getSessionId()).not.toBe(anonymous);
    expect(getSessionUserId()).toBe("3");
  });

  it("rotates back to anonymous on logout", () => {
    getTokenMock.mockReturnValue(tokenFor("3"));
    startAuthenticatedSession();
    const authenticated = getSessionId();

    getTokenMock.mockReturnValue(null);
    endSession();

    expect(getSessionId()).not.toBe(authenticated);
    expect(getSessionUserId()).toBeNull();
  });

  it("ignores a non-numeric token subject", () => {
    getTokenMock.mockReturnValue(tokenFor("not-an-id"));
    expect(getSessionUserId()).toBeNull();
  });

  it("creates a new request id per call", () => {
    expect(createRequestId()).not.toBe(createRequestId());
  });
});
