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

describe("GET /api/projects/[id]/storyboard/pdf (web.md §4.3, §6; T027)", () => {
  it("answers a signed-out caller with 401 and never calls the API", async () => {
    currentUser.mockResolvedValue(null);
    expect((await GET(new Request("http://web.test"), ctx("p1"))).status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("relays the signed PDF URL, asked for with the user's token", async () => {
    currentUser.mockResolvedValue(user);
    fetchMock.mockResolvedValue(Response.json({ pdf_url: "https://storage.test/sb.pdf?token=t" }));
    const res = await GET(new Request("http://web.test"), ctx("p1"));
    expect([res.status, await res.json()]).toEqual([200, { pdf_url: "https://storage.test/sb.pdf?token=t" }]);
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("http://api.test:8000/api/v1/projects/p1/storyboard/pdf");
    expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer tok-123");
  });

  it.each([
    [409, { error: "not_ready" }],
    [404, { error: "not_found" }],
    [503, { error: "styles_unavailable" }],
  ])("relays the API's %i unchanged", async (status, body) => {
    currentUser.mockResolvedValue(user);
    fetchMock.mockResolvedValue(Response.json(body, { status }));
    const res = await GET(new Request("http://web.test"), ctx("p1"));
    expect([res.status, await res.json()]).toEqual([status, body]);
  });

  it("never sends a dot segment, and says the API is unreachable when it is", async () => {
    currentUser.mockResolvedValue(user);
    expect((await GET(new Request("http://web.test"), ctx(".."))).status).toBe(404);
    expect(fetchMock).not.toHaveBeenCalled();
    fetchMock.mockRejectedValue(new Error("down"));
    expect((await GET(new Request("http://web.test"), ctx("p1"))).status).toBe(503);
  });
});
