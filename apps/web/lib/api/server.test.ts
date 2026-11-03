import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getBoard, getProject } from "./server";

const fetchMock = vi.fn<typeof fetch>();
const user = { email: null, accessToken: "tok" };

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  vi.stubEnv("API_URL", "http://api.test:8000");
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  fetchMock.mockReset();
});

describe("getProject", () => {
  it("reads one project by its id, encoded as one path segment", async () => {
    fetchMock.mockResolvedValue(Response.json({ id: "p1" }));
    expect(await getProject(user, "p1")).toEqual({ kind: "ok", project: { id: "p1" } });
    await getProject(user, "a/b");
    expect(fetchMock.mock.calls[1]![0]).toBe("http://api.test:8000/api/v1/projects/a%2Fb");
  });

  it.each([".", ".."])("the dot segment %s is not found, and the API is never called", async (id) => {
    // encodeURIComponent leaves dot segments alone, and a URL parser would resolve them away.
    expect(await getProject(user, id)).toEqual({ kind: "not-found" });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("a 404 is not found: missing, malformed and someone else's are the same answer (web.md §6)", async () => {
    fetchMock.mockResolvedValue(Response.json({ error: "not_found" }, { status: 404 }));
    expect(await getProject(user, "p1")).toEqual({ kind: "not-found" });
  });

  it.each([
    ["a 503", () => fetchMock.mockResolvedValue(Response.json({ error: "storage_unavailable" }, { status: 503 }))],
    ["no answer", () => fetchMock.mockRejectedValue(new TypeError("fetch failed"))],
  ])("%s is unavailable", async (_name, arrange) => {
    arrange();
    expect(await getProject(user, "p1")).toEqual({ kind: "unavailable" });
  });
});

describe("getBoard (web.md §4.3)", () => {
  it("reads lines, shots and frames in parallel with the user's token", async () => {
    fetchMock.mockImplementation(async (url) => Response.json({ url: String(url) }));
    const got = await getBoard(user, "p1");
    expect(got).toEqual({
      kind: "ok",
      lines: { url: "http://api.test:8000/api/v1/projects/p1/lines" },
      shots: { url: "http://api.test:8000/api/v1/projects/p1/shots" },
      frames: { url: "http://api.test:8000/api/v1/projects/p1/frames" },
    });
    for (const [, init] of fetchMock.mock.calls) {
      expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer tok");
    }
  });

  it.each([
    ["a 409 from …/shots", () => fetchMock.mockImplementation(async (url) =>
      String(url).endsWith("/shots") ? Response.json({ error: "not_ready" }, { status: 409 }) : Response.json([]))],
    ["a 503 from …/frames", () => fetchMock.mockImplementation(async (url) =>
      String(url).endsWith("/frames") ? Response.json({ error: "storage_unavailable" }, { status: 503 }) : Response.json([]))],
    ["no answer", () => fetchMock.mockRejectedValue(new TypeError("fetch failed"))],
  ])("%s makes the board unavailable", async (_name, arrange) => {
    arrange();
    expect(await getBoard(user, "p1")).toEqual({ kind: "unavailable" });
  });
});
