// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Job, ProjectSummary } from "@/lib/api/types";

import { ProjectRow } from "./ProjectRow";

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
  pages: 2,
  scenes: 3,
  shots: 7,
  frames: null,
  job: job(),
  ...over,
});

const row = (p: ProjectSummary) => render(<ul><ProjectRow project={p} /></ul>);

describe("ProjectRow (web.md §4.1a, projects.png, projects-states.png)", () => {
  it("rendering: verdict, settled count and a meter at settled ÷ total", () => {
    row(
      project({
        job: job({ state: "running", stage: "rendering", progress: 94 }),
        frames: { settled: 6, total: 7, withheld: 0, active: 1 },
      }),
    );
    expect(screen.getByRole("heading", { name: "The Keeper's Light" })).toBeInTheDocument();
    expect(screen.getByText("2 pages · 3 scenes · 7 shots")).toBeInTheDocument();
    expect(screen.getByText("Rendering frames")).toBeInTheDocument();
    expect(screen.getByText("6 of 7 settled")).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", String(Math.round((6 / 7) * 100)));
    expect(screen.getByRole("listitem")).toHaveAttribute("data-edge", "pencil");
  });

  it("ready: total and withheld, no meter", () => {
    row(project({ job: job({ state: "done" }), frames: { settled: 23, total: 23, withheld: 1, active: 0 } }));
    expect(screen.getByText("Storyboard ready")).toBeInTheDocument();
    expect(screen.getByText("23 frames · 1 withheld")).toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).toBeNull();
    expect(screen.getByRole("listitem")).toHaveAttribute("data-edge", "pass");
  });

  it("shots planned before any renderer", () => {
    row(project({ job: job({ state: "done", stage: "planning", progress: 60 }) }));
    expect(screen.getByText("Shots planned")).toBeInTheDocument();
    expect(screen.getByText("No frames rendered yet")).toBeInTheDocument();
  });

  it("failed: the error verbatim, the title set in the script face", () => {
    const error = "This PDF has no text layer. It looks like a scan.";
    row(
      project({
        title: "saltpan-draft-3",
        pages: null,
        scenes: null,
        shots: null,
        job: job({ state: "failed", stage: "parsing", error }),
      }),
    );
    expect(screen.getByText("Couldn't read the script")).toBeInTheDocument();
    expect(screen.getByText(error)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "saltpan-draft-3" })).toHaveAttribute("data-script", "true");
    expect(screen.getByRole("listitem")).toHaveAttribute("data-edge", "withheld");
  });

  it("queued with nothing known: the upload time, and a meter at 0", () => {
    row(project({ pages: null, scenes: null, shots: null }));
    expect(screen.getByText("Queued")).toBeInTheDocument();
    expect(screen.getByText(/^Uploaded /)).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "0");
  });

  it("links its title to the storyboard (web.md §4.1a)", () => {
    row(project({ job: job({ state: "done" }) }));
    expect(screen.getByRole("link", { name: "The Keeper's Light" })).toHaveAttribute("href", "/projects/p1/storyboard");
  });

  it("a failed row is not a link", () => {
    row(project({ job: job({ state: "failed", stage: "parsing", error: "x" }) }));
    expect(screen.queryByRole("link")).toBeNull();
  });
});
