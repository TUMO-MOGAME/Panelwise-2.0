// The comic page by the project and its comic (web.md §4.5's page table; comic.png,
// comic-states.png).

import { FailedCard } from "@/components/script/FailedCard";
import { ScriptLive } from "@/components/script/ScriptLive";
import { JobStrip } from "@/components/shared/JobStrip";
import type { ComicView, Project } from "@/lib/api/types";

import { COMIC_COPY, comicState } from "./comic";
import { ComicReader } from "./ComicReader";
import { ComicStage, Heading, Note, PAGE } from "./ComicStage";

const jobKey = (view: ComicView) => `${view.job?.id ?? "none"}/${view.job?.state ?? ""}/${view.can_make}`;

const Why = ({ children }: { children: React.ReactNode }) => <p className="text-sm text-ink-2">{children}</p>;

export function ComicPage({ project, view }: { project: Project; view: ComicView | null }) {
  const state = comicState(project, view);
  if (state === "upload-failed") {
    return (
      <main className={PAGE}>
        <Heading title={project.title} />
        <FailedCard project={project} />
      </main>
    );
  }
  if (state === "plan-waiting" || state === "storyboard-running" || view === null) {
    // (view is null only before the plan: comicState says plan-waiting then)
    // The upload's job is still running: its strip, the note, and the script page's poll, which
    // re-renders this page when the job's stage changes.
    const waiting = state === "plan-waiting";
    return (
      <>
        {project.job.state !== "done" && <JobStrip job={project.job} frames={project.frames} />}
        <main className={PAGE}>
          <Heading title={project.title} />
          <Note>
            <p>{waiting ? COMIC_COPY.planWaiting : COMIC_COPY.storyboardRunning}</p>
            <Why>{waiting ? COMIC_COPY.planWaitingWhy : COMIC_COPY.storyboardRunningWhy}</Why>
          </Note>
        </main>
        <ScriptLive id={project.id} job={project.job} />
      </>
    );
  }
  if (state === "reader" && view.comic !== null) {
    return (
      // Keyed by what the server sent, so a refresh with a new job or comic starts them afresh.
      <ComicStage key={jobKey(view)} projectId={project.id} title={project.title} view={view}>
        <ComicReader key={view.comic.made_at} projectId={project.id} title={project.title} comic={view.comic} />
      </ComicStage>
    );
  }
  return <ComicStage key={jobKey(view)} projectId={project.id} title={project.title} view={view} />;
}
