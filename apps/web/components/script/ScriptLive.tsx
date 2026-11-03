"use client";

// Keeps the script page live while its job runs (web.md §4.2, Live): polls the status every 2 s
// and re-renders the page from the server when the job's state or stage changes. Renders nothing.
// One poll in flight at a time; sign in on the second 401 in a row (web.md §4.0, T123).

import { useRouter } from "next/navigation";
import { useEffect, useRef } from "react";

import type { Job, ProjectSummary } from "@/lib/api/types";
import { unauthorizedStreak } from "@/lib/client/signed-out";

const POLL_MS = 2000;

export function ScriptLive({ id, job }: { id: string; job: Job }) {
  const router = useRouter();
  const seen = useRef(`${job.state}/${job.stage}`);
  const active = job.state === "queued" || job.state === "running";

  useEffect(() => {
    seen.current = `${job.state}/${job.stage}`;
  }, [job.state, job.stage]);

  useEffect(() => {
    if (!active) return;
    const streak = unauthorizedStreak();
    let busy = false;
    const timer = setInterval(async () => {
      if (busy) return;
      busy = true;
      try {
        const res = await fetch(`/api/projects/${encodeURIComponent(id)}/status`, { cache: "no-store" });
        if (streak.saw(res.status)) {
          router.push("/sign-in");
          return;
        }
        if (!res.ok) return;
        const { job: now } = (await res.json()) as ProjectSummary;
        const key = `${now.state}/${now.stage}`;
        if (key !== seen.current) {
          seen.current = key;
          router.refresh();
        }
      } catch {
        // The next tick tries again.
      } finally {
        busy = false;
      }
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [active, id, router]);

  return null;
}
