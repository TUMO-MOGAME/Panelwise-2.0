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

const project = {
  id: "p1",
  title: "Kite",
  created_at: "2026-10-06T07:14:00Z",
  pages: 5,
  scenes: 5,
  shots: null,
  frames: null,
  job: { id: "j1", state: "running", stage: "planning", progress: 40, error: null, updated_at: "x" },
  scene_list: [{ index: 0 }],
  entities: [{ name: "KITE" }],
  report: { faithfulness: 1 },
};

describe("GET /api/projects/[id]/status (web.md §4.2, §4.3)", () => {
  it("answers a signed-out caller with 401 JSON", async () => {
    currentUser.mockResolvedValue(null);
    const res = await GET(new Request("http://web.test"), ctx("p1"));
    expect(res.status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("reads the project with the user's token and answers its summary only", async () => {
    currentUser.mockResolvedValue(user);
    fetchMock.mockResolvedValue(Response.json(project));
    const res = await GET(new Request("http://web.test"), ctx("p1"));
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("http://api.test:8000/api/v1/projects/p1");
    expect(new Headers(init?.headers).get("authorization")).toBe("Bearer tok-123");
    expect(res.status).toBe(200);
    const { scene_list, entities, report, ...summary } = project;
    void scene_list;
    void entities;
    void report;
    expect(await res.json()).toEqual(summary);
  });

  it("puts the id into the path as one segment", async () => {
    currentUser.mockResolvedValue(user);
    fetchMock.mockResolvedValue(Response.json({ error: "not_found" }, { status: 404 }));
    await GET(new Request("http://web.test"), ctx("../health"));
    expect(fetchMock.mock.calls[0]![0]).toBe("http://api.test:8000/api/v1/projects/..%2Fhealth");
  });

  it.each([".", ".."])("the dot segment %s is 404 not_found without calling the API", async (id) => {
    currentUser.mockResolvedValue(user);
    const res = await GET(new Request("http://web.test"), ctx(id));
    expect(res.status).toBe(404);
    expect(await res.json()).toEqual({ error: "not_found" });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("passes the API's 404 through", async () => {
    currentUser.mockResolvedValue(user);
    fetchMock.mockResolvedValue(Response.json({ error: "not_found" }, { status: 404 }));
    const res = await GET(new Request("http://web.test"), ctx("nope"));
    expect(res.status).toBe(404);
    expect(await res.json()).toEqual({ error: "not_found" });
  });

  it("answers 503 when the API can't be reached", async () => {
    currentUser.mockResolvedValue(user);
    fetchMock.mockRejectedValue(new TypeError("fetch failed"));
    expect((await GET(new Request("http://web.test"), ctx("p1"))).status).toBe(503);
  });
});
