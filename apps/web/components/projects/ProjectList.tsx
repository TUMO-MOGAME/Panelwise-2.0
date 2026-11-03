// "Your screenplays" (web.md §4.1a): newest first, as the API orders them. From 861 px, where it
// sits beside the upload panel, the cards scroll on their own under a fixed heading (T125).

import type { ProjectSummary } from "@/lib/api/types";

import { ProjectRow } from "./ProjectRow";

// The bar (56 px), the page's top and bottom padding (pt-12, pb-16: 48 + 64 px) and the heading
// (about 46 px): 214 px, so 13.5rem (216 px) leaves the page itself no scroll.
// Padding inside keeps the last row's shadow and the scrollbar clear of the cards.
const SCROLLS = [
  "min-[861px]:max-h-[calc(100dvh-13.5rem)] min-[861px]:overflow-y-auto min-[861px]:overscroll-contain",
  "min-[861px]:pr-2 min-[861px]:pb-3 [scrollbar-color:var(--color-rule)_transparent] [scrollbar-width:thin]",
].join(" ");

export const EMPTY = "No screenplays yet. Upload one to board it.";
export const UNLOADED = "Your screenplays can't be loaded right now. Reload the page to try again.";

export function ProjectList({ projects }: { projects: ProjectSummary[] | null }) {
  return (
    <section aria-labelledby="list-title">
      <h2
        id="list-title"
        className="m-0 mb-3.5 border-b-2 border-ink pb-1.5 font-display text-[22px] leading-[1.1] font-extrabold tracking-[0.03em] uppercase"
      >
        Your screenplays
      </h2>
      {projects === null ? (
        <p className="m-0 text-sm text-ink-2">{UNLOADED}</p>
      ) : projects.length === 0 ? (
        <p className="m-0 text-sm text-ink-2">{EMPTY}</p>
      ) : (
        <ul aria-labelledby="list-title" tabIndex={0} className={`m-0 grid list-none gap-3.5 p-0 ${SCROLLS}`}>
          {projects.map((project) => (
            <ProjectRow key={project.id} project={project} />
          ))}
        </ul>
      )}
    </section>
  );
}
