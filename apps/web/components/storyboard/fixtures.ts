// The lighthouse project of storyboard.png (web.md §2: the self-written script of
// services/api/tests/script/conftest.py), as the API's views would send it. Test data only.

import type { FrameView, Job, LinesView, Project, ShotView } from "@/lib/api/types";

const PAGE_1 = [
  "                            THE KEEPER'S LIGHT",
  "",
  "          FADE IN:",
  "",
  "    1     INT. LIGHTHOUSE KITCHEN - NIGHT                         1",
  "",
  "          Rain hammers the window. NANDI (60s, oilskin coat)",
  "          pours tea into two chipped mugs.",
  "",
  "          DOORS SLAM.",
  "",
  "                                NANDI",
  "                          (without turning)",
  "                    You came back.",
  "",
  "                                THABO (O.S.)",
  "                    The boat didn't. I walked the last",
  "                    mile along the cliff.",
  "",
  "                                                       CUT TO:",
  "",
  "    2     EXT. LIGHTHOUSE GALLERY -- CONTINUOUS                   2",
  "",
  "          THABO steps out into the wind, holding a torn map.",
  "",
  "                                THABO",
  "                    It's gone.",
  "                          (beat)",
  "                    All of it.",
  "                                (MORE)",
];
const PAGE_2 = [
  "                                                                  2.",
  "                                THABO (CONT'D)",
  "                    The whole coast.",
  "",
  "    3     INT. LIGHTHOUSE STAIRWELL                               3",
  "",
  "          Silence.",
];

export const lines: LinesView = { lines: [...PAGE_1, ...PAGE_2], page_starts: [1, 31] };

const span = (page: number, line_start: number, line_end = line_start) => ({ page, line_start, line_end });
const action = (line_start: number, line_end = line_start) => ({ line_start, line_end, cue: null, extension: null, on_screen: true });

const shot = (over: Partial<ShotView> & Pick<ShotView, "id" | "scene_index" | "number" | "span" | "source">): ShotView => ({
  framing: "wide",
  movement: "static",
  characters: [],
  props: [],
  time_of_day: "NIGHT",
  rationale: "",
  segments: [action(over.span.line_start, over.span.line_end)],
  ...over,
});

export const shots: ShotView[] = [
  shot({
    id: "1.1", scene_index: 0, number: 1, span: span(1, 7, 8),
    characters: ["NANDI"], props: ["oilskin coat", "two chipped mugs"],
    source: "Rain hammers the window. NANDI (60s, oilskin coat) pours tea into two chipped mugs.",
  }),
  shot({ id: "1.2", scene_index: 0, number: 2, framing: "insert", span: span(1, 10), source: "DOORS SLAM." }),
  shot({
    id: "1.3", scene_index: 0, number: 3, framing: "close_up", characters: ["NANDI"], span: span(1, 14),
    source: "You came back.", segments: [{ line_start: 14, line_end: 14, cue: "NANDI", extension: null, on_screen: true }],
  }),
  shot({
    id: "1.4", scene_index: 0, number: 4, framing: "medium", characters: ["NANDI"], span: span(1, 17, 18),
    source: "The boat didn't. I walked the last mile along the cliff.",
    segments: [{ line_start: 17, line_end: 18, cue: "THABO", extension: "O.S.", on_screen: false }],
  }),
  shot({
    id: "2.1", scene_index: 1, number: 1, movement: "tracking", characters: ["THABO"], props: ["torn map"],
    span: span(1, 24), source: "THABO steps out into the wind, holding a torn map.",
  }),
  shot({
    id: "2.2", scene_index: 1, number: 2, framing: "close_up", characters: ["THABO"], span: span(1, 27, 33),
    source: "It's gone.\nAll of it.\nThe whole coast.",
    segments: [
      { line_start: 27, line_end: 27, cue: "THABO", extension: null, on_screen: true },
      { line_start: 29, line_end: 29, cue: "THABO", extension: null, on_screen: true },
      { line_start: 33, line_end: 33, cue: "THABO", extension: "CONT'D", on_screen: true },
    ],
  }),
  shot({ id: "3.1", scene_index: 2, number: 1, span: span(2, 37), source: "Silence." }),
];

export const job = (over: Partial<Job> = {}): Job => ({
  id: "j1",
  state: "done",
  stage: "planning",
  progress: 60,
  error: null,
  updated_at: "2026-10-07T07:14:00Z",
  ...over,
});

export const keeper = (over: Partial<Project> = {}): Project => ({
  id: "p1",
  title: "The Keeper's Light",
  created_at: "2026-10-07T07:14:00Z",
  pages: 2,
  scenes: 3,
  shots: 7,
  frames: null,
  job: job(),
  scene_list: [
    { index: 0, number: "1", heading: "INT. LIGHTHOUSE KITCHEN - NIGHT", time_of_day: "NIGHT", time_carried: false, elements: 4, shots: 4 },
    { index: 1, number: "2", heading: "EXT. LIGHTHOUSE GALLERY -- CONTINUOUS", time_of_day: "NIGHT", time_carried: true, elements: 4, shots: 2 },
    { index: 2, number: "3", heading: "INT. LIGHTHOUSE STAIRWELL", time_of_day: "NIGHT", time_carried: true, elements: 1, shots: 1 },
  ],
  entities: [],
  report: null,
  ...over,
});

export const frame = (over: Partial<FrameView> & Pick<FrameView, "shot_id" | "state">): FrameView => ({
  attempt: 1,
  max_renders: 3,
  image_url: null,
  withheld_check: null,
  failure: null,
  audits: [],
  ...over,
});
