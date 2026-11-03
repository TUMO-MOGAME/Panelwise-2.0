import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const currentUser = vi.fn();
vi.mock("@/lib/supabase/server", () => ({ currentUser: () => currentUser() }));

import { GET, POST } from "./route";

const fetchMock = vi.fn<typeof fetch>();
const user = { email: "judge@panelwise.demo", accessToken: "tok-123" };

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

const upload = () => {
  const form = new FormData();
  form.append("file", new File(["%PDF-1.7 body"], "kite.pdf", { type: "application/pdf" }));
  form.append("title", "The Red Kite");
  return new Request("http://web.test/api/projects", { method: "POST", body: form });
};

describe("POST /api/projects (web.md §4.1a)", () => {
  it("answers a signed-out caller with 401 JSON and calls nothing", async () => {
    currentUser.mockResolvedValue(null);
    const res = await POST(upload());
    expect(res.status).toBe(401);
    expect(await res.json()).toEqual({ error: "unauthorized" });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("forwards the body, its type and length, with the user's token", async () => {
    currentUser.mockResolvedValue(user);
    fetchMock.mockResolvedValue(Response.json({ project: { id: "p1" }, job: { id: "j1" } }, { status: 202 }));
    const req = upload();
    const type = req.headers.get("content-type");

    const res = await POST(req);

    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("http://api.test:8000/api/v1/projects");
    expect(init?.method).toBe("POST");
    const headers = new Headers(init?.headers);
    expect(headers.get("authorization")).toBe("Bearer tok-123");
    expect(headers.get("content-type")).toBe(type);
    const sent = await new Response(init?.body).text();
    expect(sent).toContain("%PDF-1.7 body");
    expect(sent).toContain("The Red Kite");
    expect(res.status).toBe(202);
    expect(await res.json()).toEqual({ project: { id: "p1" }, job: { id: "j1" } });
  });

  it.each([
    [400, { error: "not_a_pdf" }],
    [413, { error: "too_large" }],
    [503, { error: "storage_unavailable" }],
  ])("returns the API's %i and JSON unchanged", async (status, body) => {
    currentUser.mockResolvedValue(user);
    fetchMock.mockResolvedValue(Response.json(body, { status }));
    const res = await POST(upload());
    expect(res.status).toBe(status);
    expect(await res.json()).toEqual(body);
  });

  it("answers 503 when the API can't be reached", async () => {
    currentUser.mockResolvedValue(user);
    fetchMock.mockRejectedValue(new TypeError("fetch failed"));
    const res = await POST(upload());
    expect(res.status).toBe(503);
    expect(await res.json()).toEqual({ error: "api_unreachable" });
  });
});

describe("GET /api/projects (the poll)", () => {
  it("answers a signed-out caller with 401 JSON", async () => {
    currentUser.mockResolvedValue(null);
    const res = await GET();
    expect(res.status).toBe(401);
    expect(await res.json()).toEqual({ error: "unauthorized" });
  });

  it("returns the API's list with the user's token", async () => {
    currentUser.mockResolvedValue(user);
    fetchMock.mockResolvedValue(Response.json([{ id: "p1" }], { status: 200 }));
    const res = await GET();
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("http://api.test:8000/api/v1/projects");
    expect(new Headers(init?.headers).get("authorization")).toBe("Bearer tok-123");
    expect(init?.cache).toBe("no-store");
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual([{ id: "p1" }]);
  });

  it("answers 503 when the API can't be reached", async () => {
    currentUser.mockResolvedValue(user);
    fetchMock.mockRejectedValue(new TypeError("fetch failed"));
    expect((await GET()).status).toBe(503);
  });
});
