import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const currentUser = vi.fn();
vi.mock("@/lib/supabase/server", () => ({ currentUser: () => currentUser() }));

import { GET } from "./route";

const fetchMock = vi.fn<typeof fetch>();
const user = { email: "judge@panelwise.demo", accessToken: "tok-123" };
const ctx = (id: string) => ({ params: Promise.resolve({ id }) });

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  vi.stubEnv("API_URL", "http://api.test:8000");
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  fetchMock.mockReset();
  currentUser.mockReset();
});

describe("GET /api/projects/[id]/frames (web.md §4.3)", () => {
  it("answers a signed-out caller with 401 JSON", async () => {
    currentUser.mockResolvedValue(null);
    const res = await GET(new Request("http://web.test"), ctx("p1"));
    expect(res.status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("relays the API's frames, read with the user's token", async () => {
    currentUser.mockResolvedValue(user);
    fetchMock.mockResolvedValue(Response.json([{ shot_id: "1.1", state: "auditing" }]));
    const res = await GET(new Request("http://web.test"), ctx("p1"));
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual([{ shot_id: "1.1", state: "auditing" }]);
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("http://api.test:8000/api/v1/projects/p1/frames");
    expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer tok-123");
  });

  it.each([
    [404, { error: "not_found" }],
    [503, { error: "storage_unavailable" }],
  ])("passes the API's %i through", async (status, body) => {
    currentUser.mockResolvedValue(user);
    fetchMock.mockResolvedValue(Response.json(body, { status }));
    const res = await GET(new Request("http://web.test"), ctx("p1"));
    expect(res.status).toBe(status);
    expect(await res.json()).toEqual(body);
  });

  it("a dot segment is not found and never reaches the API", async () => {
    currentUser.mockResolvedValue(user);
    const res = await GET(new Request("http://web.test"), ctx(".."));
    expect(res.status).toBe(404);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("an unreachable API is a 503", async () => {
    currentUser.mockResolvedValue(user);
    fetchMock.mockRejectedValue(new TypeError("fetch failed"));
    expect((await GET(new Request("http://web.test"), ctx("p1"))).status).toBe(503);
  });
});
