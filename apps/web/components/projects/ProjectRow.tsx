"use client";

// One screenplay in the list (web.md §4.1a; projects.png, projects-states.png). The title opens
// its storyboard.

import Link from "next/link";
import { useSyncExternalStore } from "react";

import { Meter } from "@/components/shared/Meter";
import { Verdict } from "@/components/shared/Verdict";
import type { ProjectSummary } from "@/lib/api/types";
import { cn } from "@/lib/utils";

import { facts, rowState, uploadedAt } from "./rowState";

const edges = { pencil: "border-pencil", pass: "border-pass", withheld: "border-withheld" } as const;

const noop = () => () => {};

/** The upload time is in the viewer's time zone, so it is written only once in the browser. */
function useInBrowser(): boolean {
  return useSyncExternalStore(
    noop,
    () => true,
    () => false,
  );
}

export function ProjectRow({ project }: { project: ProjectSummary }) {
  const state = rowState(project);
  const inBrowser = useInBrowser();
  const failed = project.job.state === "failed";
  return (
    <li data-edge={state.edge} className={cn("border-l-4 bg-paper px-[18px] py-4 shadow-page", edges[state.edge])}>
      <h3
        data-script={failed || undefined}
        className={cn(
          "m-0",
          failed
            ? "font-script text-base font-bold"
            : "font-display text-2xl leading-[1.1] font-extrabold tracking-[0.02em] uppercase",
        )}
      >
        {failed ? (
          project.title
        ) : (
          <Link href={`/projects/${project.id}/storyboard`} className="text-inherit no-underline hover:text-pencil">
            {project.title}
          </Link>
        )}
      </h3>
      <p className="mt-1 mb-0 text-sm text-ink-2">{facts(project, (iso) => (inBrowser ? uploadedAt(iso) : ""))}</p>
      <p className="mt-2.5 mb-0 flex items-center gap-2.5 text-sm">
        <Verdict tone={state.tone}>{state.verdict}</Verdict>
        {state.detail && <span>{state.detail}</span>}
      </p>
      {state.meter !== null && <Meter value={state.meter} label={state.verdict} />}
      {state.error && <p className="mt-2 mb-0 text-sm">{state.error}</p>}
    </li>
  );
}
