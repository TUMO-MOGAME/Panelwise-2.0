// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Job } from "@/lib/api/types";

import { JobStrip, stageWords } from "./JobStrip";

const job = (over: Partial<Job> = {}): Job => ({
  id: "j1",
  state: "running",
  stage: "planning",
  progress: 40,
  error: null,
  updated_at: "2026-10-06T07:14:00Z",
  ...over,
});

describe("JobStrip (web.md §4.2, storyboard.png)", () => {
  it.each([
    [job({ state: "queued", stage: null }), "Queued"],
    [job({ stage: "parsing" }), "Reading the script"],
    [job({ stage: "extracting" }), "Reading the script"],
    [job({ stage: "planning" }), "Planning shots"],
    [job({ stage: "rendering" }), "Rendering frames"],
  ])("names the stage in words", (j, words) => {
    expect(stageWords(j)).toBe(words);
  });

  it("is a status region with the stage and a meter at the job's progress", () => {
    render(<JobStrip job={job()} frames={null} />);
    expect(screen.getByRole("status")).toHaveTextContent("Planning shots");
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "40");
  });

  it("while rendering with frames: settled of total, withheld, meter at settled ÷ total", () => {
    render(
      <JobStrip job={job({ stage: "rendering", progress: 90 })} frames={{ settled: 6, total: 7, withheld: 1, active: 1 }} />,
    );
    expect(screen.getByText("6 of 7 frames settled · 1 withheld")).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "86");
  });

  it("leaves the withheld part out at 0", () => {
    render(
      <JobStrip job={job({ stage: "rendering" })} frames={{ settled: 2, total: 7, withheld: 0, active: 1 }} />,
    );
    expect(screen.getByText("2 of 7 frames settled")).toBeInTheDocument();
  });
});
