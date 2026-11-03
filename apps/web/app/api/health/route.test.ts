import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GET } from "./route";

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  vi.stubEnv("API_URL", "http://api.test:8000");
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  fetchMock.mockReset();
});

describe("GET /api/health", () => {
  it("calls the API's health endpoint and mirrors a healthy answer", async () => {
    const api = { status: "ok", checks: { postgres: "ok", storage: "ok" } };
    fetchMock.mockResolvedValue(Response.json(api, { status: 200 }));

    const res = await GET();

    expect(fetchMock.mock.calls[0]?.[0]).toBe("http://api.test:8000/api/v1/health");
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ web: "ok", api });
  });

  it("mirrors a degraded API as 503 with the API's checks", async () => {
    const api = { status: "degraded", checks: { postgres: "ok", storage: "error: ConnectionError" } };
    fetchMock.mockResolvedValue(Response.json(api, { status: 503 }));

    const res = await GET();

    expect(res.status).toBe(503);
    expect(await res.json()).toEqual({ web: "ok", api });
  });

  it("answers 502 when the API can't be reached", async () => {
    fetchMock.mockRejectedValue(new TypeError("fetch failed"));

    const res = await GET();

    expect(res.status).toBe(502);
    expect(await res.json()).toEqual({ web: "ok", api: null, error: "api unreachable" });
  });

  it("answers 502 when something other than the API answers (not JSON)", async () => {
    fetchMock.mockResolvedValue(new Response("<html>Bad Gateway</html>", { status: 502 }));

    const res = await GET();

    expect(res.status).toBe(502);
    expect(await res.json()).toEqual({ web: "ok", api: null, error: "api unreachable" });
  });
});
