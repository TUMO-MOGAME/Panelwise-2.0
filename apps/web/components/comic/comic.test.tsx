// @vitest-environment jsdom
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const push = vi.fn();
const refresh = vi.fn();
const replace = vi.fn();
let params = new URLSearchParams();
// One router object, as Next's useRouter() gives: a new one per render would restart the poll's effect.
const router = { push, refresh, replace, back: vi.fn() };
vi.mock("next/navigation", () => ({
  useRouter: () => router,
  usePathname: () => "/projects/p1/comic",
  useSearchParams: () => params,
}));

import { keeper } from "@/components/storyboard/fixtures";
import type { ComicView, Job } from "@/lib/api/types";

import { COMIC_COPY, comicState, factsLine, hitLabel, kindWord, parsePage, placed, whoWords } from "./comic";
import { ComicPage } from "./ComicPage";
import { comic, job, said, scene, view } from "./fixtures";

const fetchMock = vi.fn<typeof fetch>();
beforeEach(() => {
  params = new URLSearchParams("page=1");
  vi.stubGlobal("fetch", fetchMock);
  window.scrollTo = vi.fn();
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  fetchMock.mockReset();
  push.mockReset();
  refresh.mockReset();
  replace.mockReset();
});

const done = keeper({ job: { ...keeper().job, state: "done", stage: "planning", progress: 60 } });

// --- the rules ------------------------------------------------------------------------------

describe("comic rules (web.md §4.5)", () => {
  it("picks the screen by the project and its comic", () => {
    const failed = keeper({ job: { ...done.job, state: "failed" } });
    const reading = keeper({ shots: null, job: { ...done.job, state: "running", stage: "extracting" } });
    const rendering = keeper({ job: { ...done.job, state: "running", stage: "rendering" } });
    expect(comicState(failed, null)).toBe("upload-failed");
    expect(comicState(reading, null)).toBe("plan-waiting");
    expect(comicState(rendering, view())).toBe("storyboard-running");
    expect(comicState(done, view())).toBe("none");
    expect(comicState(done, view({ job: job() }))).toBe("making");
    expect(comicState(done, view({ job: job({ state: "queued" }) }))).toBe("making");
    expect(comicState(done, view({ job: job({ state: "failed" }) }))).toBe("failed");
    expect(comicState(done, view({ comic: comic(), job: job() }))).toBe("reader");
  });

  it("words every kind of lettering", () => {
    const speech = said("speech", "LERATO", "LERATO", "No!", [90, 90], [0, 0, 1, 1]);
    const off = said("off_panel", "MOKGOSI", "MOKGOSI (O.S.)", "Is that my shirt?", [93, 94], [0, 0, 1, 1]);
    const vo = said("voice_over", "LERATO", "LERATO (V.O.)", "It was.", [101, 101], [0, 0, 1, 1]);
    const heading = scene("FLAT ROOF — DAY", 73, [0, 0, 1, 1]);
    expect([speech, off, vo, heading].map(whoWords)).toEqual(["LERATO", "MOKGOSI · off panel", "LERATO · voice-over", "Scene"]);
    expect(["speech", "off_panel", "voice_over", "scene"].map((k) => kindWord(k as never))).toEqual([
      "speech",
      "off panel",
      "voice-over",
      "scene heading",
    ]);
    expect(factsLine(off, "1.3")).toBe("p.2 l.93–94 · off panel · shot 1.3");
    expect(hitLabel(off)).toBe("MOKGOSI · off panel: Is that my shirt? (p.2 l.93–94)");
  });

  it("places a rect as percentages of its page", () => {
    expect(placed([497, 769, 994, 1537.5], { width: 1988, height: 3075 })).toEqual({
      left: "25%",
      top: "25.008130081300813%",
      width: "50%",
      height: "50%",
    });
  });

  it("reads ?page as a page that exists, else 1", () => {
    expect([parsePage("2", 3), parsePage("3", 3), parsePage(null, 3), parsePage("0", 3), parsePage("4", 3), parsePage("2x", 3)]).toEqual([
      2, 3, 1, 1, 1, 1,
    ]);
  });
});

// --- the screens without a comic ------------------------------------------------------------

