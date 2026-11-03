import { describe, expect, it } from "vitest";

import type { EntityView, Job, Project, ReportView, SceneView } from "@/lib/api/types";

import { entitySections, entityTag, entityWhere } from "./entities";
import { pageState } from "./pageState";
import { modelLine, scoreEdge, scoreText } from "./report";
import { carriedFrom, sceneDetail } from "./scenes";

const scene = (index: number, over: Partial<SceneView> = {}): SceneView => ({
  index,
  number: String(index + 1),
  heading: `INT. ROOM ${index + 1} - NIGHT`,
  time_of_day: "NIGHT",
  time_carried: false,
  elements: 4,
  shots: 4,
  ...over,
});

// The lighthouse script of the mockups: scene 1 sets NIGHT, scenes 2 and 3 carry it.
const lighthouse = [
  scene(0, { heading: "INT. LIGHTHOUSE KITCHEN - NIGHT", elements: 4, shots: 4 }),
  scene(1, { heading: "EXT. LIGHTHOUSE GALLERY -- CONTINUOUS", time_carried: true, elements: 4, shots: 2 }),
  scene(2, { heading: "INT. LIGHTHOUSE STAIRWELL", time_carried: true, elements: 1, shots: 1 }),
];

describe("scenes (web.md §4.2)", () => {
  it("names the scene whose own heading set a carried time, not the scene before", () => {
    expect(carriedFrom(lighthouse, 1)).toBe(lighthouse[0]);
    expect(carriedFrom(lighthouse, 2)).toBe(lighthouse[0]);
  });

  it("has no source for a scene that sets its own time", () => {
    expect(carriedFrom(lighthouse, 0)).toBeNull();
  });

  it("writes the detail line as script.png does", () => {
    expect(sceneDetail(lighthouse, 0)).toBe("4 action and dialogue blocks · 4 shots");
    expect(sceneDetail(lighthouse, 1)).toBe("Night, carried from scene 1 · 4 blocks · 2 shots");
    expect(sceneDetail(lighthouse, 2)).toBe("Night, carried from scene 1 · 1 block · 1 shot");
  });

  it("leaves the shot count out before planning, and singular for one block on the first scene", () => {
    const unplanned = [scene(0, { elements: 1, shots: null })];
    expect(sceneDetail(unplanned, 0)).toBe("1 action and dialogue block");
  });

  it("uses the scene number the script prints", () => {
    const scenes = [scene(0, { number: "12" }), scene(1, { number: "12A", time_carried: true })];
    expect(sceneDetail(scenes, 1)).toBe("Night, carried from scene 12 · 4 blocks · 4 shots");
  });

  it("sentence-cases a multi-word time", () => {
    const scenes = [
      scene(0, { time_of_day: "EARLY MORNING" }),
      scene(1, { time_of_day: "EARLY MORNING", time_carried: true }),
    ];
    expect(sceneDetail(scenes, 1)).toMatch(/^Early morning, carried from scene 1/);
  });
});

const entity = (over: Partial<EntityView>): EntityView => ({
  kind: "character",
  name: "NANDI",
  source: "model",
  scenes: [0],
  quotes: [{ text: "NANDI (60s, oilskin coat)", span: { page: 1, line_start: 7, line_end: 7 } }],
  ...over,
});

describe("entities (web.md §4.2)", () => {
  it("groups by kind in the order characters, props, locations, leaving out an empty kind", () => {
    const sections = entitySections([
      entity({ kind: "location", name: "LIGHTHOUSE KITCHEN", source: "heading" }),
      entity({ name: "NANDI" }),
      entity({ name: "THABO" }),
    ]);
    expect(sections.map((s) => [s.title, s.entities.map((e) => e.name)])).toEqual([
      ["Characters", ["NANDI", "THABO"]],
      ["Locations", ["LIGHTHOUSE KITCHEN"]],
    ]);
  });

  it("tags by source, and never a prop", () => {
    expect(entityTag(entity({ source: "model" }))).toBe("Found by the model");
    expect(entityTag(entity({ source: "cue" }))).toBe("Added from dialogue cues");
    expect(entityTag(entity({ kind: "location", source: "heading" }))).toBe("From the heading");
    expect(entityTag(entity({ kind: "prop", source: "model" }))).toBeNull();
  });

  it("says where by scene number, for characters and props only", () => {
    expect(entityWhere(entity({ scenes: [0] }), lighthouse)).toBe("Scene 1");
    expect(entityWhere(entity({ scenes: [0, 1] }), lighthouse)).toBe("Scenes 1, 2");
    expect(entityWhere(entity({ kind: "prop", scenes: [1] }), lighthouse)).toBe("Scene 2");
    expect(entityWhere(entity({ kind: "location", source: "heading", scenes: [0] }), lighthouse)).toBeNull();
  });
});

const report = (over: Partial<ReportView> = {}): ReportView => ({
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
  ...over,
});

describe("report (web.md §4.2, §6 copy)", () => {
  it("shows scores to two decimals, edged pass at 1.00 and warn below", () => {
    expect(scoreText(1)).toBe("1.00");
    expect(scoreText(0.875)).toBe("0.88");
    expect(scoreEdge(1)).toBe("pass");
    expect(scoreEdge(0.999)).toBe("warn");
  });

  it("names models by display name, unknown ids as they are, with the tokens", () => {
    expect(modelLine(report())).toBe("Nemotron 3.5 Lightning · 509 tokens in, 157 out");
    expect(
      modelLine(
        report({
          models: ["nvidia/Nemotron-3_5-Lightning", "nvidia/nemotron-3-super-120b-a12b", "acme/other-1"],
          prompt_tokens: 12345,
          completion_tokens: 2001,
        }),
      ),
    ).toBe("Nemotron 3.5 Lightning · Nemotron 3 Super · acme/other-1 · 12,345 tokens in, 2,001 out");
  });
});

const job = (over: Partial<Job> = {}): Job => ({
  id: "j1",
  state: "queued",
  stage: null,
  progress: 0,
  error: null,
  updated_at: "2026-10-06T07:14:00Z",
  ...over,
});
const project = (over: Partial<Project> = {}): Project => ({
  id: "p1",
  title: "The Keeper's Light",
  created_at: "2026-10-06T07:14:00Z",
  pages: 2,
  scenes: 3,
  shots: 7,
  frames: null,
  job: job(),
  scene_list: null,
  entities: null,
  report: null,
  ...over,
});

describe("pageState (web.md §4.2's table)", () => {
  it.each([
    ["queued", job(), null, "waiting"],
    ["reading", job({ state: "running", stage: "extracting", progress: 22 }), null, "waiting"],
    ["planning", job({ state: "running", stage: "planning", progress: 40 }), [], "live"],
    ["rendering", job({ state: "running", stage: "rendering", progress: 70 }), [], "live"],
    ["done", job({ state: "done", progress: 60 }), [], "ready"],
    ["failed", job({ state: "failed", stage: "planning", error: "x" }), [], "failed"],
    ["failed before extraction", job({ state: "failed", stage: "parsing", error: "x" }), null, "failed"],
  ] as const)("%s → %s", (_name, j, entities, expected) => {
    expect(pageState(project({ job: j, entities: entities as EntityView[] | null }))).toBe(expected);
  });
});
