// The app bar (web.md §6 component tree; tokens.css `.bar`): wordmark, the project's title and
// tabs on a project's pages, who is signed in, and the page's actions.

import Link from "next/link";

import { cn } from "@/lib/utils";

export function Wordmark({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "font-display text-[22px] leading-none font-extrabold tracking-[0.06em] text-white uppercase",
        className,
      )}
    >
      Panel<span className="text-line-1">wise</span>
    </span>
  );
}

export type ProjectTab = "script" | "storyboard" | "comic";

function ProjectTabs({ id, tab }: { id: string; tab?: ProjectTab }) {
  const item = "rounded-paper px-3 py-1.5 font-body text-[13px] font-bold tracking-[0.02em] no-underline";
  const link = (key: ProjectTab, label: string) => (
    <Link
      href={`/projects/${id}/${key}`}
      aria-current={tab === key ? "page" : undefined}
      className={cn(item, tab === key ? "bg-bar-current text-white" : "text-bar-muted")}
    >
      {label}
    </Link>
  );
  return (
    <nav aria-label="Project" className="order-5 -ml-3 flex w-full gap-1 min-[641px]:order-none min-[641px]:ml-2 min-[641px]:w-auto">
      {link("script", "Script")}
      {link("storyboard", "Storyboard")}
      {link("comic", "Comic")}
    </nav>
  );
}

export function AppBar({
  email,
  project,
  tab,
  actions,
  tools,
}: {
  email: string | null;
  project?: { id: string; title: string };
  tab?: ProjectTab;
  actions?: React.ReactNode;
  /** The page's own tools, left of who is signed in (storyboard.png's Export PDF). */
  tools?: React.ReactNode;
}) {
  return (
    <header
      className={cn(
        "flex flex-wrap items-center gap-3 bg-ink px-4 pt-3 pb-2 text-bar-text",
        "min-[641px]:h-14 min-[641px]:flex-nowrap min-[641px]:gap-6 min-[641px]:px-6 min-[641px]:py-0",
      )}
    >
      <Link href="/projects" aria-label="Panelwise" className="no-underline">
        <Wordmark />
      </Link>
      {project && (
        <span className="hidden font-body text-sm font-medium text-bar-muted min-[641px]:inline">{project.title}</span>
      )}
      {project && <ProjectTabs id={project.id} tab={tab} />}
      <span className="flex-1" />
      {tools}
      {email && <span className="hidden text-[13px] text-bar-muted min-[641px]:inline">{email}</span>}
      {actions}
    </header>
  );
}
