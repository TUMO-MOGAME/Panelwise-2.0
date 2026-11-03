// The lined script's geometry (web.md §4.3, Geometry; storyboard.html, storyboard.css): pages
// split where the PDF broke them, and each shot as a line in the gutter over exactly its span.

import type { LinesView, ShotView } from "@/lib/api/types";

export const LINE_PX = 22;
const LANE_PX = 30;

export interface ScriptPage {
  number: number; // 1-based
  start: number; // the global number of its first line
  lines: string[];
}

/** One straight or wavy stretch of a piece, in px from the piece's top. */
export interface Run {
  top: number;
  height: number;
  wavy: boolean;
}

/** A shot's line on one page: its whole span, clipped to the page. */
export interface Piece {
  shot: ShotView;
  k: number; // the shot's place in script order: its colour and lane
  top: number;
  height: number;
  left: number;
  runsOn: boolean; // the shot carries on past this page's last line (an arrowhead)
  continued: boolean; // the shot began on an earlier page
  runs: Run[];
}

export function scriptPages({ lines, page_starts }: LinesView): ScriptPage[] {
  return page_starts.map((start, i) => {
    const end = i + 1 < page_starts.length ? page_starts[i + 1] : lines.length + 1;
    return { number: i + 1, start, lines: lines.slice(start - 1, end - 1) };
  });
}

/** `--color-line-{(k mod 6)+1}`, the k-th shot's colour. */
export const lineColour = (k: number) => `var(--color-line-${(k % 6) + 1})`;

/** Straight and wavy stretches over lines a..b: wavy where an off-screen speaker's dialogue is. */
function runs(shot: ShotView, a: number, b: number): Run[] {
  const wavy = (line: number) =>
    shot.segments.some((s) => !s.on_screen && s.line_start <= line && line <= s.line_end);
  const out: Run[] = [];
  for (let line = a; line <= b; line++) {
    const w = wavy(line);
    const last = out.at(-1);
    if (last && last.wavy === w) last.height += LINE_PX;
    else out.push({ top: (line - a) * LINE_PX, height: LINE_PX, wavy: w });
  }
  // the piece itself ends 4 px short of its last line (storyboard.css), and so does its last run
  out[out.length - 1].height -= 4;
  return out;
}

/** Every shot's piece on this page, in script order. */
export function pieces(page: ScriptPage, shots: readonly ShotView[]): Piece[] {
  const last = page.start + page.lines.length - 1;
  const out: Piece[] = [];
  shots.forEach((shot, k) => {
    const { line_start, line_end } = shot.span;
    if (line_end < page.start || line_start > last) return;
    const a = Math.max(line_start, page.start);
    const b = Math.min(line_end, last);
    out.push({
      shot,
      k,
      top: (a - page.start) * LINE_PX + 2,
      height: (b - a + 1) * LINE_PX - 4,
      left: (k % 2) * LANE_PX,
      runsOn: line_end > last,
      continued: line_start < page.start,
      runs: runs(shot, a, b),
    });
  });
  return out;
}

/** Is this global line inside the shot's span (its lines tint while the shot is highlighted)? */
export const covers = (shot: ShotView, line: number) => shot.span.line_start <= line && line <= shot.span.line_end;
