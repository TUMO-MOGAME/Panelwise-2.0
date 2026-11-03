// @vitest-environment jsdom
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { AuditView, FrameView, ShotView } from "@/lib/api/types";

let params = new URLSearchParams();
const replace = vi.fn();
const back = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn(), replace, back }),
  usePathname: () => "/projects/p1/storyboard",
  useSearchParams: () => params,
}));
// A plain anchor: the test drives the URL itself through `params`.
vi.mock("next/link", () => ({
  default: ({ href, scroll, ...rest }: { href: string; scroll?: boolean } & React.AnchorHTMLAttributes<HTMLAnchorElement>) => {
    void scroll;
    return <a href={href} {...rest} onClick={(e) => (e.preventDefault(), rest.onClick?.(e))} />;
  },
}));

import { frame, keeper, lines, shots } from "./fixtures";
import { positions, sourceBlocks, spanWords } from "./sheet";
import { StoryboardPage } from "./StoryboardPage";

beforeEach(() => {
  params = new URLSearchParams();
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(() => {
  replace.mockReset();
  back.mockReset();
});

const byId = (id: string) => shots.find((s) => s.id === id)!;
const board = (frames: FrameView[] = []) => ({ lines, shots, frames });
const page = (frames: FrameView[] = []) => <StoryboardPage project={keeper()} board={board(frames)} />;
const at = (shot: string | null) => {
  params = new URLSearchParams(shot ? { shot } : {});
};
const audit = (over: Partial<AuditView>): AuditView => ({
  attempt: 1, seed: 1, verdict: "pass", description: null, judgement: null, checks: [], positions: {}, models: [], created_at: "",
  ...over,
});

describe("the sheet's words (web.md §4.4, T045's rules)", () => {
  it("each part under its speaker, labelled only when the speaker changes", () => {
    expect(sourceBlocks(byId("1.4"))).toEqual([
      { speaker: "THABO (O.S.)", text: "The boat didn't. I walked the last mile along the cliff." },
    ]);
    expect(sourceBlocks(byId("2.2"))).toEqual([
      { speaker: "THABO", text: "It's gone." },
      { speaker: null, text: "All of it." },
      { speaker: "THABO (CONT'D)", text: "The whole coast." },
    ]);
    expect(sourceBlocks(byId("1.1"))).toEqual([{ speaker: null, text: byId("1.1").source }]);
  });

  it("a heading-only shot's part has no segment, so no label", () => {
    const establishing: ShotView = { ...byId("2.1"), source: "EXT. LIGHTHOUSE GALLERY -- CONTINUOUS", segments: [] };
    expect(sourceBlocks(establishing)).toEqual([{ speaker: null, text: "EXT. LIGHTHOUSE GALLERY -- CONTINUOUS" }]);
  });

  it("the span in words, with its scene", () => {
    const scene = keeper().scene_list![0];
    expect(spanWords(byId("1.4").span, scene)).toBe("Page 1, lines 17–18 · scene 1, INT. LIGHTHOUSE KITCHEN - NIGHT");
    expect(spanWords(byId("1.3").span, scene)).toBe("Page 1, line 14 · scene 1, INT. LIGHTHOUSE KITCHEN - NIGHT");
  });

  it("positions come from the last audit that passed or warned; none before T021", () => {
    expect(positions(undefined)).toEqual({});
    expect(positions(frame({ shot_id: "1.4", state: "rendering" }))).toEqual({});
    const audits = [
      audit({ attempt: 1, verdict: "warn", positions: { NANDI: "right" } }),
      audit({ attempt: 2, verdict: "pass", positions: { NANDI: "left" } }),
      audit({ attempt: 3, verdict: "fail", positions: { NANDI: "centre" } }),
    ];
    expect(positions(frame({ shot_id: "1.4", state: "passed", audits }))).toEqual({ NANDI: "left" });
  });
});

describe("FrameSheet (web.md §4.4; storyboard-frame.png)", () => {
  it("?shot= opens it, named 'Shot 1.4', with the header, the source and who is in frame", () => {
    at("1.4");
    render(page([frame({ shot_id: "1.4", state: "passed", attempt: 2, image_url: "https://s/14", audits: [audit({ positions: { NANDI: "left" } })] })]));
    const sheet = screen.getByRole("dialog", { name: "Shot 1.4" });
    expect(sheet).toHaveTextContent("Medium · Static · NIGHT");
    expect(within(sheet).getByText("Passed audit")).toBeInTheDocument();
    expect(within(sheet).getByAltText("Frame for shot 1.4")).toHaveAttribute("src", "https://s/14");
    const source = within(sheet).getByRole("region", { name: "From the script" });
    expect(within(source).getByText("THABO (O.S.)")).toBeInTheDocument();
    expect(within(source).getByText("The boat didn't. I walked the last mile along the cliff.")).toBeInTheDocument();
    expect(source).not.toHaveTextContent("“");
    expect(source).toHaveTextContent("Page 1, lines 17–18 · scene 1, INT. LIGHTHOUSE KITCHEN - NIGHT");
    const inFrame = within(sheet).getByRole("region", { name: "In frame" });
    expect(within(inFrame).getByRole("listitem")).toHaveTextContent("NANDIleft");
  });

  it("sits above the board: its scrim and panel outrank a card's `relative z-10` Try another render", () => {
    at("3.1");
    render(page([frame({ shot_id: "3.1", state: "withheld", withheld_check: "text_in_frame" })]));
    expect(document.querySelector("[data-sheet-scrim]")).toHaveClass("z-50");
    expect(screen.getByRole("dialog")).toHaveClass("z-50");
  });

  it("an id that names no shot opens nothing", () => {
    at("9.9");
    render(page());
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("before any frames row: no verdict, the hatched panel, chips without positions", () => {
    at("1.1");
    render(page());
    const sheet = screen.getByRole("dialog", { name: "Shot 1.1" });
    expect(within(sheet).getByText("Not rendered yet")).toBeInTheDocument();
    expect(within(sheet).queryByText(/passed|withheld|rendering/i)).toBeNull();
    expect(within(sheet).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["NANDI", "oilskin coat", "two chipped mugs"]);
  });

  it("no one and nothing in frame says so", () => {
    at("3.1");
    render(page());
    expect(within(screen.getByRole("region", { name: "In frame" })).getByText("No one in frame")).toBeInTheDocument();
  });

  it("a withheld frame shows its reason, and its source once", () => {
    at("3.1");
    render(page([frame({ shot_id: "3.1", state: "withheld", withheld_check: "text_in_frame" })]));
    const sheet = screen.getByRole("dialog");
    expect(within(sheet).getByText("Frame withheld: failed audit (text in frame)")).toBeInTheDocument();
    expect(within(sheet).getAllByText("Silence.")).toHaveLength(1);
    expect(within(sheet).queryByRole("img")).toBeNull();
  });

  it("traps focus inside it", () => {
    at("1.4");
    render(page());
    expect(screen.getByRole("dialog").contains(document.activeElement)).toBe(true);
  });

  const tickOver = () => act(async () => new Promise((resolve) => setTimeout(resolve, 0)));
  const closeBy = {
    "×": () => fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Close" })),
    Esc: () => fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" }),
    // Radix dismisses on the click that follows an outside press, as a mouse makes them
    "the scrim": () => {
      const scrim = document.querySelector("[data-sheet-scrim]")!;
      fireEvent.pointerDown(scrim);
      fireEvent.click(scrim);
    },
  };

  it.each(Object.keys(closeBy) as (keyof typeof closeBy)[])(
    "%s after a loaded ?shot= replaces the URL, then focus lands on the card's link",
    async (how) => {
      at("1.4");
      const { rerender } = render(page());
      await tickOver(); // Radix listens for outside pointer-downs from the next tick
      closeBy[how]();
      expect(replace).toHaveBeenCalledWith("/projects/p1/storyboard", { scroll: false });
      expect(back).not.toHaveBeenCalled();
      at(null);
      rerender(page());
      expect(screen.queryByRole("dialog")).toBeNull();
      await tickOver(); // Radix hands focus back a tick after the sheet unmounts
      expect(screen.getByRole("link", { name: "Open shot 1.4" })).toHaveFocus();
    },
  );

  it.each(Object.keys(closeBy) as (keyof typeof closeBy)[])(
    "%s after a card opened it goes back, so the history holds no duplicate page",
    async (how) => {
      const { rerender } = render(page());
      fireEvent.click(screen.getByRole("link", { name: "Open shot 2.2" }));
      at("2.2");
      rerender(page());
      await tickOver();
      closeBy[how]();
      expect(back).toHaveBeenCalledOnce();
      expect(replace).not.toHaveBeenCalled();
      at(null);
      rerender(page());
      expect(screen.queryByRole("dialog")).toBeNull();
      await tickOver();
      expect(screen.getByRole("link", { name: "Open shot 2.2" })).toHaveFocus();
    },
  );

  it("Back and Forward over a card-opened entry still close it by going back", () => {
    const { rerender } = render(page());
    fireEvent.click(screen.getByRole("link", { name: "Open shot 1.1" }));
    at("1.1");
    rerender(page());
    at(null); // the browser's Back
    rerender(page());
    at("1.1"); // and Forward
    rerender(page());
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(back).toHaveBeenCalledOnce();
    expect(replace).not.toHaveBeenCalled();
  });

  it("one card, then another: each closes by going back", () => {
    const { rerender } = render(page());
    fireEvent.click(screen.getByRole("link", { name: "Open shot 1.1" }));
    at("1.1");
    rerender(page());
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    at(null);
    rerender(page());
    fireEvent.click(screen.getByRole("link", { name: "Open shot 1.2" }));
    at("1.2");
    rerender(page());
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(back).toHaveBeenCalledTimes(2);
    expect(replace).not.toHaveBeenCalled();
  });

  it("a frame row that disappears while open shows the no-row panel", () => {
    at("2.2");
    const { rerender } = render(page([frame({ shot_id: "2.2", state: "auditing" })]));
    rerender(page([]));
    expect(within(screen.getByRole("dialog")).getByText("Not rendered yet")).toBeInTheDocument();
  });

  it("follows the frame live while it is open", () => {
    at("2.2");
    const { rerender } = render(page([frame({ shot_id: "2.2", state: "auditing" })]));
    expect(within(screen.getByRole("dialog")).getByText("Auditing attempt 1 of 3")).toBeInTheDocument();
    rerender(page([frame({ shot_id: "2.2", state: "passed", image_url: "https://s/22" })]));
    expect(within(screen.getByRole("dialog")).getByAltText("Frame for shot 2.2")).toBeInTheDocument();
  });

  it("a loaded ?shot= brings its card into view behind the sheet", () => {
    at("2.1");
    render(page());
    expect(document.getElementById("shot-2.1")!.scrollIntoView).toHaveBeenCalled();
  });

  it("2.2: three parts, its speaker labelled twice (THABO, then THABO (CONT'D))", () => {
    at("2.2");
    render(page());
    const source = screen.getByRole("region", { name: "From the script" });
    expect(within(source).getByText("THABO")).toBeInTheDocument();
    expect(within(source).getByText("THABO (CONT'D)")).toBeInTheDocument();
  });
});
