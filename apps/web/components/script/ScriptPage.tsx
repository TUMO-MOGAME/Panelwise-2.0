// The script page (web.md §4.2, §5; script.png, script-states.png): what was read from the
// screenplay, each thing with the line it came from, by the state of the project's job.

import { JobStrip } from "@/components/shared/JobStrip";
import type { Project } from "@/lib/api/types";

import { entitySections } from "./entities";
import { EntitySection } from "./EntitySection";
import { FailedCard } from "./FailedCard";
import { pageState } from "./pageState";
import { ReportPanel } from "./ReportPanel";
import { SceneIndex } from "./SceneIndex";
import { ScriptLive } from "./ScriptLive";

const count = (n: number, one: string) => `${n} ${one}${n === 1 ? "" : "s"}`;

function Intro({ project, facts }: { project: Project; facts: boolean }) {
  const parts = [
    project.pages === null ? null : count(project.pages, "page"),
    project.scenes === null ? null : count(project.scenes, "scene"),
    "every name below quotes the line it came from",
  ].filter((part) => part !== null);
  return (
    <section data-area="intro" className="[grid-area:intro]">
      <p className="m-0 font-display text-[13px] leading-none font-semibold tracking-[0.14em] text-ink-2 uppercase">
        Read from the script
      </p>
      <h1 className="mt-1.5 mb-2 font-display text-4xl leading-none font-extrabold tracking-[0.03em] uppercase min-[641px]:text-5xl">
        {project.title}
      </h1>
      {facts && <p className="m-0 text-ink-2">{parts.join(" · ")}</p>}
    </section>
  );
}

const padding = "mx-auto max-w-[1440px] px-4 pt-5 pb-12 min-[641px]:px-6 min-[641px]:pt-8 min-[641px]:pb-16";

export function ScriptPage({ project }: { project: Project }) {
  const state = pageState(project);
  const live = <ScriptLive id={project.id} job={project.job} />;

  if (state === "failed") {
    return (
      <main className={`${padding} min-[1101px]:pl-[324px]`}>
        <Intro project={project} facts={false} />
        <FailedCard project={project} />
      </main>
    );
  }
  if (state === "waiting") {
    return (
      <>
        <JobStrip job={project.job} frames={project.frames} />
        {live}
      </>
    );
  }
  return (
    <>
      {state === "live" && <JobStrip job={project.job} frames={project.frames} />}
      {state === "live" && live}
      <main
        className={`${padding} grid items-start gap-x-10 gap-y-8 [grid-template-areas:'intro'_'report'_'entities'_'scenes'] min-[1101px]:grid-cols-[260px_minmax(0,1fr)_300px] min-[1101px]:[grid-template-areas:'scenes_intro_report'_'scenes_entities_report']`}
      >
        <Intro project={project} facts />
        {project.report && <ReportPanel report={project.report} />}
        <section aria-label="What was found" data-area="entities" className="[grid-area:entities]">
          {entitySections(project.entities ?? []).map((section) => (
            <EntitySection key={section.kind} section={section} scenes={project.scene_list ?? []} />
          ))}
        </section>
        <SceneIndex scenes={project.scene_list ?? []} storyboard={`/projects/${project.id}/storyboard`} />
      </main>
    </>
  );
}