describe("the comic page's states (comic-states.png)", () => {
  it("the plan isn't ready: the job strip and the note, nothing to press", () => {
    const reading = keeper({ shots: null, job: { ...done.job, state: "running", stage: "planning", progress: 52 } });
    render(<ComicPage project={reading} view={null} />);
    expect(screen.getByText(COMIC_COPY.planWaiting)).toBeInTheDocument();
    expect(screen.getByText(COMIC_COPY.planWaitingWhy)).toBeInTheDocument();
    expect(screen.getByText("Planning shots")).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("planned but the storyboard still running: its own note, no button", () => {
    const rendering = keeper({ job: { ...done.job, state: "running", stage: "rendering" } });
    render(<ComicPage project={rendering} view={view()} />);
    expect(screen.getByText(COMIC_COPY.storyboardRunning)).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("the upload failed: the script page's failed card", () => {
    const failed = keeper({ job: { ...done.job, state: "failed", stage: "extracting", error: "Reading the script failed at scene 2." } });
    render(<ComicPage project={failed} view={null} />);
    expect(screen.getByText("Reading the script failed at scene 2.")).toBeInTheDocument();
  });

  it("no comic, no renderer (today's real state): the reason, and the button disabled", () => {
    render(<ComicPage project={done} view={view({ can_make: false })} />);
    expect(screen.getByText(COMIC_COPY.none)).toBeInTheDocument();
    expect(screen.getByText(COMIC_COPY.explain(21))).toBeInTheDocument();
    expect(screen.getByText(COMIC_COPY.noRenderer)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: COMIC_COPY.make })).toBeDisabled();
  });

  it("Make the comic: a 202 shows the making strip at once and polls until the job settles", async () => {
    vi.useFakeTimers();
    render(<ComicPage project={done} view={view()} />);
    expect(screen.queryByText(COMIC_COPY.noRenderer)).toBeNull();
    fetchMock.mockResolvedValueOnce(Response.json({ job: job({ progress: 0 }) }, { status: 202 }));
    await act(async () => fireEvent.click(screen.getByRole("button", { name: COMIC_COPY.make })));
    expect(fetchMock).toHaveBeenCalledWith("/api/projects/p1/comic", { method: "POST" });
    expect(screen.getByText(COMIC_COPY.strip(0))).toBeInTheDocument();
    expect(screen.getByText(COMIC_COPY.making)).toBeInTheDocument();

    fetchMock.mockResolvedValueOnce(Response.json(view({ job: job({ progress: 43 }) })));
    await act(async () => vi.advanceTimersByTime(2000));
    expect(screen.getByText(COMIC_COPY.strip(43))).toBeInTheDocument();
    expect(refresh).not.toHaveBeenCalled();

    fetchMock.mockResolvedValueOnce(Response.json(view({ job: job({ state: "done", progress: 100 }), comic: comic() })));
    await act(async () => vi.advanceTimersByTime(2000));
    expect(refresh).toHaveBeenCalledTimes(1);
    // Until the refreshed page arrives: still the strip, never "No comic yet" with a live button.
    expect(screen.getByText(COMIC_COPY.strip(43))).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: COMIC_COPY.make })).toBeNull();
  });

  it("Make the comic over the demo's budget says so (T069)", async () => {
    render(<ComicPage project={done} view={view()} />);
    fetchMock.mockResolvedValueOnce(Response.json({ error: "llm_budget_spent" }, { status: 429 }));
    await act(async () => fireEvent.click(screen.getByRole("button", { name: COMIC_COPY.make })));
    expect(screen.getByRole("alert")).toHaveTextContent("The demo has used this month's model budget.");
    expect(screen.getByRole("button", { name: COMIC_COPY.make })).toBeEnabled();
  });

  it("Make the comic over the demo's drawings says so (T030)", async () => {
    render(<ComicPage project={done} view={view()} />);
    fetchMock.mockResolvedValueOnce(Response.json({ error: "image_budget_spent" }, { status: 429 }));
    await act(async () => fireEvent.click(screen.getByRole("button", { name: COMIC_COPY.make })));
    expect(screen.getByRole("alert")).toHaveTextContent("The demo has drawn this month's budget of frames.");
    expect(screen.getByRole("button", { name: COMIC_COPY.make })).toBeEnabled();
  });

  it.each([
    [503, { error: "renderer_unavailable" }, "disabled"],
    [500, { error: "boom" }, "failed"],
    [409, { error: "comic_running" }, "refresh"],
  ] as const)("Make the comic answered %i", async (status, body, outcome) => {
    render(<ComicPage project={done} view={view()} />);
    fetchMock.mockResolvedValueOnce(Response.json(body, { status }));
    await act(async () => fireEvent.click(screen.getByRole("button", { name: COMIC_COPY.make })));
    const button = screen.getByRole("button", { name: COMIC_COPY.make });
    if (outcome === "disabled") {
      expect(button).toBeDisabled();
      expect(screen.getByText(COMIC_COPY.noRenderer)).toBeInTheDocument();
    } else if (outcome === "failed") {
      expect(screen.getByRole("alert")).toHaveTextContent(COMIC_COPY.startFailed);
      expect(button).toBeEnabled();
    } else {
      expect(refresh).toHaveBeenCalled();
    }
  });

  describe("a 401 while still signed in (web.md §4.0, T123)", () => {
    const unauthorized = () => Response.json({ error: "unauthorized" }, { status: 401 });
    const making = view({ job: job({ progress: 10 }) });
    const tick = () => act(async () => vi.advanceTimersByTimeAsync(2000));
    beforeEach(() => vi.useFakeTimers());

    it("polling: one 401 stays on the page, and the next tick asks again", async () => {
      fetchMock.mockResolvedValueOnce(unauthorized()).mockResolvedValueOnce(Response.json(view({ job: job({ progress: 43 }) })));
      render(<ComicPage project={done} view={making} />);
      await tick();
      expect(push).not.toHaveBeenCalled();
      await tick();
      expect(screen.getByText(COMIC_COPY.strip(43))).toBeInTheDocument();
      expect(push).not.toHaveBeenCalled();
    });

    it("polling: the second 401 in a row goes to sign in", async () => {
      fetchMock.mockImplementation(async () => unauthorized());
      render(<ComicPage project={done} view={making} />);
      await tick();
      expect(push).not.toHaveBeenCalled();
      await tick();
      expect(push).toHaveBeenCalledExactlyOnceWith("/sign-in");
    });

    it("polling: an answer between two 401s starts the count again", async () => {
      fetchMock
        .mockResolvedValueOnce(unauthorized())
        .mockResolvedValueOnce(Response.json(view({ job: job({ progress: 43 }) })))
        .mockResolvedValueOnce(unauthorized());
      render(<ComicPage project={done} view={making} />);
      await tick();
      await tick();
      expect(screen.getByText(COMIC_COPY.strip(43))).toBeInTheDocument();
      await tick();
      expect(push).not.toHaveBeenCalled();
    });

    it("polling: no answer neither counts nor resets: 401, network error, 401 goes to sign in", async () => {
      fetchMock
        .mockResolvedValueOnce(unauthorized())
        .mockRejectedValueOnce(new TypeError("offline"))
        .mockResolvedValueOnce(unauthorized());
      render(<ComicPage project={done} view={making} />);
      await tick();
      await tick();
      expect(push).not.toHaveBeenCalled();
      await tick();
      expect(push).toHaveBeenCalledExactlyOnceWith("/sign-in");
    });

    it("polling: no second poll goes while one is unanswered", async () => {
      fetchMock.mockReturnValue(new Promise(() => {}));
      render(<ComicPage project={done} view={making} />);
      await tick();
      await tick();
      await tick();
      expect(fetchMock).toHaveBeenCalledOnce();
    });

    it("Make the comic: a 401 asks once more a second later, and its 202 starts the comic", async () => {
      render(<ComicPage project={done} view={view()} />);
      fetchMock.mockResolvedValueOnce(unauthorized()).mockResolvedValueOnce(Response.json({ job: job({ progress: 0 }) }, { status: 202 }));
      fireEvent.click(screen.getByRole("button", { name: COMIC_COPY.make }));
      await act(async () => vi.advanceTimersByTimeAsync(1000));
      expect(fetchMock.mock.calls).toEqual([
        ["/api/projects/p1/comic", { method: "POST" }],
        ["/api/projects/p1/comic", { method: "POST" }],
      ]);
      expect(screen.getByText(COMIC_COPY.strip(0))).toBeInTheDocument();
      expect(push).not.toHaveBeenCalled();
    });

    it("Make the comic: a second 401 goes to sign in", async () => {
      render(<ComicPage project={done} view={view()} />);
      fetchMock.mockImplementation(async () => unauthorized());
      fireEvent.click(screen.getByRole("button", { name: COMIC_COPY.make }));
      await act(async () => vi.advanceTimersByTimeAsync(1000));
      expect(fetchMock).toHaveBeenCalledTimes(2);
      expect(push).toHaveBeenCalledExactlyOnceWith("/sign-in");
    });
  });

  it("failed: the job's own words, the reuse line and Make the comic again", () => {
    const error = "Shot 1.3's lettering didn't fit its panel, so the comic stopped.";
    render(<ComicPage project={done} view={view({ job: job({ state: "failed", error }) })} />);
    expect(screen.getByText(error)).toBeInTheDocument();
    expect(screen.getByText(COMIC_COPY.reuse)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: COMIC_COPY.makeAgain })).toBeEnabled();
  });

  it("failed with no renderer: the button disabled, with why", () => {
    render(<ComicPage project={done} view={view({ can_make: false, job: job({ state: "failed", error: "x" }) })} />);
    expect(screen.getByRole("button", { name: COMIC_COPY.makeAgain })).toBeDisabled();
    expect(screen.getByText(COMIC_COPY.noRenderer)).toBeInTheDocument();
  });
});

