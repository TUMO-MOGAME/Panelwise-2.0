// What a projects-list row says about its screenplay: web.md §4.1a, the ProjectRow table.

import type { ProjectSummary } from "@/lib/api/types";

export type Tone = "pending" | "pass" | "withheld";

export interface RowState {
  edge: "pencil" | "pass" | "withheld"; // the row's left edge colour token
  verdict: string;
  tone: Tone;
  detail: string | null; // the text beside the verdict
  meter: number | null; // 0–100, or no meter
  error: string | null; // job.error, verbatim, on its own line
}

const count = (n: number, one: string) => `${n} ${one}${n === 1 ? "" : "s"}`;

export function rowState(p: ProjectSummary): RowState {
  const { job, frames } = p;
  const pending = { edge: "pencil", tone: "pending", detail: null, error: null } as const;

  switch (job.state) {
    case "queued":
      return { ...pending, verdict: "Queued", meter: 0 };
    case "running":
      if (job.stage === "planning") return { ...pending, verdict: "Planning shots", meter: job.progress };
      if (job.stage === "rendering") {
        if (frames === null) return { ...pending, verdict: "Rendering frames", meter: job.progress };
        return {
          ...pending,
          verdict: "Rendering frames",
          detail: `${frames.settled} of ${frames.total} settled`,
          meter: frames.total > 0 ? (frames.settled / frames.total) * 100 : 0,
        };
      }
      // parsing, extracting, and a running job that hasn't named its stage yet
      return { ...pending, verdict: "Reading the script", meter: job.progress };
    case "done": {
      const done = { edge: "pass", tone: "pass", meter: null, error: null } as const;
      if (frames === null) return { ...done, verdict: "Shots planned", detail: "No frames rendered yet" };
      const withheld = frames.withheld > 0 ? ` · ${frames.withheld} withheld` : "";
      return { ...done, verdict: "Storyboard ready", detail: `${count(frames.total, "frame")}${withheld}` };
    }
    case "failed":
      return {
        edge: "withheld",
        verdict: job.stage === "rendering" ? "Couldn't render the frames" : "Couldn't read the script",
        tone: "withheld",
        detail: null,
        meter: null,
        error: job.error,
      };
  }
}

/** "2 pages · 3 scenes · 7 shots" from the counts known so far, else when it was uploaded. */
export function facts(p: ProjectSummary, uploadedAt: (iso: string) => string): string {
  const parts = [
    p.pages === null ? null : count(p.pages, "page"),
    p.scenes === null ? null : count(p.scenes, "scene"),
    p.shots === null ? null : count(p.shots, "shot"),
  ].filter((part) => part !== null);
  return parts.length > 0 ? parts.join(" · ") : `Uploaded ${uploadedAt(p.created_at)}`;
}

/** The list keeps polling while this is true for any row (web.md §4.1a). */
export function isActive(p: ProjectSummary): boolean {
  return p.job.state === "queued" || p.job.state === "running" || (p.frames?.active ?? 0) > 0;
}

/** "6 Oct, 09:14": en-GB in the viewer's time zone, so only ever called in the browser. */
export function uploadedAt(iso: string): string {
  const d = new Date(iso);
  const day = d.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
  const time = d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false });
  return `${day}, ${time}`;
}
