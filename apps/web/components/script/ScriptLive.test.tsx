// @vitest-environment jsdom
import { act, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Job } from "@/lib/api/types";

const push = vi.fn();
const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh }) }));

import { ScriptLive } from "./ScriptLive";

const fetchMock = vi.fn<typeof fetch>();
beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  fetchMock.mockReset();
  push.mockReset();
  refresh.mockReset();
});

const job = (over: Partial<Job> = {}): Job => ({
  id: "j1",
  state: "running",
  stage: "extracting",
  progress: 22,
  error: null,
  updated_at: "2026-10-06T07:14:00Z",
  ...over,
});
const status = (j: Job) => Response.json({ id: "p1", job: j });
const tick = () => act(async () => vi.advanceTimersByTimeAsync(2000));

describe("ScriptLive (web.md §4.2, Live)", () => {
  it("polls the status every 2 s and re-renders the page when the stage changes", async () => {
    fetchMock.mockResolvedValueOnce(status(job())).mockResolvedValueOnce(status(job({ stage: "planning", progress: 40 })));
    render(<ScriptLive id="p1" job={job()} />);
    await tick();
    expect(fetchMock).toHaveBeenCalledWith("/api/projects/p1/status", expect.objectContaining({ cache: "no-store" }));
    expect(refresh).not.toHaveBeenCalled();
    await tick();
    expect(refresh).toHaveBeenCalledOnce();
  });

  it("doesn't re-render while the job stays at the same stage", async () => {
    fetchMock.mockResolvedValue(status(job({ progress: 30 })));
    render(<ScriptLive id="p1" job={job()} />);
    await tick();
    await tick();
    await tick();
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(refresh).not.toHaveBeenCalled();
  });

  it("re-renders when the state changes", async () => {
    fetchMock.mockResolvedValueOnce(status(job({ state: "done", stage: "planning" })));
    render(<ScriptLive id="p1" job={job({ stage: "planning" })} />);
    await tick();
    expect(refresh).toHaveBeenCalledOnce();
  });

  it("doesn't poll a finished job", async () => {
    render(<ScriptLive id="p1" job={job({ state: "done" })} />);
    await tick();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  describe("a 401 while still signed in (web.md §4.0, T123)", () => {
    const unauthorized = () => Response.json({ error: "unauthorized" }, { status: 401 });

    it("one 401 stays on the page, and the next tick asks again", async () => {
      fetchMock.mockResolvedValueOnce(unauthorized()).mockResolvedValueOnce(status(job()));
      render(<ScriptLive id="p1" job={job()} />);
      await tick();
      await tick();
      expect(fetchMock).toHaveBeenCalledTimes(2);
      expect(push).not.toHaveBeenCalled();
    });

    it("the second 401 in a row goes to sign in", async () => {
      fetchMock.mockImplementation(async () => unauthorized());
      render(<ScriptLive id="p1" job={job()} />);
      await tick();
      expect(push).not.toHaveBeenCalled();
      await tick();
      expect(push).toHaveBeenCalledExactlyOnceWith("/sign-in");
    });

    it("an answer between two 401s starts the count again", async () => {
      fetchMock
        .mockResolvedValueOnce(unauthorized())
        .mockResolvedValueOnce(status(job()))
        .mockResolvedValueOnce(unauthorized());
      render(<ScriptLive id="p1" job={job()} />);
      await tick();
      await tick();
      await tick();
      expect(push).not.toHaveBeenCalled();
    });

    it("a poll with no answer neither counts nor resets: 401, network error, 401 goes to sign in", async () => {
      fetchMock
        .mockResolvedValueOnce(unauthorized())
        .mockRejectedValueOnce(new TypeError("offline"))
        .mockResolvedValueOnce(unauthorized());
      render(<ScriptLive id="p1" job={job()} />);
      await tick();
      await tick();
      expect(push).not.toHaveBeenCalled();
      await tick();
      expect(push).toHaveBeenCalledExactlyOnceWith("/sign-in");
    });

    it("no second poll goes while one is unanswered", async () => {
      fetchMock.mockReturnValue(new Promise(() => {}));
      render(<ScriptLive id="p1" job={job()} />);
      await tick();
      await tick();
      await tick();
      expect(fetchMock).toHaveBeenCalledOnce();
    });
  });

  it("a failed poll tries again on the next tick", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("offline")).mockResolvedValueOnce(status(job()));
    render(<ScriptLive id="p1" job={job()} />);
    await tick();
    await tick();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
