// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ProjectSummary } from "@/lib/api/types";

import { EMPTY, ProjectList, UNLOADED } from "./ProjectList";

const project = (id: string): ProjectSummary => ({
  id,
  title: `Script ${id}`,
  created_at: "2026-10-06T07:14:00Z",
  pages: 4,
  scenes: 5,
  shots: 18,
  frames: { settled: 18, total: 18, withheld: 0, active: 0 },
  job: {
    id: `j${id}`,
    state: "done",
    stage: "rendering",
    progress: 100,
    error: null,
    updated_at: "2026-10-06T07:20:00Z",
  },
});

describe("ProjectList scrolls on its own (web.md §4.1a, T125)", () => {
  it("the cards are one scroll area, reachable by keyboard and named by the heading", () => {
    render(<ProjectList projects={[project("a"), project("b"), project("c")]} />);
    const area = screen.getByRole("list", { name: "Your screenplays" });
    expect(area).toHaveAttribute("tabindex", "0");
    expect(area.querySelectorAll("li")).toHaveLength(3);
  });

  it("from 861 px only: a bounded height that scrolls and keeps the scroll to itself", () => {
    render(<ProjectList projects={[project("a")]} />);
    const classes = screen.getByRole("list", { name: "Your screenplays" }).className.split(/\s+/);
    for (const rule of [
      "min-[861px]:max-h-[calc(100dvh-13.5rem)]",
      "min-[861px]:overflow-y-auto",
      "min-[861px]:overscroll-contain",
    ]) {
      expect(classes).toContain(rule);
    }
    // Below 861 px the page scrolls: no unprefixed height cap or overflow.
    expect(classes.some((c) => /^(max-h-|overflow-y-|overscroll-)/.test(c))).toBe(false);
  });

  it.each([
    ["empty", [], EMPTY],
    ["unavailable", null, UNLOADED],
  ] as const)("%s: the message, and no scroll area", (_, projects, message) => {
    render(<ProjectList projects={projects as ProjectSummary[] | null} />);
    expect(screen.getByText(message)).toBeInTheDocument();
    expect(screen.queryByRole("list")).toBeNull();
  });
});
