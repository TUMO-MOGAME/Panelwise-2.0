import { describe, expect, it } from "vitest";

import type { Job, ProjectSummary } from "@/lib/api/types";

import { facts, isActive, rowState } from "./rowState";

const job = (over: Partial<Job> = {}): Job => ({
  id: "j1",
  state: "queued",
  stage: null,
  progress: 0,
  error: null,
  updated_at: "2026-10-06T07:14:00Z",
  ...over,
});

const project = (over: Partial<ProjectSummary> = {}): ProjectSummary => ({
  id: "p1",
  title: "The Keeper's Light",
  created_at: "2026-10-06T07:14:00Z",
  pages: null,
  scenes: null,
  shots: null,
  frames: null,
  job: job(),
  ...over,
});

const frames = (settled: number, total: number, withheld = 0, active = 0) => ({
  settled,
  total,
  withheld,
  active,
});

// web.md §4.1a, the ProjectRow table, row by row.
describe("rowState", () => {
  it("queued: pending, meter at 0", () => {
    expect(rowState(project())).toEqual({
      edge: "pencil",
      verdict: "Queued",
      tone: "pending",
      detail: null,
      meter: 0,
      error: null,
    });
  });

  it.each(["parsing", "extracting"] as const)("running, %s: reading the script, meter at progress", (stage) => {
    const s = rowState(project({ job: job({ state: "running", stage, progress: 22 }) }));
    expect(s).toMatchObject({ edge: "pencil", verdict: "Reading the script", tone: "pending", detail: null, meter: 22 });
  });

  it("running, planning: planning shots, meter at progress", () => {
    const s = rowState(project({ job: job({ state: "running", stage: "planning", progress: 40 }) }));
    expect(s).toMatchObject({ verdict: "Planning shots", tone: "pending", meter: 40 });
  });

  it("running, rendering, no frames row yet: meter at progress, no count", () => {
    const s = rowState(project({ job: job({ state: "running", stage: "rendering", progress: 60 }) }));
    expect(s).toMatchObject({ edge: "pencil", verdict: "Rendering frames", detail: null, meter: 60 });
  });

  it("running, rendering, frames set: settled of total, meter at settled ÷ total", () => {
    const s = rowState(
      project({ job: job({ state: "running", stage: "rendering", progress: 94 }), frames: frames(6, 7, 0, 1) }),
    );
    expect(s).toMatchObject({ verdict: "Rendering frames", detail: "6 of 7 settled", meter: (6 / 7) * 100 });
  });

  it("done, frames null: shots planned, no frames rendered yet", () => {
    const s = rowState(project({ shots: 19, job: job({ state: "done", stage: "planning", progress: 60 }) }));
    expect(s).toEqual({
      edge: "pass",
      verdict: "Shots planned",
      tone: "pass",
      detail: "No frames rendered yet",
      meter: null,
      error: null,
    });
  });

  it("done, frames set: storyboard ready with total and withheld", () => {
    const done = job({ state: "done", stage: "rendering", progress: 100 });
    expect(rowState(project({ job: done, frames: frames(23, 23, 1) }))).toMatchObject({
      edge: "pass",
      verdict: "Storyboard ready",
      tone: "pass",
      detail: "23 frames · 1 withheld",
      meter: null,
    });
    expect(rowState(project({ job: done, frames: frames(23, 23, 0) })).detail).toBe("23 frames");
    expect(rowState(project({ job: done, frames: frames(1, 1, 0) })).detail).toBe("1 frame");
  });

  it.each([["parsing"], ["extracting"], ["planning"], [null]] as const)(
    "failed at %s: couldn't read the script, the error verbatim",
    (stage) => {
      const error = "This PDF has no text layer. It looks like a scan.";
      expect(rowState(project({ job: job({ state: "failed", stage, error }) }))).toEqual({
        edge: "withheld",
        verdict: "Couldn't read the script",
        tone: "withheld",
        detail: null,
        meter: null,
        error,
      });
    },
  );

  it("failed at rendering: couldn't render the frames", () => {
    const s = rowState(project({ job: job({ state: "failed", stage: "rendering", error: "The renderer failed." }) }));
    expect(s).toMatchObject({ verdict: "Couldn't render the frames", error: "The renderer failed." });
  });

  it("failed with no error text shows the verdict alone, never a stand-in", () => {
    expect(rowState(project({ job: job({ state: "failed", stage: "parsing" }) })).error).toBeNull();
  });
});

describe("facts", () => {
  const uploaded = (iso: string) => `at ${iso}`;

  it("joins the known counts, singular for 1", () => {
    expect(facts(project({ pages: 2, scenes: 3, shots: 7 }), uploaded)).toBe("2 pages · 3 scenes · 7 shots");
    expect(facts(project({ pages: 1, scenes: 1, shots: 1 }), uploaded)).toBe("1 page · 1 scene · 1 shot");
    expect(facts(project({ pages: 5, scenes: 5 }), uploaded)).toBe("5 pages · 5 scenes");
  });

  it("falls back to the upload time when nothing is known", () => {
    expect(facts(project(), uploaded)).toBe("Uploaded at 2026-10-06T07:14:00Z");
  });
});

describe("isActive", () => {
  it("polls while queued or running, or while any frame is active", () => {
    expect(isActive(project())).toBe(true);
    expect(isActive(project({ job: job({ state: "running", stage: "planning" }) }))).toBe(true);
    expect(isActive(project({ job: job({ state: "done" }) }))).toBe(false);
    expect(isActive(project({ job: job({ state: "done" }), frames: frames(6, 7, 0, 1) }))).toBe(true);
    expect(isActive(project({ job: job({ state: "failed" }) }))).toBe(false);
  });
});
