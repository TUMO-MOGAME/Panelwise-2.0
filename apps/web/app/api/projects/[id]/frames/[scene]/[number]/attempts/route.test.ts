import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const currentUser = vi.fn();
vi.mock("@/lib/supabase/server", () => ({ currentUser: () => currentUser() }));

import { POST } from "./route";

const fetchMock = vi.fn<typeof fetch>();
const user = { email: "judge@panelwise.demo", accessToken: "tok-123" };
const ctx = (id: string, scene = "0", number = "1") => ({ params: Promise.resolve({ id, scene, number }) });
const req = () => new Request("http://web.test", { method: "POST" });

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

describe("POST /api/projects/[id]/frames/[scene]/[number]/attempts (web.md §6)", () => {
  it("answers a signed-out caller with 401 JSON", async () => {
    currentUser.mockResolvedValue(null);
    expect((await POST(req(), ctx("p1"))).status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("posts to the API with the user's token and relays its 202", async () => {
    currentUser.mockResolvedValue(user);
    fetchMock.mockResolvedValue(Response.json({ shot_id: "1.1", state: "rendering" }, { status: 202 }));
    const res = await POST(req(), ctx("p1", "0", "1"));
    expect(res.status).toBe(202);
    expect(await res.json()).toEqual({ shot_id: "1.1", state: "rendering" });
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("http://api.test:8000/api/v1/projects/p1/frames/0/1/attempts");
    expect(init?.method).toBe("POST");
    expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer tok-123");
  });

  it.each([
    [404, { error: "not_found" }],
    [409, { error: "not_withheld" }],
    [503, { error: "renderer_unavailable" }],
  ])("passes the API's %i through", async (status, body) => {
    currentUser.mockResolvedValue(user);
    fetchMock.mockResolvedValue(Response.json(body, { status }));
    const res = await POST(req(), ctx("p1"));
    expect([res.status, await res.json()]).toEqual([status, body]);
  });

  it.each([
    ["..", "0", "1"],
    ["p1", "x", "1"],
    ["p1", "0", "../1"],
  ])("%s / %s / %s names no frame and never reaches the API", async (id, scene, number) => {
    currentUser.mockResolvedValue(user);
    expect((await POST(req(), ctx(id, scene, number))).status).toBe(404);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("an unreachable API is a 503", async () => {
    currentUser.mockResolvedValue(user);
    fetchMock.mockRejectedValue(new TypeError("fetch failed"));
    expect((await POST(req(), ctx("p1"))).status).toBe(503);
  });
});
