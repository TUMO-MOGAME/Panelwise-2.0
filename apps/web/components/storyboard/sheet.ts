// What the frame sheet says (web.md §4.4 and T045's rules under it): the header's words, the
// speaker of each source part, the span in words, and where the accepted audit saw each person.

import type { FrameView, SceneView, ShotView, SpanRef } from "@/lib/api/types";

import { cameraText, sourceParts } from "./cards";

/** "Medium · Static · NIGHT": the card's camera words, then the time verbatim when there is one. */
export const sheetCamera = (shot: ShotView) =>
  shot.time_of_day ? `${cameraText(shot)} · ${shot.time_of_day}` : cameraText(shot);

/**
 * Each part of the source with its speaker label, "THABO (O.S.)", shown only when it differs from
 * the previous part's; null for action and for a part with no segment (a heading-only shot).
 */
export function sourceBlocks(shot: ShotView): { speaker: string | null; text: string }[] {
  let last: string | null = null;
  return sourceParts(shot).map((text, i) => {
    const segment = shot.segments.at(i);
    const label = segment?.cue ? (segment.extension ? `${segment.cue} (${segment.extension})` : segment.cue) : null;
    const speaker = label !== null && label !== last ? label : null;
    last = label;
    return { speaker, text };
  });
}

/** "Page 1, lines 17–18 · scene 1, INT. LIGHTHOUSE KITCHEN - NIGHT" ("line 14" for one). */
export function spanWords(span: SpanRef, scene: SceneView | undefined): string {
  const lines = span.line_end > span.line_start ? `lines ${span.line_start}–${span.line_end}` : `line ${span.line_start}`;
  const where = `Page ${span.page}, ${lines}`;
  return scene ? `${where} · scene ${scene.number}, ${scene.heading}` : where;
}

/** Where the accepted audit (the last that passed or warned) placed each character; {} before T021. */
export function positions(frame: FrameView | undefined): Record<string, string> {
  const accepted = frame?.audits.findLast((a) => a.verdict === "pass" || a.verdict === "warn");
  return accepted?.positions ?? {};
}
