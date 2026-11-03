// One shot's card on the board (web.md §4.3; storyboard.css `.card`): its frame or the frame's
// state, the shot id and camera, the verdict, who is in it, and its verbatim source and span.

import Link from "next/link";
import type { Dispatch, ReactNode, SetStateAction } from "react";

import { SpanRef } from "@/components/shared/SpanRef";
import { Verdict } from "@/components/shared/Verdict";
import type { FrameView, ShotView } from "@/lib/api/types";
import { cn } from "@/lib/utils";

import { cameraText, cardState, whoText } from "./cards";
import { FrameMedia, MEDIA_BOX, SourceText } from "./FrameMedia";
import { lineColour } from "./lined";

/** No image yet: the hatched panel, with the pencil dots while a render or audit runs. */
export function PendingMedia({ text, busy }: { text: string; busy: boolean }) {
  return (
    <div className={MEDIA_BOX}>
      <div className="grid h-full place-content-center justify-items-center gap-2.5 bg-[repeating-linear-gradient(135deg,#f1f3f1_0_10px,#e9ecea_10px_20px)] text-sm text-ink-2">
        {busy && (
          <span
            aria-hidden
            className="h-2 w-11 animate-pulse bg-[radial-gradient(circle,var(--color-pencil)_3px,transparent_3.5px)] bg-size-[14px_8px] bg-repeat-x"
          />
        )}
        <p className="m-0">{text}</p>
      </div>
    </div>
  );
}

/** A frame that won't be shown: the source once, its span, why, and the retry. */
function TextCard({ shot, why, action }: { shot: ShotView; why: string; action?: ReactNode }) {
  // 16:9 at least, but it grows rather than clip: a long source, the button or its error must show.
  return (
    <div data-text-card className="flex aspect-video flex-col border-b border-rule bg-[#f1f3f1]">
      <div className="flex grow flex-col gap-1.5 border border-b-0 border-dashed border-withheld bg-paper px-4.5 py-4">
        <p className="m-0">
          <SourceText shot={shot} />
        </p>
        <p className="m-0">
          <SpanRef span={shot.span} />
        </p>
        <p className="mt-auto mb-0 text-[13px] font-bold text-withheld">{why}</p>
        {action}
      </div>
    </div>
  );
}

// Both carry "Try another render" (T061 withheld, T066 failed); the failed card says why, by
// FrameView.failure (cards.ts).
const WithheldCard = TextCard;
const RenderFailedCard = TextCard;

export function FrameCard({
  shot,
  k,
  frame,
  on,
  onHighlight,
  href,
  onOpen,
  retry,
}: {
  shot: ShotView;
  k: number;
  frame: FrameView | undefined;
  on: boolean;
  onHighlight: Dispatch<SetStateAction<string | null>>;
  /** The page with `?shot={id}`: the link that opens this card's frame sheet. */
  href: string;
  /** Called when the card's link is followed: the sheet then closes by going back. */
  onOpen: (id: string) => void;
  /** "Try another render", for a withheld or failed frame (null otherwise). */
  retry: ReactNode;
}) {
  const { media, verdict, notes } = cardState(frame);
  const textCard = media.kind === "withheld" || media.kind === "failed";
  return (
    // The shot id is the card's one link, stretched over all of it, so a click anywhere opens the
    // sheet (web.md §4.4). Anything clickable added inside a card must be `relative z-10`.
    <article
      id={`shot-${shot.id}`}
      data-state={frame?.state ?? "none"}
      onMouseEnter={() => onHighlight(shot.id)}
      onMouseLeave={(event) => {
        // A card with focus inside it (its link) stays highlighted: only its blur lets go.
        // ...and a card only lets go of its own highlight, handing it to the card with focus, if any.
        if (event.currentTarget.contains(document.activeElement)) return;
        const focused = document.activeElement?.closest<HTMLElement>("article[id^='shot-']")?.id.slice(5) ?? null;
        onHighlight((current) => (current === shot.id ? focused : current));
      }}
      onFocus={() => onHighlight(shot.id)}
      onBlur={() => onHighlight((current) => (current === shot.id ? null : current))}
      className={cn("relative scroll-mt-4 border-t-4 bg-paper shadow-page", on && "outline-2 outline-offset-[3px] outline-pencil")}
      style={{ borderTopColor: lineColour(k) }}
    >
      {media.kind === "image" && <FrameMedia url={media.url} shot={shot} />}
      {media.kind === "pending" && <PendingMedia text={media.text} busy={media.busy} />}
      {media.kind === "withheld" && <WithheldCard shot={shot} why={media.why} action={retry} />}
      {media.kind === "failed" && <RenderFailedCard shot={shot} why={media.why} action={retry} />}
      <header className="flex flex-wrap items-center gap-x-2.5 gap-y-1 px-3.5 pt-2.5 *:whitespace-nowrap">
        <Link
          href={href}
          scroll={false}
          aria-label={`Open shot ${shot.id}`}
          data-card-link={shot.id}
          onClick={() => onOpen(shot.id)}
          className="font-display text-xl leading-none font-extrabold text-ink no-underline after:absolute after:inset-0 after:content-[''] focus-visible:outline-none focus-visible:after:outline-2 focus-visible:after:outline-offset-[3px] focus-visible:after:outline-pencil"
        >
          {shot.id}
        </Link>
        <span className="text-[13px] text-ink-2">{cameraText(shot)}</span>
        {verdict && (
          <span className="ml-auto">
            <Verdict tone={verdict.tone}>{verdict.label}</Verdict>
          </span>
        )}
      </header>
      <p className={cn("mx-3.5 mt-1.5 text-[13px] font-bold", textCard ? "mb-3.5" : "mb-0")}>{whoText(shot)}</p>
      {!textCard && (
        <p className="mx-3.5 mt-1.5 mb-3.5 text-[13px]">
          <SourceText shot={shot} /> <SpanRef span={shot.span} />
        </p>
      )}
      {notes.map((note) => (
        <p key={note} className="mx-3.5 -mt-2 mb-3.5 text-[13px] text-warn">
          {note}
        </p>
      ))}
    </article>
  );
}
