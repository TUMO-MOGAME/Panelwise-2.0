// @vitest-environment jsdom
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { FrameView, ProjectSummary } from "@/lib/api/types";

const push = vi.fn();
const refresh = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh, replace: vi.fn(), back: vi.fn() }),
  usePathname: () => "/projects/p1/storyboard",
  useSearchParams: () => new URLSearchParams(),
}));

import { frame, job, keeper, lines, shots } from "./fixtures";
import { StoryboardPage } from "./StoryboardPage";

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

const board = (frames: FrameView[] = []) => ({ lines, shots, frames });
const tick = () => act(async () => vi.advanceTimersByTimeAsync(2000));
const card = (id: string) => document.getElementById(`shot-${id}`)!;

describe("StoryboardPage by the job (web.md §4.3's table; storyboard-states.png)", () => {
  it("queued, reading or planning: the job strip and nothing else", () => {
    render(<StoryboardPage project={keeper({ shots: null, job: job({ state: "running", stage: "extracting", progress: 22 }) })} board={null} />);
    expect(screen.getByRole("status")).toHaveTextContent("Reading the script");
    expect(screen.queryByRole("region", { name: "Frames" })).toBeNull();
    expect(screen.queryByRole("complementary", { name: "Lined script" })).toBeNull();
  });

  it("failed: the eyebrow, the title and the script page's failed card", () => {
    render(
      <StoryboardPage
        project={keeper({ shots: null, job: job({ state: "failed", stage: "parsing", error: "Reading the script failed at scene 12A." }) })}
        board={null}
      />,
    );
    expect(screen.getByText("Storyboard")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "The Keeper's Light" })).toBeInTheDocument();
    const failed = screen.getByRole("region", { name: "This run failed" });
    expect(failed).toHaveTextContent("Couldn't read the script");
    expect(failed).toHaveTextContent("It stopped while reading the script.");
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("done with no frames rows: every card 'Not rendered yet', no verdict, no strip, no image", () => {
    render(<StoryboardPage project={keeper()} board={board()} />);
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.getAllByText("Not rendered yet")).toHaveLength(7);
    expect(document.querySelector("img")).toBeNull();
    expect(within(card("1.1")).queryByText(/passed|rendering|withheld/i)).toBeNull();
  });

  it("rendering: the strip with the frames settled, then the board", () => {
    render(
      <StoryboardPage
        project={keeper({ job: job({ state: "running", stage: "rendering", progress: 80 }), frames: { settled: 6, total: 7, withheld: 1, active: 1 } })}
        board={board([frame({ shot_id: "2.2", state: "auditing" })])}
      />,
    );
    expect(screen.getByRole("status")).toHaveTextContent("6 of 7 frames settled · 1 withheld");
    expect(within(card("2.2")).getByText("Auditing attempt 1 of 3")).toBeInTheDocument();
  });
});

