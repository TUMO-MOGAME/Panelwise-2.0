"use client";

// The lined script (web.md §4.3; storyboard.css `.lined`): the screenplay's own pages, each shot a
// line in the gutter over exactly its lines, wavy where its speaker is off screen. The signature
// of the app: a frame is never far from the words it came from.

import { spanText } from "@/components/shared/SpanRef";
import type { ShotView } from "@/lib/api/types";
import { cn } from "@/lib/utils";

import { covers, LINE_PX, lineColour, pieces, type Piece, type ScriptPage } from "./lined";

const wavy = (colour: string) =>
  `radial-gradient(circle at 0 50%, transparent 3px, ${colour} 3px 4.5px, transparent 4.5px) 0 0 / 8px 8px repeat-y`;

function ShotLine({ piece, on, onPick }: { piece: Piece; on: boolean; onPick: (id: string) => void }) {
  const c = lineColour(piece.k);
  const id = piece.shot.id;
  return (
    <a
      href={`#shot-${id}`}
      aria-label={`Shot ${id}, ${spanText(piece.shot.span)}`}
      data-shot={id}
      data-runs-on={piece.runsOn || undefined}
      data-continued={piece.continued || undefined}
      onClick={(event) => {
        event.preventDefault();
        onPick(id);
      }}
      className="absolute ml-[9px] block w-[22px] no-underline"
      style={{ top: piece.top, height: piece.height, left: piece.left }}
    >
      {piece.runs.map((run) => (
        <span
          key={run.top}
          data-wavy={run.wavy || undefined}
          className="absolute"
          style={
            run.wavy
              ? { top: run.top, height: run.height, left: -3, width: 8, background: wavy(c) }
              : { top: run.top, height: run.height, left: 0, borderLeft: `${on ? 5 : 3}px solid ${c}` }
          }
        />
      ))}
      <b
        className={cn(
          "absolute -top-[9px] -left-[14px] min-w-7 rounded-[2px] border-[1.5px] px-[3px] py-px text-center font-body text-[10px] leading-[1.3] font-bold",
          on ? "text-white" : "bg-paper text-ink",
          piece.continued && !on && "opacity-75",
        )}
        style={{ borderColor: c, ...(on ? { background: c } : {}) }}
      >
        {id}
      </b>
      {piece.runsOn ? (
        <span
          className="absolute -bottom-2 -left-[7px] size-0 border-x-[5px] border-t-[7px] border-x-transparent"
          style={{ borderTopColor: c }}
        />
      ) : (
        <span className="absolute -bottom-px -left-2 w-[13px] border-b-[3px]" style={{ borderBottomColor: c }} />
      )}
    </a>
  );
}

function Sheet({
  page,
  shots,
  highlight,
  onPick,
}: {
  page: ScriptPage;
  shots: readonly ShotView[];
  highlight: ShotView | null;
  onPick: (id: string) => void;
}) {
  return (
    <section
      aria-label={`Script page ${page.number}`}
      className="relative mb-[18px] w-max min-w-full bg-paper pt-6 pr-5 pb-7 pl-[76px] shadow-page"
    >
      <span className="absolute top-2.5 right-4 font-script text-xs text-ink-2">{page.number}.</span>
      <div className="absolute top-6 left-3 h-0 w-[60px]">
        {pieces(page, shots).map((piece) => (
          <ShotLine key={piece.shot.id} piece={piece} on={piece.shot.id === highlight?.id} onPick={onPick} />
        ))}
      </div>
      <div className="font-script text-[13px] whitespace-pre text-ink" style={{ lineHeight: `${LINE_PX}px` }}>
        {page.lines.map((line, i) => {
          const n = page.start + i;
          return (
            <div
              key={n}
              data-line={n}
              className={cn(highlight && covers(highlight, n) && "bg-pencil-soft")}
              style={{ height: LINE_PX }}
            >
              <i className="-ml-[34px] mr-1.5 inline-block w-7 text-right text-[10px] text-[#a3adb5] not-italic">{n}</i>
              {line || " "}
            </div>
          );
        })}
      </div>
    </section>
  );
}

export function LinedScript({
  pages,
  shots,
  highlight,
  onPick,
}: {
  pages: readonly ScriptPage[];
  shots: readonly ShotView[];
  highlight: string | null;
  onPick: (id: string) => void;
}) {
  const on = shots.find((s) => s.id === highlight) ?? null;
  return (
    <aside
      aria-label="Lined script"
      className="sticky top-4 hidden max-h-[calc(100vh-32px)] overflow-auto pb-2 min-[1101px]:block"
    >
      <p className="mt-0 mb-3 font-display text-[13px] leading-none font-semibold tracking-[0.14em] text-ink-2 uppercase">
        Lined script
      </p>
      {pages.map((page) => (
        <Sheet key={page.number} page={page} shots={shots} highlight={on} onPick={onPick} />
      ))}
      <p className="mt-1 mb-0 flex items-center gap-2 text-xs text-ink-2">
        <span aria-hidden className="inline-block h-4 w-[3px] bg-ink-2" /> speaker on screen
        <span aria-hidden className="ml-3 inline-block h-4 w-2" style={{ background: wavy("var(--color-ink-2)") }} />{" "}
        speaker off screen
      </p>
    </aside>
  );
}
