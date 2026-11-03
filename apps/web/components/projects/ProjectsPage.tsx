"use client";

// The projects page's live part (web.md §4.1a): the upload panel beside the list, polling
// GET /api/projects every 2 s while any job is queued or running or any frame is active. One poll
// in flight at a time; sign in on the second 401 in a row, never the first (web.md §4.0, T123).

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import type { ProjectSummary } from "@/lib/api/types";
import { unauthorizedStreak } from "@/lib/client/signed-out";

import { ProjectList } from "./ProjectList";
import { isActive } from "./rowState";
import { UploadPanel } from "./UploadPanel";

const POLL_MS = 2000;

export function ProjectsPage({ initial }: { initial: ProjectSummary[] | null }) {
  const [projects, setProjects] = useState(initial);
  const router = useRouter();

  const polling = projects?.some(isActive) ?? false;
  useEffect(() => {
    if (!polling) return;
    const streak = unauthorizedStreak();
    let busy = false;
    const timer = setInterval(async () => {
      if (busy) return;
      busy = true;
      try {
        const res = await fetch("/api/projects", { cache: "no-store" });
        if (streak.saw(res.status)) {
          router.push("/sign-in");
          return;
        }
        if (!res.ok) throw new Error(`list answered ${res.status}`);
        setProjects((await res.json()) as ProjectSummary[]);
      } catch {
        // Keep the last list; the next tick tries again.
      } finally {
        busy = false;
      }
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [polling, router]);

  return (
    <main className="mx-auto grid max-w-[1100px] items-start gap-8 px-4 pt-7 pb-12 min-[861px]:grid-cols-2 min-[861px]:gap-12 min-[861px]:px-6 min-[861px]:pt-12 min-[861px]:pb-16">
      <UploadPanel />
      <ProjectList projects={projects} />
    </main>
  );
}