describe("the board (web.md §4.3; storyboard.png)", () => {
  const frames = [
    frame({ shot_id: "1.1", state: "passed", image_url: "https://s/11" }),
    frame({ shot_id: "1.3", state: "warned", image_url: "https://s/13" }),
    frame({ shot_id: "1.4", state: "passed", attempt: 2, image_url: "https://s/14" }),
    frame({ shot_id: "2.1", state: "rendering" }),
    frame({ shot_id: "2.2", state: "auditing" }),
    frame({ shot_id: "3.1", state: "withheld", withheld_check: "text_in_frame" }),
  ];

  it("a heading per scene, then its cards in order", () => {
    render(<StoryboardPage project={keeper()} board={board(frames)} />);
    const board_ = screen.getByRole("region", { name: "Frames" });
    expect(within(board_).getAllByRole("heading", { level: 2 }).map((h) => h.textContent)).toEqual([
      "1INT. LIGHTHOUSE KITCHEN - NIGHT",
      "2EXT. LIGHTHOUSE GALLERY -- CONTINUOUS",
      "3INT. LIGHTHOUSE STAIRWELL",
    ]);
    expect([...board_.querySelectorAll("article")].map((a) => a.id)).toEqual(shots.map((s) => `shot-${s.id}`));
  });

  it("an <img> only for passed and warned frames", () => {
    render(<StoryboardPage project={keeper()} board={board(frames)} />);
    expect([...document.querySelectorAll("img")].map((i) => i.getAttribute("src"))).toEqual([
      "https://s/11",
      "https://s/13",
      "https://s/14",
    ]);
    expect(screen.getByAltText("Frame for shot 1.4")).toBeInTheDocument();
  });

  it("a card: id, camera, verdict, who, the verbatim source and its span", () => {
    render(<StoryboardPage project={keeper()} board={board(frames)} />);
    const c = card("1.4");
    expect(c).toHaveTextContent("1.4");
    expect(c).toHaveTextContent("Medium · Static");
    expect(c).toHaveTextContent("Passed audit");
    expect(c).toHaveTextContent("NANDI");
    expect(c).toHaveTextContent("“The boat didn't. I walked the last mile along the cliff.”");
    expect(c).toHaveTextContent("p.1 l.17–18");
    expect(c).toHaveTextContent("Passed on attempt 2 of 3");
  });

  it("a withheld card carries the source once and 'Try another render' above its link (T061)", () => {
    render(<StoryboardPage project={keeper()} board={board(frames)} />);
    const c = card("3.1");
    expect(within(c).getAllByText(/Silence\./)).toHaveLength(1);
    expect(c).toHaveTextContent("Frame withheld: failed audit (text in frame)");
    const button = within(c).getByRole("button", { name: "Try another render" });
    expect(button.parentElement).toHaveClass("relative", "z-10");
    // only the withheld card has one
    expect(within(card("1.1")).queryByRole("button")).toBeNull();
  });

  it("2.2's three parts sit on three lines", () => {
    render(<StoryboardPage project={keeper()} board={board()} />);
    expect(card("2.2").querySelectorAll("br")).toHaveLength(2);
  });

  it("each card is one tab stop: its shot id, a link that opens its sheet (web.md §4.4)", () => {
    render(<StoryboardPage project={keeper()} board={board()} />);
    expect(card("1.1")).not.toHaveAttribute("tabindex");
    const links = within(card("1.1")).getAllByRole("link");
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAccessibleName("Open shot 1.1");
    expect(links[0]).toHaveAttribute("href", "/projects/p1/storyboard?shot=1.1");
    expect(within(card("1.1")).queryByRole("button")).toBeNull();
  });
});

