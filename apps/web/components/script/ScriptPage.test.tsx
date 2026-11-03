// @vitest-environment jsdom
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Job, Project } from "@/lib/api/types";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }) }));

import { ScriptPage } from "./ScriptPage";

const job = (over: Partial<Job> = {}): Job => ({
  id: "j1",
  state: "done",
  stage: "planning",
  progress: 60,
  error: null,
  updated_at: "2026-10-06T07:14:00Z",
  ...over,
});

// The lighthouse project of script.png.
const keeper = (over: Partial<Project> = {}): Project => ({
  id: "p1",
  title: "The Keeper's Light",
  created_at: "2026-10-06T07:14:00Z",
  pages: 2,
  scenes: 3,
  shots: 7,
  frames: null,
  job: job(),
  scene_list: [
    { index: 0, number: "1", heading: "INT. LIGHTHOUSE KITCHEN - NIGHT", time_of_day: "NIGHT", time_carried: false, elements: 4, shots: 4 },
    { index: 1, number: "2", heading: "EXT. LIGHTHOUSE GALLERY -- CONTINUOUS", time_of_day: "NIGHT", time_carried: true, elements: 4, shots: 2 },
    { index: 2, number: "3", heading: "INT. LIGHTHOUSE STAIRWELL", time_of_day: "NIGHT", time_carried: true, elements: 1, shots: 1 },
  ],
  entities: [
    {
      kind: "character",
      name: "NANDI",
      source: "model",
      scenes: [0],
      quotes: [{ text: "NANDI (60s, oilskin coat)", span: { page: 1, line_start: 7, line_end: 7 } }],
    },
    {
      kind: "character",
      name: "THABO",
      source: "model",
      scenes: [0, 1],
      quotes: [
        { text: "THABO steps out into the wind", span: { page: 1, line_start: 24, line_end: 24 } },
        { text: "holding a torn map", span: { page: 1, line_start: 24, line_end: 24 } },
      ],
    },
    {
      kind: "prop",
      name: "torn map",
      source: "model",
      scenes: [1],
      quotes: [{ text: "a torn map", span: { page: 1, line_start: 24, line_end: 24 } }],
    },
    {
      kind: "location",
      name: "LIGHTHOUSE STAIRWELL",
      source: "heading",
      scenes: [2],
      quotes: [{ text: "INT. LIGHTHOUSE STAIRWELL", span: { page: 2, line_start: 35, line_end: 35 } }],
    },
  ],
  report: {
    faithfulness: 1,
    entities_proposed: 5,
    entities_grounded: 5,
    quotes_proposed: 8,
    quotes_located: 8,
    recall: 1,
    cues_total: 2,
    cues_found_by_model: 2,
    models: ["nvidia/Nemotron-3_5-Lightning"],
    prompt_tokens: 509,
    completion_tokens: 157,
  },
  ...over,
});

