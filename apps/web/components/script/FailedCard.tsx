// A project whose job failed (web.md §4.2, script-states.png): the row's verdict, the error
// verbatim, the stage it stopped at, and the way back.

import Link from "next/link";

import { rowState } from "@/components/projects/rowState";
import { stageWords } from "@/components/shared/JobStrip";
import { Verdict } from "@/components/shared/Verdict";
import { Button } from "@/components/ui/button";
import type { ProjectSummary } from "@/lib/api/types";

export function FailedCard({ project }: { project: ProjectSummary }) {
  const { verdict, error } = rowState(project);
  const stage = project.job.stage === null ? null : stageWords(project.job).toLowerCase();
  return (
    <section aria-label="This run failed" className="mt-6 max-w-[640px] border-l-4 border-withheld bg-paper px-5 py-[18px] shadow-page">
      <Verdict tone="withheld">{verdict}</Verdict>
      {error && <p className="mt-2.5 mb-0">{error}</p>}
      {stage && <p className="mt-2.5 mb-0 text-sm text-ink-2">It stopped while {stage}.</p>}
      <Button asChild variant="quiet" className="mt-4">
        <Link href="/projects">Back to your screenplays</Link>
      </Button>
    </section>
  );
}
