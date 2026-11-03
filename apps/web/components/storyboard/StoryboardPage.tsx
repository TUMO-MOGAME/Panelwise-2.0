// The storyboard page by the state of the project's job (web.md §4.3's page table, §5;
// storyboard.png, storyboard-states.png).

import { FailedCard } from "@/components/script/FailedCard";
import { ScriptLive } from "@/components/script/ScriptLive";
import { JobStrip } from "@/components/shared/JobStrip";
import type { FrameView, LinesView, Project, ShotView } from "@/lib/api/types";

import { boardState } from "./board";
import { Storyboard } from "./Storyboard";

export type Board = { lines: LinesView; shots: ShotView[]; frames: FrameView[] };

export function StoryboardPage({ project, board }: { project: Project; board: Board | null }) {
  const state = boardState(project);
  if (state === "failed") {
    return (
      <main className="mx-auto max-w-[1440px] px-4 pt-5 pb-12 min-[641px]:px-6 min-[641px]:pt-8 min-[641px]:pb-16">
        <p className="m-0 font-display text-[13px] leading-none font-semibold tracking-[0.14em] text-ink-2 uppercase">
          Storyboard
        </p>
        <h1 className="mt-1.5 mb-2 font-display text-4xl leading-none font-extrabold tracking-[0.03em] uppercase min-[641px]:text-5xl">
          {project.title}
        </h1>
        <FailedCard project={project} />
      </main>
    );
  }
  if (state === "waiting" || board === null) {
    // Queued, reading or planning: the strip alone until the plan exists, refreshed when the
    // stage changes (the same poll as the script page's).
    return (
      <>
        <JobStrip job={project.job} frames={project.frames} />
        <ScriptLive id={project.id} job={project.job} />
      </>
    );
  }
  return <Storyboard project={project} lines={board.lines} shots={board.shots} frames={board.frames} />;
}