describe("ScriptPage, ready (script.png)", () => {
  it("has the intro", () => {
    render(<ScriptPage project={keeper()} />);
    expect(screen.getByText("Read from the script")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "The Keeper's Light" })).toBeInTheDocument();
    expect(screen.getByText("2 pages · 3 scenes · every name below quotes the line it came from")).toBeInTheDocument();
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("lists the scenes with their heading in Courier and the carried-from line", () => {
    render(<ScriptPage project={keeper()} />);
    const scenes = screen.getByRole("navigation", { name: "Scenes" });
    expect(within(scenes).getByText("INT. LIGHTHOUSE KITCHEN - NIGHT")).toHaveClass("font-script");
    expect(within(scenes).getByText("4 action and dialogue blocks · 4 shots")).toBeInTheDocument();
    expect(within(scenes).getByText("Night, carried from scene 1 · 1 block · 1 shot")).toBeInTheDocument();
  });

  it("shows every quote in Courier with its span, the tag and where", () => {
    render(<ScriptPage project={keeper()} />);
    const thabo = screen.getByRole("article", { name: "THABO" });
    expect(within(thabo).getByText("Found by the model")).toBeInTheDocument();
    expect(within(thabo).getByText("Scenes 1, 2")).toBeInTheDocument();
    expect(within(thabo).getByText("“THABO steps out into the wind”")).toHaveClass("font-script");
    expect(within(thabo).getAllByText("p.1 l.24")).toHaveLength(2);

    const map = screen.getByRole("article", { name: "torn map" });
    expect(within(map).queryByText(/Found by the model|dialogue cues|heading/)).toBeNull();
    expect(within(map).getByText("Scene 2")).toBeInTheDocument();

    const stairwell = screen.getByRole("article", { name: "LIGHTHOUSE STAIRWELL" });
    expect(within(stairwell).getByText("From the heading")).toBeInTheDocument();
    expect(within(stairwell).queryByText(/^Scenes? /)).toBeNull();
  });

  it("says one page and one scene in the singular", () => {
    render(<ScriptPage project={keeper({ pages: 1, scenes: 1 })} />);
    expect(screen.getByText("1 page · 1 scene · every name below quotes the line it came from")).toBeInTheDocument();
  });

  it("tags a speaker added from dialogue cues", () => {
    const cue = { ...keeper().entities![0], name: "LERATO", source: "cue" as const };
    render(<ScriptPage project={keeper({ entities: [cue] })} />);
    const lerato = screen.getByRole("article", { name: "LERATO" });
    expect(within(lerato).getByText("Added from dialogue cues")).toBeInTheDocument();
  });

  it("puts the sections in order, each only with entities", () => {
    render(<ScriptPage project={keeper({ entities: keeper().entities!.filter((e) => e.kind !== "prop") })} />);
    expect(screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent)).toEqual([
      "Characters",
      "Locations",
      "Scenes",
    ]);
  });

  it("shows faithfulness and recall together, with their counts in words and the model line", () => {
    render(<ScriptPage project={keeper()} />);
    const report = screen.getByRole("complementary", { name: "How much of the script was found" });
    expect(within(report).getAllByText("1.00")).toHaveLength(2);
    expect(within(report).getByText("Faithfulness")).toBeInTheDocument();
    expect(within(report).getByText("Recall")).toBeInTheDocument();
    expect(
      within(report).getByText("5 of 5 things the model named are in the script. 8 of 8 quotes found on the page."),
    ).toBeInTheDocument();
    expect(
      within(report).getByText(
        "2 of 2 speaking characters found by the model. A speaker it misses is still added from their dialogue cues.",
      ),
    ).toBeInTheDocument();
    expect(within(report).getByText("Nemotron 3.5 Lightning · 509 tokens in, 157 out")).toBeInTheDocument();
  });

  it("stacks intro, report, entities, scenes in that order on a phone (the DOM order)", () => {
    const { container } = render(<ScriptPage project={keeper()} />);
    const order = Array.from(container.querySelectorAll("[data-area]")).map((el) => el.getAttribute("data-area"));
    expect(order).toEqual(["intro", "report", "entities", "scenes"]);
  });

  it("the scenes column opens the storyboard (script.png)", () => {
    render(<ScriptPage project={keeper()} />);
    const scenes = screen.getByRole("navigation", { name: "Scenes" });
    expect(within(scenes).getByRole("link", { name: "Open the storyboard" })).toHaveAttribute("href", "/projects/p1/storyboard");
  });
});

describe("ScriptPage, by job state (web.md §4.2's table)", () => {
  it("queued or reading: the job strip and nothing else", () => {
    render(
      <ScriptPage
        project={keeper({ job: job({ state: "running", stage: "extracting", progress: 22 }), entities: null, report: null })}
      />,
    );
    expect(screen.getByRole("status")).toHaveTextContent("Reading the script");
    expect(screen.queryByText("Read from the script")).toBeNull();
    expect(screen.queryByRole("navigation", { name: "Scenes" })).toBeNull();
  });

  it("planning: the job strip, then the page, with no shot counts", () => {
    const unplanned = keeper().scene_list!.map((s) => ({ ...s, shots: null }));
    render(
      <ScriptPage project={keeper({ job: job({ state: "running", stage: "planning", progress: 40 }), scene_list: unplanned })} />,
    );
    expect(screen.getByRole("status")).toHaveTextContent("Planning shots");
    expect(screen.getByText("4 action and dialogue blocks")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Characters" })).toBeInTheDocument();
  });

  it("failed: eyebrow and title, the verdict, the error verbatim, the stage, the way back", () => {
    const error = "Reading the script failed at scene 12A. Nothing was saved from this run. Upload the script again to retry.";
    render(<ScriptPage project={keeper({ title: "saltpan-draft-3", job: job({ state: "failed", stage: "extracting", error }) })} />);
    expect(screen.getByText("Read from the script")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "saltpan-draft-3" })).toBeInTheDocument();
    expect(screen.queryByText(/every name below/)).toBeNull();
    expect(screen.getByText("Couldn't read the script")).toBeInTheDocument();
    expect(screen.getByText(error)).toBeInTheDocument();
    expect(screen.getByText("It stopped while reading the script.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to your screenplays" })).toHaveAttribute("href", "/projects");
    expect(screen.queryByRole("navigation", { name: "Scenes" })).toBeNull();
  });

  it("failed with no stage leaves the stage line out", () => {
    render(<ScriptPage project={keeper({ job: job({ state: "failed", stage: null, error: "The server restarted while this ran. Upload the script again." }) })} />);
    expect(screen.queryByText(/^It stopped while/)).toBeNull();
  });

  it("failed at rendering says the frames couldn't be rendered", () => {
    render(<ScriptPage project={keeper({ job: job({ state: "failed", stage: "rendering", error: "x" }) })} />);
    expect(screen.getByText("Couldn't render the frames")).toBeInTheDocument();
    expect(screen.getByText("It stopped while rendering frames.")).toBeInTheDocument();
  });
});
