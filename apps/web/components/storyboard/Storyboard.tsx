"use client";

// The board of a planned project (web.md §4.3): the lined script beside the frames, linked both
// ways, kept live while the job runs or a frame is still rendering or auditing.

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { JobStrip } from "@/components/shared/JobStrip";
import type { FrameView, LinesView, Project, ProjectSummary, ShotView } from "@/lib/api/types";
import { unauthorizedStreak } from "@/lib/client/signed-out";

import { isLive, mergeFrames, retryable, stageKey } from "./board";
import { FrameBoard } from "./FrameBoard";
import { FrameSheet } from "./FrameSheet";
import { RetryButton } from "./RetryButton";
import { scriptPages } from "./lined";
import { LinedScript } from "./LinedScript";

const POLL_MS = 2000;

const cardLink = (id: string) => document.querySelector<HTMLElement>(`[data-card-link="${CSS.escape(id)}"]`);

export function Storyboard({
  project,
  lines,
  shots,
  frames: initialFrames,
}: {
  project: Project;
  lines: LinesView;
  shots: ShotView[];
  frames: FrameView[];
}) {
  const router = useRouter();
  const pathname = usePathname();
  // `?shot=` is the sheet's only state (web.md §4.4): an id that names no shot opens nothing.
  const open = useSearchParams().get("shot");
  // The poll reads the router through a ref, so a new router object never restarts it mid-flight.
  const routerRef = useRef(router);
  useEffect(() => {
    routerRef.current = router;
  }, [router]);
  const [summary, setSummary] = useState<ProjectSummary>(project);
  const [frames, setFrames] = useState(initialFrames);
  const [highlight, setHighlight] = useState<string | null>(null);
  const seen = useRef(stageKey(project));

  // A refresh from the server brings new props: they replace what the poll had (React's
  // "adjusting state when a prop changes", during render rather than in an effect).
  const [props, setProps] = useState({ project, initialFrames });
  if (props.project !== project || props.initialFrames !== initialFrames) {
    setProps({ project, initialFrames });
    setSummary(project);
    setFrames((old) => mergeFrames(old, initialFrames));
  }
  useEffect(() => {
    seen.current = stageKey(project);
  }, [project]);

  // Live while the job runs, a frame is active by the last status, or one just started here (a
  // retry's 202 arrives before the next status says so).
  const live = isLive(summary) || frames.some((f) => f.state === "rendering" || f.state === "auditing");
  useEffect(() => {
    if (!live) return;
    const base = `/api/projects/${encodeURIComponent(project.id)}`;
    // One round trip at a time, cancelled on cleanup, so a slow answer never lands over a newer
    // one, after the refresh, or after the page has gone.
    const abort = new AbortController();
    const init = { cache: "no-store", signal: abort.signal } as const;
    // Sign in on the second 401 in a row, never the first (web.md §4.0, T123).
    const streak = unauthorizedStreak();
    let busy = false;
    const timer = setInterval(async () => {
      if (busy) return;
      busy = true;
      try {
        const res = await fetch(`${base}/status`, init);
        if (streak.saw(res.status)) {
          routerRef.current.push("/sign-in");
          return;
        }
        if (!res.ok) return;
        const now = (await res.json()) as ProjectSummary;
        if (stageKey(now) !== seen.current) {
          seen.current = stageKey(now);
          routerRef.current.refresh();
          return;
        }
        setSummary(now);
        // Every tick while frames are set: rendering → auditing, or a next attempt, moves no count.
        if (now.frames === null) return;
        const got = await fetch(`${base}/frames`, init);
        if (!got.ok) return; // the next tick asks again
        const fresh = (await got.json()) as FrameView[];
        setFrames((old) => mergeFrames(old, fresh));
      } catch {
        // The next tick tries again (or the effect was cleaned up and aborted the request).
      } finally {
        busy = false;
      }
    }, POLL_MS);
    return () => {
      clearInterval(timer);
      abort.abort();
    };
  }, [live, project.id]);

  // A shot line was clicked: its card scrolls into view and its link takes focus (which
  // highlights it).
  const pick = useCallback((id: string) => {
    const card = document.getElementById(`shot-${id}`);
    const still = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    card?.scrollIntoView({ block: "nearest", behavior: still ? "auto" : "smooth" });
    cardLink(id)?.focus({ preventScroll: true });
  }, []);

  const refetchFrames = useCallback(async () => {
    try {
      const res = await fetch(`/api/projects/${encodeURIComponent(project.id)}/frames`, { cache: "no-store" });
      if (res.ok) {
        const fresh = (await res.json()) as FrameView[];
        setFrames((old) => mergeFrames(old, fresh));
      }
    } catch {
      // The board keeps what it has; the next poll, if live, catches up.
    }
  }, [project.id]);
  const retryFor = useCallback(
    (shot: ShotView) => (
      <RetryButton
        projectId={project.id}
        sceneIndex={shot.scene_index}
        number={shot.number}
        onStarted={(frame) => setFrames((old) => old.map((f) => (f.shot_id === frame.shot_id ? frame : f)))}
        onMoved={() => void refetchFrames()}
      />
    ),
    [project.id, refetchFrames],
  );
  const hrefFor = useCallback((id: string) => `${pathname}?shot=${encodeURIComponent(id)}`, [pathname]);
  const k = shots.findIndex((s) => s.id === open);
  const sheetShot = k >= 0 ? shots[k] : null;
  // Opened from a card, the sheet closes by going back (no duplicate page in the history);
  // opened from a loaded or followed ?shot= link, by replacing the URL (web.md §4.4, Closing).
  // The id of the last card push, not a one-shot flag, so Back and Forward over that history entry
  // still close it with back(); a reload forgets it.
  const pushed = useRef<string | null>(null);
  const close = useCallback(() => {
    if (open !== null && open === pushed.current) router.back();
    else router.replace(pathname, { scroll: false });
  }, [router, pathname, open]);
  // A loaded ?shot= brings its card into view behind the sheet, so closing lands on it.
  useEffect(() => {
    if (open && open !== pushed.current) document.getElementById(`shot-${open}`)?.scrollIntoView({ block: "center" });
  }, [open]);

  return (
    <>
      {live && <JobStrip job={summary.job} frames={summary.frames} />}
      <main className="mx-auto grid max-w-[1600px] items-start gap-8 px-4 pt-5 pb-12 min-[641px]:px-6 min-[641px]:pt-7 min-[641px]:pb-16 min-[1101px]:grid-cols-[minmax(520px,680px)_minmax(0,1fr)]">
        <LinedScript pages={scriptPages(lines)} shots={shots} highlight={highlight} onPick={pick} />
        <FrameBoard
          scenes={project.scene_list ?? []}
          shots={shots}
          frames={frames}
          highlight={highlight}
          onHighlight={setHighlight}
          hrefFor={hrefFor}
          retryFor={retryFor}
          onOpen={(id) => (pushed.current = id)}
        />
      </main>
      {sheetShot && (
        <FrameSheet
          key={sheetShot.id}
          shot={sheetShot}
          k={k}
          frame={frames.find((f) => f.shot_id === sheetShot.id)}
          scene={project.scene_list?.find((s) => s.index === sheetShot.scene_index)}
          onClose={close}
          onCloseFocus={() => cardLink(sheetShot.id)?.focus()}
          retry={retryable(frames.find((f) => f.shot_id === sheetShot.id)?.state) ? retryFor(sheetShot) : null}
        />
      )}
    </>
  );
}
