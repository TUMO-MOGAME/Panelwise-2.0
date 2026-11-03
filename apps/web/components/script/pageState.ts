// Which script page a project gets (web.md §4.2's table, §5).

import type { Project } from "@/lib/api/types";

/**
 * waiting: queued or still reading, the job strip alone · live: read, the job still running ·
 * ready: done · failed: the failed card.
 */
export type ScriptPageState = "waiting" | "live" | "ready" | "failed";

export function pageState(p: Project): ScriptPageState {
  if (p.job.state === "failed") return "failed";
  if (p.entities === null) return "waiting";
  return p.job.state === "done" ? "ready" : "live";
}