describe("the lined script (web.md §4.3)", () => {
  it("pages of every line, numbered globally, hidden below 1100 px", () => {
    render(<StoryboardPage project={keeper()} board={board()} />);
    const aside = screen.getByRole("complementary", { name: "Lined script" });
    expect(aside.className).toMatch(/(^| )hidden( |$)/);
    expect(aside.className).toContain("min-[1101px]:block");
    expect(within(aside).getAllByRole("region").map((r) => r.getAttribute("aria-label"))).toEqual(["Script page 1", "Script page 2"]);
    expect(aside.querySelectorAll("[data-line]")).toHaveLength(37);
    expect(aside.querySelector('[data-line="31"]')).toHaveTextContent("31");
  });

  it("each shot a labelled link; 2.2 runs on, then continues; 1.4 wavy", () => {
    render(<StoryboardPage project={keeper()} board={board()} />);
    const lines22 = screen.getAllByRole("link", { name: "Shot 2.2, p.1 l.27–33" });
    expect(lines22).toHaveLength(2);
    expect(lines22[0]).toHaveAttribute("data-runs-on", "true");
    expect(lines22[1]).toHaveAttribute("data-continued", "true");
    const l14 = screen.getByRole("link", { name: "Shot 1.4, p.1 l.17–18" });
    expect(l14.querySelector("[data-wavy]")).not.toBeNull();
    expect(l14).toHaveStyle({ top: "354px", height: "40px", left: "30px" });
  });

  it("hovering a card highlights its line and tints its lines", () => {
    render(<StoryboardPage project={keeper()} board={board()} />);
    fireEvent.mouseEnter(card("1.4"));
    expect(document.querySelector('[data-line="17"]')).toHaveClass("bg-pencil-soft");
    expect(document.querySelector('[data-line="18"]')).toHaveClass("bg-pencil-soft");
    expect(document.querySelector('[data-line="19"]')).not.toHaveClass("bg-pencil-soft");
    fireEvent.mouseLeave(card("1.4"));
    expect(document.querySelector('[data-line="17"]')).not.toHaveClass("bg-pencil-soft");
  });

  it("a focused card keeps its highlight when the pointer leaves it", () => {
    render(<StoryboardPage project={keeper()} board={board()} />);
    const link = screen.getByRole("link", { name: "Open shot 1.4" });
    act(() => link.focus());
    fireEvent.mouseLeave(card("1.4"));
    expect(document.querySelector('[data-line="17"]')).toHaveClass("bg-pencil-soft");
    act(() => link.blur());
    expect(document.querySelector('[data-line="17"]')).not.toHaveClass("bg-pencil-soft");
  });

  it("leaving one card hands the highlight back to the card with focus", () => {
    render(<StoryboardPage project={keeper()} board={board()} />);
    act(() => screen.getByRole("link", { name: "Open shot 2.1" }).focus());
    fireEvent.mouseEnter(card("1.4"));
    expect(document.querySelector('[data-line="17"]')).toHaveClass("bg-pencil-soft");
    fireEvent.mouseLeave(card("1.4"));
    expect(document.querySelector('[data-line="17"]')).not.toHaveClass("bg-pencil-soft");
    expect(document.querySelector('[data-line="24"]')).toHaveClass("bg-pencil-soft");
  });

  it("clicking a shot line focuses its card's link, which highlights it", () => {
    Element.prototype.scrollIntoView = vi.fn();
    render(<StoryboardPage project={keeper()} board={board()} />);
    fireEvent.click(screen.getByRole("link", { name: "Shot 2.1, p.1 l.24" }));
    expect(screen.getByRole("link", { name: "Open shot 2.1" })).toHaveFocus();
    expect(card("2.1").scrollIntoView).toHaveBeenCalled();
    expect(document.querySelector('[data-line="24"]')).toHaveClass("bg-pencil-soft");
  });
});

