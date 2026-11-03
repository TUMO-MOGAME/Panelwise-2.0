// The job strip under the bar while a job runs (web.md §4.2; storyboard.css `.job`).

import type { Job, ProjectSummary } from "@/lib/api/types";

import { Meter } from "./Meter";

export function stageWords(job: Job): string {
  if (job.state === "queued") return "Queued";
  switch (job.stage) {
    case "planning":
      return "Planning shots";
    case "rendering":
      return "Rendering frames";
    default:
      // parsing, extracting, and a running job that hasn't named its stage yet
      return "Reading the script";
  }
}

export function JobStrip({ job, frames }: { job: Job; frames: ProjectSummary["frames"] }) {
  const words = stageWords(job);
  const counting = job.stage === "rendering" && frames !== null;
  const value = counting && frames.total > 0 ? (frames.settled / frames.total) * 100 : job.progress;
  return (
    <div
      role="status"
      className="flex flex-wrap items-center gap-4 border-b border-rule bg-paper px-4 py-2.5 text-sm text-ink-2 min-[641px]:flex-nowrap min-[641px]:px-6"
    >
      <span className="font-display text-[13px] leading-none font-semibold tracking-[0.14em] uppercase">{words}</span>
      <span className="order-3 basis-full min-[641px]:order-none min-[641px]:basis-[220px] min-[641px]:shrink-0">
        <Meter value={value} label={words} className="mt-0" />
      </span>
      {counting && (
        <span>
          {frames.settled} of {frames.total} frames settled
          {frames.withheld > 0 && ` · ${frames.withheld} withheld`}
        </span>
      )}
    </div>
  );
}
