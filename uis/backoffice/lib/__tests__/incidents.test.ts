import { describe, expect, it, jest } from "@jest/globals";
import { analyzeIncident, fetchTaskStatus, pollTaskStatus } from "../incidents";

function jsonResponse(status: number, body: unknown) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response;
}

const API_URL = "http://analyzer.test";

function mockFetchOnce(status: number, body: unknown) {
  const fetchMock = jest.fn(async () => jsonResponse(status, body));
  global.fetch = fetchMock as unknown as typeof fetch;
  return fetchMock;
}

function mockFetchSequence(responses: Array<[number, unknown]>) {
  let last: [number, unknown] = [500, null];
  const fetchMock = jest.fn(async () => {
    const next = responses.shift();
    if (next) {
      last = next;
    }
    return jsonResponse(last[0], last[1]);
  });
  global.fetch = fetchMock as unknown as typeof fetch;
  return fetchMock;
}

describe("analyzeIncident", () => {
  it("posts the file and returns the task id from the 202 response", async () => {
    const fetchMock = mockFetchOnce(202, { task_id: "t-1", status: "pending" });
    const file = new File(["ticket_id,date\n"], "incidents.csv", { type: "text/csv" });

    const taskId = await analyzeIncident(file, API_URL);

    expect(taskId).toBe("t-1");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${API_URL}/api/incidents/analyze`);
    expect(init?.method).toBe("POST");
    expect((init?.body as FormData).get("file")).toBe(file);
  });

  it("surfaces the API detail message when the upload is rejected", async () => {
    mockFetchOnce(400, { detail: "The uploaded CSV file is empty." });

    await expect(analyzeIncident(new File([""], "empty.csv"), API_URL)).rejects.toThrow(
      "The uploaded CSV file is empty.",
    );
  });

  it("fails when the response carries no task id", async () => {
    mockFetchOnce(202, { status: "pending" });

    await expect(analyzeIncident(new File(["a,b\n"], "x.csv"), API_URL)).rejects.toThrow(
      "The analyzer did not return a task id.",
    );
  });
});

describe("fetchTaskStatus", () => {
  it("returns the task status payload", async () => {
    mockFetchOnce(200, { task_id: "t-1", status: "success", result: { total: 3 }, error: null });

    const status = await fetchTaskStatus("t-1", API_URL);
    expect(status.task_id).toBe("t-1");
    expect(status.status).toBe("success");
  });

  it("rejects when the status endpoint fails", async () => {
    mockFetchOnce(500, { detail: "boom" });

    await expect(fetchTaskStatus("t-1", API_URL)).rejects.toThrow("boom");
  });
});

describe("pollTaskStatus", () => {
  it("polls until the worker succeeds and returns the result", async () => {
    mockFetchSequence([
      [200, { task_id: "t-1", status: "pending", result: null, error: null }],
      [200, { task_id: "t-1", status: "started", result: null, error: null }],
      [200, { task_id: "t-1", status: "success", result: { total: 3 }, error: null }],
    ]);
    const sleep = jest.fn(async () => undefined);

    const status = await pollTaskStatus("t-1", API_URL, { sleep });

    expect(status.status).toBe("success");
    expect(status.result).toEqual({ total: 3 });
    expect(sleep).toHaveBeenCalledTimes(2);
  });

  it("returns the failure status with its error instead of throwing", async () => {
    mockFetchSequence([
      [200, { task_id: "t-1", status: "pending", result: null, error: null }],
      [200, { task_id: "t-1", status: "failure", result: null, error: "InvalidCsvError: bad csv" }],
    ]);

    const status = await pollTaskStatus("t-1", API_URL, {
      sleep: async () => undefined,
    });

    expect(status.status).toBe("failure");
    expect(status.error).toContain("InvalidCsvError");
  });

  it("gives up after the timeout and points at Flower", async () => {
    mockFetchSequence([[200, { task_id: "t-1", status: "pending", result: null, error: null }]]);
    const nowValues = [0, 500, 1500];
    const now = jest.fn(() => nowValues.shift() ?? 0);

    await expect(
      pollTaskStatus("t-1", API_URL, { timeoutMs: 1000, now, sleep: async () => undefined }),
    ).rejects.toThrow("Flower");
  });

  it("does not poll again once the first check has already finished", async () => {
    const fetchMock = mockFetchOnce(200, {
      task_id: "t-1",
      status: "success",
      result: { total: 0 },
      error: null,
    });

    const status = await pollTaskStatus("t-1", API_URL, {
      sleep: async () => undefined,
    });

    expect(status.status).toBe("success");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
