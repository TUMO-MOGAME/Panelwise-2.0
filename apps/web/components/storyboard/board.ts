// The storyboard page's rules outside its components (web.md §4.3): which page a project gets,
// when it stays live, and how a fresh frames list replaces the one on screen.

import type { FrameView, Project, ProjectSummary } from "@/lib/api/types";

/**
 * waiting: queued, reading or planning, the job strip alone · live: the board while the job runs
 * or a frame is still active · ready: the board · failed: the failed card.
 */
export type BoardState = "waiting" | "live" | "ready" | "failed";

const running = (s: ProjectSummary) => s.job.state === "queued" || s.job.state === "running";
export const isLive = (s: ProjectSummary) => running(s) || (s.frames?.active ?? 0) > 0;

/** "Try another render" is offered on a withheld frame and, since T066, a failed one (web.md §4.3). */
export const retryable = (state: FrameView["state"] | undefined) => state === "withheld" || state === "failed";

/** Export PDF's rule (web.md §4.3; T027): the job done and every frame settled, none active. */
export const canExport = (s: ProjectSummary) =>
  s.job.state === "done" && s.frames !== null && s.frames.active === 0 && s.frames.settled === s.frames.total;

export function boardState(p: Project): BoardState {
  if (p.job.state === "failed") return "failed";
  if (p.shots === null) return "waiting";
  return isLive(p) ? "live" : "ready";
}

/**
 * The fresh list, except that a frame whose state and attempt haven't changed keeps the image URL
 * it has: a newly signed URL for the same image would only reload it (web.md §4.3).
 */
export function mergeFrames(old: readonly FrameView[], fresh: readonly FrameView[]): FrameView[] {
  const before = new Map(old.map((f) => [f.shot_id, f]));
  return fresh.map((f) => {
    const was = before.get(f.shot_id);
    return was && was.state === f.state && was.attempt === f.attempt && was.image_url && f.image_url
      ? { ...f, image_url: was.image_url }
      : f;
  });
}

export const stageKey = (s: ProjectSummary) => `${s.job.state}/${s.job.stage}`;
