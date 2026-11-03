// Test data for the comic page: the-red-kite's reference page 1 (docs/design/comic/), its real
// rects and lettering, as the API's ComicView would carry it.

import type { ComicMade, ComicView, Job, LetteringView } from "@/lib/api/types";

const span = (line_start: number, line_end = line_start) => ({ page: 2, line_start, line_end });

export const scene = (text: string, line: number, rect: LetteringView["rect"]): LetteringView => ({
  kind: "scene",
  speaker: null,
  cue: null,
  text,
  span: span(line),
  rect,
});

export const said = (
  kind: LetteringView["kind"],
  speaker: string,
  cue: string,
  text: string,
  lines: [number, number],
  rect: LetteringView["rect"],
): LetteringView => ({ kind, speaker, cue, text, span: span(...lines), rect });

export const comic = (over: Partial<ComicMade> = {}): ComicMade => ({
  made_at: "2026-10-09T12:20:00Z",
  pdf_url: "https://signed/comics/c.pdf?e=3600",
  pages: [
    {
      number: 1,
      width: 1988,
      height: 3075,
      image_url: "https://signed/comics/p1.png?e=3600",
      panels: [
        { shot_id: "1.1", rect: [120, 120, 1748, 986], withheld: false, lettering: [scene("FLAT ROOF — DAY", 73, [136, 136, 298, 69])] },
        {
          shot_id: "1.2",
          rect: [120, 1142, 930, 789],
          withheld: false,
          lettering: [
            said("speech", "LERATO", "LERATO", "Come on. Come on, wind.", [84, 84], [435, 1158, 380, 69]),
            said("speech", "LERATO", "LERATO", "No, no, no!", [90, 90], [435, 1252, 180, 69]),
          ],
        },
        {
          shot_id: "1.3",
          rect: [1086, 1142, 782, 789],
          withheld: true,
          lettering: [
            said("off_panel", "MOKGOSI", "MOKGOSI (O.S.)", "Is that my good shirt you are flying?", [93, 94], [1102, 1158, 321, 106]),
          ],
        },
      ],
    },
    {
      number: 2,
      width: 1988,
      height: 3075,
      image_url: "https://signed/comics/p2.png?e=3600",
      panels: [
        {
          shot_id: "2.1",
          rect: [120, 120, 1748, 986],
          withheld: false,
          lettering: [said("voice_over", "LERATO", "LERATO (V.O.)", "It was the best kite.", [101, 101], [136, 136, 400, 69])],
        },
      ],
    },
  ],
  ...over,
});

export const job = (over: Partial<Job> = {}): Job => ({
  id: "j1",
  state: "running",
  stage: "rendering",
  progress: 43,
  error: null,
  updated_at: "2026-10-09T12:00:00Z",
  ...over,
});

export const view = (over: Partial<ComicView> = {}): ComicView => ({
  can_make: true,
  shots: 21,
  job: null,
  comic: null,
  ...over,
});