// --- the reader -------------------------------------------------------------------------------

function reader(over: Partial<ComicView> = {}) {
  return render(<ComicPage project={done} view={view({ comic: comic(), job: job({ state: "done", progress: 100 }), ...over })} />);
}

describe("the reader (comic.png)", () => {
  it("shows one page, its hit areas from the rects, panel link then its lettering in tab order", () => {
    reader();
    expect(screen.getByRole("img", { name: /^Comic page 1 of 2\./ })).toHaveAttribute("src", "https://signed/comics/p1.png?e=3600");
    expect(screen.getByText(/2 pages · 4 panels · made/)).toBeInTheDocument();
    const page = screen.getByRole("figure", { name: "Page 1 of 2" });
    // DOM order is tab order (web.md §4.5).
    const order = [...page.querySelectorAll("a, button")].map((el) => el.getAttribute("aria-label"));
    expect(order).toEqual([
      "Shot 1.1 in the storyboard",
      "Scene: FLAT ROOF — DAY (p.2 l.73)",
      "Shot 1.2 in the storyboard",
      "LERATO: Come on. Come on, wind. (p.2 l.84)",
      "LERATO: No, no, no! (p.2 l.90)",
      "Shot 1.3 in the storyboard, frame not shown",
      "MOKGOSI · off panel: Is that my good shirt you are flying? (p.2 l.93–94)",
    ]);
    const link = within(page).getByRole("link", { name: "Shot 1.2 in the storyboard" });
    expect(link).toHaveAttribute("href", "/projects/p1/storyboard?shot=1.2");
    expect(link.style.left).toBe(`${(120 / 1988) * 100}%`);
    expect(link.style.top).toBe(`${(1142 / 3075) * 100}%`);
  });

  it("tracing a line: the page and the list are one selection, the card shows the script's words", () => {
    reader();
    const traced = () => screen.getByText(COMIC_COPY.traced).closest("section")!;
    expect(traced()).toHaveTextContent(COMIC_COPY.traceEmpty);
    const page = screen.getByRole("figure", { name: "Page 1 of 2" });
    const bubble = within(page).getByRole("button", { name: /Is that my good shirt/ });
    fireEvent.click(bubble);
    expect(bubble).toHaveAttribute("aria-pressed", "true");
    expect(within(bubble).getByText("p.2 l.93–94")).toBeInTheDocument();
    const list = screen.getByText(COMIC_COPY.lettering).closest("section")!;
    expect(within(list).getByRole("button", { name: /Is that my good shirt/ })).toHaveAttribute("aria-pressed", "true");
    expect(traced()).toHaveTextContent("MOKGOSI (O.S.)");
    expect(traced()).toHaveTextContent("Is that my good shirt you are flying?");
    expect(traced()).toHaveTextContent("p.2 l.93–94 · off panel · shot 1.3");
    expect(within(traced()).getByRole("link", { name: "Open shot 1.3 in the storyboard" })).toHaveAttribute(
      "href",
      "/projects/p1/storyboard?shot=1.3",
    );
    // from the list, another line; then Escape clears
    fireEvent.click(within(list).getByRole("button", { name: /No, no, no!/ }));
    expect(bubble).toHaveAttribute("aria-pressed", "false");
    expect(traced()).toHaveTextContent("p.2 l.90 · speech · shot 1.2");
    fireEvent.keyDown(window, { key: "Escape" });
    expect(traced()).toHaveTextContent(COMIC_COPY.traceEmpty);
    // selecting again clears it too, and a scene caption has no cue
    const caption = within(page).getByRole("button", { name: /FLAT ROOF/ });
    fireEvent.click(caption);
    expect(traced()).toHaveTextContent("p.2 l.73 · scene heading · shot 1.1");
    fireEvent.click(caption);
    expect(traced()).toHaveTextContent(COMIC_COPY.traceEmpty);
  });

  it("pages: Previous and Next, the arrow keys (not while typing), ?page kept in the URL", () => {
    reader();
    expect(screen.getByRole("button", { name: COMIC_COPY.previous })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: COMIC_COPY.next }));
    expect(replace).toHaveBeenLastCalledWith("/projects/p1/comic?page=2", { scroll: false });
    replace.mockReset();
    fireEvent.keyDown(window, { key: "ArrowRight" });
    expect(replace).toHaveBeenCalledExactlyOnceWith("/projects/p1/comic?page=2", { scroll: false });
    replace.mockReset();
    // Alt/Cmd + arrow is the browser's back and forward; ← on page 1 has nowhere to go
    fireEvent.keyDown(window, { key: "ArrowRight", altKey: true });
    fireEvent.keyDown(window, { key: "ArrowRight", metaKey: true });
    fireEvent.keyDown(window, { key: "ArrowLeft" });
    expect(replace).not.toHaveBeenCalled();
    const input = document.createElement("input");
    document.body.appendChild(input);
    fireEvent.keyDown(input, { key: "ArrowRight" });
    expect(replace).not.toHaveBeenCalled();
    input.remove();
  });

  it("page 2 from the URL; a page that doesn't exist is replaced by page 1", () => {
    params = new URLSearchParams("page=2");
    const { unmount } = reader();
    expect(screen.getByRole("img", { name: /^Comic page 2 of 2\./ })).toBeInTheDocument();
    expect(screen.getByText("LERATO · voice-over")).toBeInTheDocument();
    replace.mockReset();
    fireEvent.keyDown(window, { key: "ArrowRight" }); // the last page: nowhere to go
    expect(replace).not.toHaveBeenCalled();
    fireEvent.keyDown(window, { key: "ArrowLeft" });
    expect(replace).toHaveBeenLastCalledWith("/projects/p1/comic?page=1", { scroll: false });
    unmount();
    replace.mockReset();
    params = new URLSearchParams("page=9");
    reader();
    expect(replace).toHaveBeenCalledWith("/projects/p1/comic?page=1", { scroll: false });
  });

  it("an image that fails asks for fresh URLs once, then says so", async () => {
    reader();
    const fresh = comic({ pages: comic().pages.map((p) => ({ ...p, image_url: `${p.image_url}&fresh` })) });
    fetchMock.mockResolvedValueOnce(Response.json(view({ comic: fresh })));
    await act(async () => fireEvent.error(screen.getByRole("img")));
    expect(screen.getByRole("img")).toHaveAttribute("src", "https://signed/comics/p1.png?e=3600&fresh");
    await act(async () => fireEvent.error(screen.getByRole("img")));
    expect(screen.getByText(COMIC_COPY.pageFailed)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("a selection belongs to its page: a page change by the URL leaves it behind", () => {
    const { rerender } = reader();
    const page = screen.getByRole("figure", { name: "Page 1 of 2" });
    fireEvent.click(within(page).getByRole("button", { name: /No, no, no!/ }));
    expect(screen.getByText(COMIC_COPY.traced).closest("section")).toHaveTextContent("No, no, no!");
    params = new URLSearchParams("page=2");
    rerender(<ComicPage project={done} view={view({ comic: comic(), job: job({ state: "done", progress: 100 }) })} />);
    expect(screen.getByText(COMIC_COPY.traced).closest("section")).toHaveTextContent(COMIC_COPY.traceEmpty);
    expect(screen.queryAllByRole("button", { pressed: true })).toEqual([]);
  });

  it("a remake that failed above a comic: its note, the reader, no button", () => {
    reader({ job: job({ state: "failed", error: "A panel couldn't be drawn, so the comic stopped." }) });
    expect(screen.getByText("A panel couldn't be drawn, so the comic stopped.")).toBeInTheDocument();
    expect(screen.getByRole("figure", { name: "Page 1 of 2" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: COMIC_COPY.makeAgain })).toBeNull();
  });

  it("a remake running above a comic: the strip, the reader, no button", () => {
    reader({ job: job({ progress: 30 }) as Job });
    expect(screen.getByText(COMIC_COPY.strip(30))).toBeInTheDocument();
    expect(screen.getByRole("figure", { name: "Page 1 of 2" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: COMIC_COPY.make })).toBeNull();
  });
});
