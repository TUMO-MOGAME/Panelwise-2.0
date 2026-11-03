import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const currentUser = vi.fn();
vi.mock("@/lib/supabase/server", () => ({ currentUser: () => currentUser() }));

import { GET, POST } from "./route";

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

describe("GET and POST /api/projects/[id]/comic (web.md §4.5, §6)", () => {
  it("answers a signed-out caller with 401 and never calls the API", async () => {
    currentUser.mockResolvedValue(null);
    expect((await GET(new Request("http://web.test"), ctx("p1"))).status).toBe(401);
    expect((await POST(new Request("http://web.test"), ctx("p1"))).status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("relays the comic view, read with the user's token", async () => {
    currentUser.mockResolvedValue(user);
    fetchMock.mockResolvedValue(Response.json({ can_make: false, shots: 21, job: null, comic: null }));
    const res = await GET(new Request("http://web.test"), ctx("p1"));
    expect(await res.json()).toEqual({ can_make: false, shots: 21, job: null, comic: null });
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("http://api.test:8000/api/v1/projects/p1/comic");
    expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer tok-123");
  });

  it.each([
    [202, { job: { id: "j1", state: "running" } }],
    [409, { error: "comic_running" }],
    [503, { error: "renderer_unavailable" }],
  ])("relays Make the comic's %i unchanged", async (status, body) => {
    currentUser.mockResolvedValue(user);
    fetchMock.mockResolvedValue(Response.json(body, { status }));
    const res = await POST(new Request("http://web.test", { method: "POST" }), ctx("p1"));
    expect([res.status, await res.json()]).toEqual([status, body]);
    expect(fetchMock.mock.calls[0]![1]?.method).toBe("POST");
  });

  it("never sends a dot segment, and says the API is unreachable when it is", async () => {
    currentUser.mockResolvedValue(user);
    expect((await GET(new Request("http://web.test"), ctx(".."))).status).toBe(404);
    expect(fetchMock).not.toHaveBeenCalled();
    fetchMock.mockRejectedValue(new Error("down"));
    expect((await POST(new Request("http://web.test"), ctx("p1"))).status).toBe(503);
  });
});
