"use client";

// The comic page around its comic job (web.md §4.5; comic-states.png): the making strip, the
// heading and the notes with "Make the comic" when there is no comic yet; above a comic (a remake
// started elsewhere, §10) only the strip or the failed note, never the button. One component owns
// the job, so the strip appears the moment Make the comic answers. Polls the comic view every 2 s
// while a comic job runs, moving the strip, and re-renders the page when the job settles.
// One poll in flight at a time; sign in on the second 401, never the first (web.md §4.0, T123).

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { Meter } from "@/components/shared/Meter";
import { Button } from "@/components/ui/button";
import type { ComicView, Job } from "@/lib/api/types";
import { fetchPast401, unauthorizedStreak } from "@/lib/client/signed-out";
import { cn } from "@/lib/utils";

import { COMIC_COPY } from "./comic";

const POLL_MS = 2000;
const active = (job: Job | null) => job !== null && (job.state === "queued" || job.state === "running");

export function Note({ children, failed = false }: { children: React.ReactNode; failed?: boolean }) {
  return (
    <div
      className={cn(
        "mt-5 max-w-[640px] border-l-4 bg-paper px-5 py-[18px] shadow-page [&>p]:mt-0 [&>p]:mb-2.5 [&>p:last-child]:mb-0",
        failed ? "border-withheld" : "border-rule",
      )}
    >
      {children}
    </div>
  );
}

const Why = ({ children }: { children: React.ReactNode }) => <p className="text-sm text-ink-2">{children}</p>;

export function MakingStrip({ progress }: { progress: number }) {
  const words = COMIC_COPY.strip(progress);
  return (
    <div
      role="status"
      className="flex flex-wrap items-center gap-4 border-b border-rule bg-paper px-4 py-2.5 text-sm text-ink-2 min-[641px]:flex-nowrap min-[641px]:px-6"
    >
      <span>{words}</span>
      <span className="order-3 basis-full min-[641px]:order-none min-[641px]:basis-[220px] min-[641px]:shrink-0">
        <Meter value={progress} label="Making the comic" className="mt-0" />
      </span>
    </div>
  );
}

export function Heading({ title }: { title: string }) {
  return (
    <>
      <p className="m-0 font-display text-[13px] leading-none font-semibold tracking-[0.14em] text-ink-2 uppercase">
        {COMIC_COPY.eyebrow}
      </p>
      <h1 className="mt-1.5 mb-2 font-display text-4xl leading-none font-extrabold tracking-[0.03em] uppercase min-[641px]:text-5xl">
        {title}
      </h1>
    </>
  );
}

export const PAGE = "mx-auto max-w-[1440px] px-4 pt-5 pb-12 min-[641px]:px-6 min-[641px]:pt-8 min-[641px]:pb-16";

export function ComicStage({
  projectId,
  title,
  view,
  children,
}: {
  projectId: string;
  title: string;
  view: ComicView;
  /** The reader, when a comic exists: no notes about making one, no button. */
  children?: React.ReactNode;
}) {
  const hasComic = children !== undefined;
  const router = useRouter();
  const [job, setJob] = useState<Job | null>(view.job);
  const [canMake, setCanMake] = useState(view.can_make);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const seen = useRef(view.job?.state ?? null);
  const making = active(job);
  const base = `/api/projects/${encodeURIComponent(projectId)}/comic`;

  useEffect(() => {
    if (!making) return;
    const streak = unauthorizedStreak();
    let busy = false;
    const timer = setInterval(async () => {
      if (busy) return;
      busy = true;
      try {
        const res = await fetch(base, { cache: "no-store" });
        if (streak.saw(res.status)) {
          router.push("/sign-in");
          return;
        }
        if (!res.ok) return;
        const now = (await res.json()) as ComicView;
        const state = now.job?.state ?? null;
        // A finished job keeps the strip until the refreshed page (with its comic) arrives: never
        // a moment of "No comic yet" with Make the comic pressable.
        if (state !== "done") setJob(now.job);
        if (state !== seen.current) {
          seen.current = state;
          router.refresh();
        }
      } catch {
        // The next tick tries again.
      } finally {
        busy = false;
      }
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [making, base, router]);

  async function make() {
    setSending(true);
    setError(null);
    try {
      const res = await fetchPast401(base, { method: "POST" });
      if (res.status === 202) {
        const body = (await res.json().catch(() => null)) as { job?: Job } | null;
        if (body?.job) {
          seen.current = body.job.state;
          setJob(body.job);
        } else router.refresh();
        return;
      }
      if (res.status === 401) {
        router.push("/sign-in");
        return;
      }
      if (res.status === 409) {
        router.refresh();
        return;
      }
      const body = (await res.json().catch(() => null)) as { error?: string } | null;
      if (res.status === 503 && body?.error === "renderer_unavailable") setCanMake(false);
      else if (res.status === 429 && body?.error === "llm_budget_spent") setError(COMIC_COPY.budgetSpent);
      else if (res.status === 429 && body?.error === "image_budget_spent") setError(COMIC_COPY.imagesSpent);
      else setError(COMIC_COPY.startFailed);
    } catch {
      setError(COMIC_COPY.startFailed);
    } finally {
      setSending(false);
    }
  }

  const button = (label: string) => (
    <>
      {!canMake && <Why>{COMIC_COPY.noRenderer}</Why>}
      <Button className="mt-1.5" disabled={!canMake || sending} onClick={() => void make()}>
        {sending ? COMIC_COPY.starting : label}
      </Button>
      {error && (
        <p role="alert" className="mt-2 text-[13px] text-withheld">
          {error}
        </p>
      )}
    </>
  );

  const failed = job?.state === "failed" && (
    <Note failed>
      <p>{job.error}</p>
      <Why>{COMIC_COPY.reuse}</Why>
      {!hasComic && button(COMIC_COPY.makeAgain)}
    </Note>
  );
  const strip = making && job && <MakingStrip progress={job.progress} />;

  if (hasComic) {
    return (
      <>
        {strip}
        {failed && <div className="mx-auto max-w-[1440px] px-4 min-[641px]:px-6">{failed}</div>}
        {children}
      </>
    );
  }
  return (
    <>
      {strip}
      <main className={PAGE}>
        <Heading title={title} />
        {making ? (
          <Note>
            <p>{COMIC_COPY.making}</p>
          </Note>
        ) : (
          failed || (
            <Note>
              <p>{COMIC_COPY.none}</p>
              <Why>{COMIC_COPY.explain(view.shots)}</Why>
              {button(COMIC_COPY.make)}
            </Note>
          )
        )}
      </main>
    </>
  );
}