describe("live (web.md §4.3)", () => {
  const status = (s: Partial<ProjectSummary>) => Response.json({ ...keeper(), ...s });
  const rendering = { job: job({ state: "running", stage: "rendering", progress: 70 }), frames: { settled: 0, total: 7, withheld: 0, active: 1 } };

  it("fetches the frames every tick: rendering → auditing reaches the card with the same counts", async () => {
    fetchMock
      .mockResolvedValueOnce(status(rendering))
      .mockResolvedValueOnce(Response.json([frame({ shot_id: "1.1", state: "auditing" })]));
    render(<StoryboardPage project={keeper(rendering)} board={board([frame({ shot_id: "1.1", state: "rendering" })])} />);
    expect(within(card("1.1")).getByText("Rendering attempt 1 of 3")).toBeInTheDocument();
    await tick();
    expect(fetchMock.mock.calls.map((c) => c[0])).toEqual(["/api/projects/p1/status", "/api/projects/p1/frames"]);
    expect(within(card("1.1")).getByText("Auditing attempt 1 of 3")).toBeInTheDocument();
    expect(refresh).not.toHaveBeenCalled();
  });

  it("a stage change refreshes the page from the server instead", async () => {
    fetchMock.mockResolvedValueOnce(status({ ...rendering, job: job({ state: "done", stage: "rendering", progress: 100 }) }));
    render(<StoryboardPage project={keeper(rendering)} board={board()} />);
    await tick();
    expect(refresh).toHaveBeenCalledOnce();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("keeps polling after the job is done while a frame is active, and stops when none is", async () => {
    const done = { job: job(), frames: { settled: 6, total: 7, withheld: 1, active: 1 } };
    fetchMock
      .mockResolvedValueOnce(status(done))
      .mockResolvedValueOnce(Response.json([]))
      .mockResolvedValueOnce(status({ ...done, frames: { settled: 7, total: 7, withheld: 1, active: 0 } }))
      .mockResolvedValueOnce(Response.json([]));
    render(<StoryboardPage project={keeper(done)} board={board()} />);
    expect(screen.getByRole("status")).toBeInTheDocument();
    await tick();
    await tick();
    expect(fetchMock).toHaveBeenCalledTimes(4);
    await tick();
    expect(fetchMock).toHaveBeenCalledTimes(4);
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("an image already on screen keeps its URL when the frame hasn't changed", async () => {
    fetchMock
      .mockResolvedValueOnce(status(rendering))
      .mockResolvedValueOnce(
        Response.json([frame({ shot_id: "1.1", state: "passed", image_url: "https://s/re-signed" }), frame({ shot_id: "1.2", state: "auditing" })]),
      );
    render(<StoryboardPage project={keeper(rendering)} board={board([frame({ shot_id: "1.1", state: "passed", image_url: "https://s/first" })])} />);
    await tick();
    expect(screen.getByAltText("Frame for shot 1.1")).toHaveAttribute("src", "https://s/first");
    expect(within(card("1.2")).getByText("Auditing attempt 1 of 3")).toBeInTheDocument();
  });

  it("one round trip at a time: a tick waits while the last one's frames are still coming", async () => {
    let late!: (r: Response) => void;
    fetchMock
      .mockResolvedValueOnce(status(rendering))
      .mockReturnValueOnce(new Promise((resolve) => (late = resolve)))
      .mockResolvedValueOnce(status(rendering))
      .mockResolvedValueOnce(Response.json([frame({ shot_id: "1.1", state: "passed", image_url: "https://s/11" })]));
    render(<StoryboardPage project={keeper(rendering)} board={board()} />);
    await tick();
    await tick(); // skipped: the first is still waiting on …/frames
    expect(fetchMock).toHaveBeenCalledTimes(2);
    await act(async () => late(Response.json([frame({ shot_id: "1.1", state: "auditing" })])));
    expect(within(card("1.1")).getByText("Auditing attempt 1 of 3")).toBeInTheDocument();
    await tick();
    expect(fetchMock).toHaveBeenCalledTimes(4);
    expect(screen.getByAltText("Frame for shot 1.1")).toHaveAttribute("src", "https://s/11");
  });

  it("leaving the page aborts the request in flight", async () => {
    fetchMock.mockReturnValueOnce(new Promise(() => {}));
    const { unmount } = render(<StoryboardPage project={keeper(rendering)} board={board()} />);
    await tick();
    const signal = fetchMock.mock.calls[0]![1]!.signal!;
    expect(signal.aborted).toBe(false);
    unmount();
    expect(signal.aborted).toBe(true);
  });

  it("a failed poll is retried on the next tick", async () => {
    fetchMock
      .mockRejectedValueOnce(new TypeError("offline"))
      .mockResolvedValueOnce(status(rendering))
      .mockResolvedValueOnce(Response.json({ error: "storage_unavailable" }, { status: 503 }))
      .mockResolvedValueOnce(status(rendering))
      .mockResolvedValueOnce(Response.json([frame({ shot_id: "1.1", state: "auditing" })]));
    render(<StoryboardPage project={keeper(rendering)} board={board()} />);
    await tick();
    await tick();
    expect(within(card("1.1")).getByText("Not rendered yet")).toBeInTheDocument();
    await tick();
    expect(within(card("1.1")).getByText("Auditing attempt 1 of 3")).toBeInTheDocument();
  });

  it("no frames to fetch while the summary has none, and the poll goes on", async () => {
    const reading = { job: job({ state: "running", stage: "rendering", progress: 60 }), frames: null };
    fetchMock.mockImplementation(async () => status(reading));
    render(<StoryboardPage project={keeper(reading)} board={board()} />);
    await tick();
    await tick();
    expect(fetchMock.mock.calls.map((c) => c[0])).toEqual(["/api/projects/p1/status", "/api/projects/p1/status"]);
  });

  it("a refresh's new props replace the summary and the cards", () => {
    const { rerender } = render(
      <StoryboardPage project={keeper(rendering)} board={board([frame({ shot_id: "1.1", state: "rendering" })])} />,
    );
    expect(screen.getByRole("status")).toBeInTheDocument();
    rerender(
      <StoryboardPage
        project={keeper({ job: job({ state: "done", stage: "rendering", progress: 100 }), frames: { settled: 7, total: 7, withheld: 0, active: 0 } })}
        board={board([frame({ shot_id: "1.1", state: "passed", image_url: "https://s/11" })])}
      />,
    );
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.getByAltText("Frame for shot 1.1")).toHaveAttribute("src", "https://s/11");
  });

  it("doesn't poll a ready board", async () => {
    render(<StoryboardPage project={keeper()} board={board()} />);
    await tick();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  describe("a 401 while still signed in (web.md §4.0, T123)", () => {
    const unauthorized = () => Response.json({ error: "unauthorized" }, { status: 401 });
    const reading = { job: job({ state: "running", stage: "rendering", progress: 60 }), frames: null };

    it("one 401 stays on the page, and the next tick asks again", async () => {
      fetchMock.mockResolvedValueOnce(unauthorized()).mockResolvedValueOnce(status(reading));
      render(<StoryboardPage project={keeper(reading)} board={board()} />);
      await tick();
      await tick();
      expect(fetchMock).toHaveBeenCalledTimes(2);
      expect(push).not.toHaveBeenCalled();
    });

    it("the second 401 in a row sends the browser to sign in", async () => {
      fetchMock.mockImplementation(async () => unauthorized());
      render(<StoryboardPage project={keeper(reading)} board={board()} />);
      await tick();
      expect(push).not.toHaveBeenCalled();
      await tick();
      expect(push).toHaveBeenCalledExactlyOnceWith("/sign-in");
    });

    it("an answer between two 401s starts the count again", async () => {
      fetchMock
        .mockResolvedValueOnce(unauthorized())
        .mockResolvedValueOnce(status(reading))
        .mockResolvedValueOnce(unauthorized());
      render(<StoryboardPage project={keeper(reading)} board={board()} />);
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
      render(<StoryboardPage project={keeper(reading)} board={board()} />);
      await tick();
      await tick();
      expect(push).not.toHaveBeenCalled();
      await tick();
      expect(push).toHaveBeenCalledExactlyOnceWith("/sign-in");
    });

    it("only the status poll counts: a 401 on …/frames, twice, stays on the page", async () => {
      fetchMock
        .mockResolvedValueOnce(status(rendering))
        .mockResolvedValueOnce(unauthorized())
        .mockResolvedValueOnce(status(rendering))
        .mockResolvedValueOnce(unauthorized());
      render(<StoryboardPage project={keeper(rendering)} board={board()} />);
      await tick();
      await tick();
      expect(fetchMock.mock.calls.map((c) => c[0])).toEqual([
        "/api/projects/p1/status",
        "/api/projects/p1/frames",
        "/api/projects/p1/status",
        "/api/projects/p1/frames",
      ]);
      expect(push).not.toHaveBeenCalled();
    });

    it("no second poll goes while one is unanswered", async () => {
      fetchMock.mockReturnValue(new Promise(() => {}));
      render(<StoryboardPage project={keeper(reading)} board={board()} />);
      await tick();
      await tick();
      await tick();
      expect(fetchMock).toHaveBeenCalledOnce();
    });
  });
});
