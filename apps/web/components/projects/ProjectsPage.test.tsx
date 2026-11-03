// @vitest-environment jsdom
import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Job, ProjectSummary } from "@/lib/api/types";

import { ProjectsPage } from "./ProjectsPage";

const fetchMock = vi.fn<typeof fetch>();
const push = vi.fn();
// One router object, as Next's useRouter() gives: a new one per render would restart the poll's effect.
const router = { push };
vi.mock("next/navigation", () => ({ useRouter: () => router }));

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: false });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  fetchMock.mockReset();
  push.mockReset();
});

const job = (over: Partial<Job> = {}): Job => ({
  id: "j1",
  state: "running",
  stage: "planning",
  progress: 40,
  error: null,
  updated_at: "2026-10-06T07:14:00Z",
  ...over,
});
const project = (over: Partial<ProjectSummary> = {}): ProjectSummary => ({
  id: "p1",
  title: "Lost Property",
  created_at: "2026-10-06T07:14:00Z",
  pages: 9,
  scenes: 12,
  shots: null,
  frames: null,
  job: job(),
  ...over,
});

const tick = () => act(async () => vi.advanceTimersByTimeAsync(2000));

describe("ProjectsPage (web.md §4.1a)", () => {
  it("lists the screenplays newest first under its heading", () => {
    render(<ProjectsPage initial={[project({ title: "B" }), project({ id: "p2", title: "A" })]} />);
    expect(screen.getByRole("heading", { name: "Your screenplays" })).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent)).toEqual(["B", "A"]);
  });

  it("an empty list invites an upload", () => {
    render(<ProjectsPage initial={[]} />);
    expect(screen.getByText("No screenplays yet. Upload one to board it.")).toBeInTheDocument();
  });

  it("a list that couldn't load says so", () => {
    render(<ProjectsPage initial={null} />);
    expect(
      screen.getByText("Your screenplays can't be loaded right now. Reload the page to try again."),
    ).toBeInTheDocument();
  });

  it("polls every 2 s while a job is active, and stops when none is", async () => {
    const done = project({ shots: 31, job: job({ state: "done", progress: 60 }) });
    fetchMock.mockResolvedValueOnce(Response.json([done]));
    render(<ProjectsPage initial={[project()]} />);
    expect(screen.getByText("Planning shots")).toBeInTheDocument();

    await tick();
    expect(fetchMock).toHaveBeenCalledWith("/api/projects", expect.objectContaining({ cache: "no-store" }));
    expect(screen.getByText("Shots planned")).toBeInTheDocument();

    await tick();
    await tick();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("doesn't poll when nothing is active", async () => {
    render(<ProjectsPage initial={[project({ job: job({ state: "done" }) })]} />);
    await tick();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("keeps the last list when a poll fails, and tries again", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("offline")).mockResolvedValueOnce(Response.json([project()]));
    render(<ProjectsPage initial={[project()]} />);
    await tick();
    expect(screen.getByText("Planning shots")).toBeInTheDocument();
    await tick();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("one poll at a time: a slow answer is waited for, then lands, and polling goes on (T123)", async () => {
    let slow!: (r: Response) => void;
    fetchMock
      .mockReturnValueOnce(new Promise((resolve) => (slow = resolve))) // the first poll hangs past two ticks
      .mockResolvedValueOnce(Response.json([project({ title: "Next" })]));
    render(<ProjectsPage initial={[project()]} />);
    await tick();
    await tick();
    expect(fetchMock).toHaveBeenCalledOnce();
    await act(async () => slow(Response.json([project({ title: "Slow" })])));
    expect(screen.getByText("Slow")).toBeInTheDocument();
    await tick();
    expect(screen.getByText("Next")).toBeInTheDocument();
  });

  describe("a 401 while still signed in (web.md §4.0, T123)", () => {
    const unauthorized = () => Response.json({ error: "unauthorized" }, { status: 401 });

    it("one 401 keeps the list, and the next tick asks again", async () => {
      fetchMock.mockResolvedValueOnce(unauthorized()).mockResolvedValueOnce(Response.json([project({ title: "Later" })]));
      render(<ProjectsPage initial={[project()]} />);
      await tick();
      expect(screen.getByText("Lost Property")).toBeInTheDocument();
      await tick();
      expect(screen.getByText("Later")).toBeInTheDocument();
      expect(push).not.toHaveBeenCalled();
    });

    it("the second 401 in a row sends the browser to sign in", async () => {
      fetchMock.mockImplementation(async () => unauthorized());
      render(<ProjectsPage initial={[project()]} />);
      await tick();
      expect(push).not.toHaveBeenCalled();
      await tick();
      expect(push).toHaveBeenCalledExactlyOnceWith("/sign-in");
    });

    it("an answer between two 401s starts the count again", async () => {
      fetchMock
        .mockResolvedValueOnce(unauthorized())
        .mockResolvedValueOnce(Response.json([project({ title: "Changed" })]))
        .mockResolvedValueOnce(unauthorized());
      render(<ProjectsPage initial={[project()]} />);
      await tick();
      await tick();
      expect(screen.getByText("Changed")).toBeInTheDocument();
      await tick();
      expect(push).not.toHaveBeenCalled();
    });

    it("a poll with no answer neither counts nor resets: 401, network error, 401 goes to sign in", async () => {
      fetchMock
        .mockResolvedValueOnce(unauthorized())
        .mockRejectedValueOnce(new TypeError("offline"))
        .mockResolvedValueOnce(unauthorized());
      render(<ProjectsPage initial={[project()]} />);
      await tick();
      await tick();
      expect(push).not.toHaveBeenCalled();
      await tick();
      expect(push).toHaveBeenCalledExactlyOnceWith("/sign-in");
    });
  });
});
