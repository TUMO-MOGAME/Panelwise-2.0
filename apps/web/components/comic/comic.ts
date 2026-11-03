// The comic page's rules outside its components (web.md §4.5): which screen a project gets, the
// words for each lettering, where a hit area sits on the page, and the page number in the URL.

import { spanText } from "@/components/shared/SpanRef";
import type { ComicPageView, ComicView, Job, LetteringKind, LetteringView, Project } from "@/lib/api/types";

/** web.md §4.5's copy, verbatim. */
export const COMIC_COPY = {
  eyebrow: "Comic",
  planWaiting: "The comic is made from the shot plan, which isn't ready yet.",
  planWaitingWhy: "This page updates when planning finishes.",
  storyboardRunning: "The comic can be made once the storyboard is finished.",
  storyboardRunningWhy: "This page updates when it is.",
  none: "No comic yet.",
  explain: (shots: number) =>
    `Making one draws each of the ${shots} shots again at its panel's size, audits every drawing against the script, and letters the panels with the script's own dialogue.`,
  noRenderer: "Drawing isn't set up on this server yet, so a comic can't be made here.",
  making: "Drawing and auditing the panels. The pages appear here when the comic is done.",
  strip: (progress: number) => `Making the comic · ${progress}%`,
  reuse: "Panels the audit already accepted are reused when you make it again.",
  make: "Make the comic",
  makeAgain: "Make the comic again",
  starting: "Starting…",
  startFailed: "The comic couldn't be started. Try again.",
  budgetSpent: "The demo has used this month's model budget.", // T069
  imagesSpent: "The demo has drawn this month's budget of frames.", // T030
  download: "Download PDF",
  traced: "From the script",
  traceEmpty: "Select any bubble or caption to see the script line it comes from.",
  lettering: "Lettering on this page",
  previous: "← Previous",
  next: "Next →",
  pageFailed: "This page couldn't be loaded. Reload to try again.",
} as const;

/**
 * upload-failed: the script page's failed card · plan-waiting: no plan yet · storyboard-running:
 * planned, the upload's job still running · none / making / failed: no comic yet, by the comic
 * job · reader: a comic exists (with the strip or failed note above it when a later job runs).
 */
export type ComicState = "upload-failed" | "plan-waiting" | "storyboard-running" | "none" | "making" | "failed" | "reader";

const running = (job: Job | null) => job !== null && (job.state === "queued" || job.state === "running");

export function comicState(project: Project, view: ComicView | null): ComicState {
  if (project.job.state === "failed") return "upload-failed";
  if (project.shots === null || view === null) return "plan-waiting";
  if (view.comic !== null) return "reader";
  if (project.job.state !== "done") return "storyboard-running";
  if (running(view.job)) return "making";
  if (view.job?.state === "failed") return "failed";
  return "none";
}

/** Poll the comic view while this is true (web.md §4.5). */
export const isMaking = (view: ComicView) => running(view.job);

/** The list's label and the hit area's: who speaks, or "Scene". */
export function whoWords(item: LetteringView): string {
  switch (item.kind) {
    case "scene":
      return "Scene";
    case "off_panel":
      return `${item.speaker ?? ""} · off panel`;
    case "voice_over":
      return `${item.speaker ?? ""} · voice-over`;
    default:
      return item.speaker ?? "";
  }
}

const KIND_WORDS: Record<LetteringKind, string> = {
  speech: "speech",
  off_panel: "off panel",
  voice_over: "voice-over",
  scene: "scene heading",
};

export const kindWord = (kind: LetteringKind) => KIND_WORDS[kind];

/** The traced card's facts: "p.2 l.93–94 · off panel · shot 1.3". */
export const factsLine = (item: LetteringView, shotId: string) =>
  `${spanText(item.span)} · ${kindWord(item.kind)} · shot ${shotId}`;

/** A hit area's label: "MOKGOSI · off panel: Is that my good shirt you are flying? (p.2 l.93–94)". */
export const hitLabel = (item: LetteringView) => `${whoWords(item)}: ${item.text} (${spanText(item.span)})`;

/** A rect as percentages of its page, so the hit areas scale with the image. */
export function placed(rect: readonly [number, number, number, number], page: Pick<ComicPageView, "width" | "height">) {
  const [x, y, w, h] = rect;
  const pct = (v: number, of: number) => `${(v / of) * 100}%`;
  return { left: pct(x, page.width), top: pct(y, page.height), width: pct(w, page.width), height: pct(h, page.height) };
}

/** `?page=` as a 1-based page of `count`; anything else is page 1 (and is replaced in the URL). */
export function parsePage(raw: string | null, count: number): number {
  if (raw === null || !/^\d+$/.test(raw)) return 1;
  const n = Number(raw);
  return n >= 1 && n <= count ? n : 1;
}

/** A selection: the k-th lettering of the p-th panel on the page. */
export type Selected = { panel: number; item: number };
export const sameSelection = (a: Selected | null, b: Selected) => a !== null && a.panel === b.panel && a.item === b.item;
