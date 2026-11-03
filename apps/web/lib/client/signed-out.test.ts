import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { fetchPast401, RETRY_401_MS, unauthorizedStreak } from "./signed-out";

const unauthorized = () => Response.json({ error: "unauthorized" }, { status: 401 });

describe("unauthorizedStreak (web.md §4.0, T123)", () => {
  it("one 401 is not enough to go to sign in", () => {
    expect(unauthorizedStreak().saw(401)).toBe(false);
  });

  it("the second 401 in a row is", () => {
    const streak = unauthorizedStreak();
    streak.saw(401);
    expect(streak.saw(401)).toBe(true);
  });

  it.each([200, 404, 503])("a %i between two 401s starts the count again", (status) => {
    const streak = unauthorizedStreak();
    streak.saw(401);
    expect(streak.saw(status)).toBe(false);
    expect(streak.saw(401)).toBe(false);
    expect(streak.saw(401)).toBe(true);
  });

  it("each streak counts its own 401s", () => {
    const a = unauthorizedStreak();
    const b = unauthorizedStreak();
    a.saw(401);
    expect(b.saw(401)).toBe(false);
  });
});

describe("fetchPast401 (web.md §4.0, T123)", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    fetchMock.mockReset();
  });

  it("an answer other than 401 is returned after one request", async () => {
    fetchMock.mockResolvedValueOnce(Response.json({}, { status: 503 }));
    const res = await fetchPast401("/api/x");
    expect(res.status).toBe(503);
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("a 401 asks once more, the same request, a second later", async () => {
    const body = new FormData();
    const init = { method: "POST", body };
    fetchMock.mockResolvedValueOnce(unauthorized()).mockResolvedValueOnce(Response.json({}, { status: 202 }));
    const pending = fetchPast401("/api/projects", init);
    await vi.advanceTimersByTimeAsync(RETRY_401_MS - 1);
    expect(fetchMock).toHaveBeenCalledOnce();
    await vi.advanceTimersByTimeAsync(1);
    const res = await pending;
    expect(res.status).toBe(202);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[1]).toEqual(["/api/projects", init]);
    expect(fetchMock.mock.calls[1][1]).toBe(init);
  });

  it("a second 401 is returned as it is, and no third request goes", async () => {
    fetchMock.mockImplementation(async () => unauthorized());
    const pending = fetchPast401("/api/x");
    await vi.advanceTimersByTimeAsync(RETRY_401_MS * 5);
    expect((await pending).status).toBe(401);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("a request that throws, first or second, throws", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("offline"));
    await expect(fetchPast401("/api/x")).rejects.toThrow("offline");

    fetchMock.mockResolvedValueOnce(unauthorized()).mockRejectedValueOnce(new TypeError("offline again"));
    const pending = fetchPast401("/api/x");
    const caught = pending.catch((e: unknown) => e);
    await vi.advanceTimersByTimeAsync(RETRY_401_MS);
    expect(await caught).toEqual(new TypeError("offline again"));
  });
});
