import { describe, expect, it } from "vitest";

import { boardState, mergeFrames } from "./board";
import { cameraText, cardState, checkWords, sourceParts, whoText } from "./cards";
import { frame, job, keeper, lines, shots } from "./fixtures";
import { lineColour, pieces, scriptPages } from "./lined";

const byId = (id: string) => shots.find((s) => s.id === id)!;

describe("the lined script's geometry (web.md §4.3; storyboard.html's inline styles)", () => {
  const [p1, p2] = scriptPages(lines);

  it("splits the lines at page_starts, numbered globally", () => {
    expect(p1).toMatchObject({ number: 1, start: 1 });
    expect(p1.lines).toHaveLength(30);
    expect(p2).toMatchObject({ number: 2, start: 31 });
    expect(p2.lines[0].trim()).toBe("2.");
  });

  it("places every shot exactly where storyboard.html does", () => {
    const at = (page: typeof p1) =>
      Object.fromEntries(pieces(page, shots).map((p) => [p.shot.id, [p.top, p.height, p.left]]));
    expect(at(p1)).toEqual({
      "1.1": [134, 40, 0],
      "1.2": [200, 18, 30],
      "1.3": [288, 18, 0],
      "1.4": [354, 40, 30],
      "2.1": [508, 18, 0],
      "2.2": [574, 84, 30],
    });
    expect(at(p2)).toEqual({ "2.2": [2, 62, 30], "3.1": [134, 18, 0] });
  });

  it("a shot over a page break runs on, then continues on the next page", () => {
    const [onP1] = pieces(p1, shots).filter((p) => p.shot.id === "2.2");
    const [onP2] = pieces(p2, shots).filter((p) => p.shot.id === "2.2");
    expect([onP1.runsOn, onP1.continued]).toEqual([true, false]);
    expect([onP2.runsOn, onP2.continued]).toEqual([false, true]);
    expect(pieces(p1, shots).find((p) => p.shot.id === "1.1")).toMatchObject({ runsOn: false, continued: false });
  });

  it("draws an off-screen speaker's lines wavy and the rest straight", () => {
    expect(pieces(p1, shots).find((p) => p.shot.id === "1.4")!.runs).toEqual([{ top: 0, height: 40, wavy: true }]);
    const mixed = { ...byId("2.2"), segments: [...byId("2.2").segments.slice(0, 1), { line_start: 29, line_end: 29, cue: "RADIO", extension: null, on_screen: false }] };
    expect(pieces(p1, [mixed])[0].runs).toEqual([
      { top: 0, height: 44, wavy: false },
      { top: 44, height: 22, wavy: true },
      { top: 66, height: 18, wavy: false },
    ]);
  });

  it("a heading-only establishing shot draws straight over its span", () => {
    const establishing = { ...byId("2.1"), id: "2.0", span: { page: 1, line_start: 22, line_end: 22 }, segments: [] };
    expect(pieces(p1, [establishing])[0].runs).toEqual([{ top: 0, height: 18, wavy: false }]);
  });

  it("colours the k-th shot --line-{(k mod 6)+1}", () => {
    expect(lineColour(0)).toBe("var(--color-line-1)");
    expect(lineColour(5)).toBe("var(--color-line-6)");
    expect(lineColour(6)).toBe("var(--color-line-1)"); // 3.1 in storyboard.png
  });
});

describe("card text (web.md §4.3)", () => {
  it("the camera in words", () => {
    expect(cameraText(byId("1.3"))).toBe("Close-up · Static");
    expect(cameraText(byId("2.1"))).toBe("Wide · Tracking");
    expect(cameraText({ ...byId("1.1"), framing: "over_shoulder", movement: "handheld" })).toBe("Over the shoulder · Handheld");
  });

  it("who and what is in frame, 'No one in frame' first when no character is", () => {
    expect(whoText(byId("1.1"))).toBe("NANDI · oilskin coat · two chipped mugs");
    expect(whoText(byId("1.2"))).toBe("No one in frame");
    expect(whoText({ ...byId("1.2"), props: ["door"] })).toBe("No one in frame · door");
  });

  it("the source in its parts, one per covered element", () => {
    expect(sourceParts(byId("2.2"))).toEqual(["It's gone.", "All of it.", "The whole coast."]);
    expect(sourceParts(byId("1.4"))).toEqual(["The boat didn't. I walked the last mile along the cliff."]);
  });

  it("every row of the card table", () => {
    expect(cardState(undefined)).toEqual({ media: { kind: "pending", text: "Not rendered yet", busy: false }, verdict: null, notes: [] });
    expect(cardState(frame({ shot_id: "1.1", state: "rendering" }))).toMatchObject({
      media: { kind: "pending", text: "Rendering attempt 1 of 3", busy: true },
      verdict: { tone: "pending", label: "Rendering" },
    });
    expect(cardState(frame({ shot_id: "1.1", state: "auditing", attempt: 2 }))).toMatchObject({
      media: { text: "Auditing attempt 2 of 3" },
      verdict: { label: "Auditing" },
    });
    expect(cardState(frame({ shot_id: "1.1", state: "passed", image_url: "https://s/1" }))).toEqual({
      media: { kind: "image", url: "https://s/1" },
      verdict: { tone: "pass", label: "Passed audit" },
      notes: [],
    });
    expect(cardState(frame({ shot_id: "1.4", state: "passed", attempt: 2, image_url: "https://s/4" })).notes).toEqual([
      "Passed on attempt 2 of 3",
    ]);
    const warned = frame({
      shot_id: "1.3",
      state: "warned",
      image_url: "https://s/3",
      audits: [
        {
          attempt: 1, seed: 1, verdict: "warn", description: null, judgement: null, positions: {}, models: [], created_at: "",
          checks: [
            { check: "light", severity: "soft", ok: false, detail: "day light in a night scene" },
            { check: "framing", severity: "soft", ok: true, detail: "" },
            { check: "setting", severity: "hard", ok: true, detail: "" },
          ],
        },
      ],
    });
    expect(cardState(warned)).toMatchObject({ verdict: { tone: "warn", label: "Passed with a warning" }, notes: ["Light: day light in a night scene"] });
    // T094: a hard check off the rule ladder fails but warns, and the card names it.
    const laddered = frame({
      shot_id: "1.5",
      state: "warned",
      image_url: "https://s/5",
      audits: [
        {
          attempt: 1, seed: 1, verdict: "warn", description: null, judgement: null, positions: {}, models: [], created_at: "",
          checks: [
            { check: "unscripted_person", severity: "hard", ok: false, detail: "person 2: no shot character, no support" },
            { check: "light", severity: "soft", ok: false, detail: "day light in a night scene" },
          ],
        },
      ],
    });
    expect(cardState(laddered).notes).toHaveLength(2);
    expect(cardState(laddered).notes[1]).toBe("Light: day light in a night scene");
    expect(cardState(frame({ shot_id: "3.1", state: "withheld", withheld_check: "text_in_frame" }))).toEqual({
      media: { kind: "withheld", why: "Frame withheld: failed audit (text in frame)" },
      verdict: { tone: "withheld", label: "Withheld" },
      notes: [],
    });
    expect(cardState(frame({ shot_id: "3.1", state: "failed" }))).toMatchObject({
      media: { kind: "failed", why: "The renderer failed on this frame." },
      verdict: { label: "Render failed" },
    });
  });

  it("no image outside passed and warned, whatever the frame carries", () => {
    for (const state of ["rendering", "auditing", "withheld", "failed"] as const) {
      expect(cardState(frame({ shot_id: "1.1", state, image_url: "https://leak" })).media.kind).not.toBe("image");
    }
  });

  it("check names in words (web.md §6, Copy)", () => {
    expect(checkWords("audit_error")).toBe("the audit couldn't run");
    expect(checkWords("setting")).toBe("wrong setting");
    expect(checkWords("signature")).toBe("artist's signature"); // T077
    expect(checkWords("no_character")).toBe("no character in frame"); // T080
    expect(checkWords("background_object")).toBe("unscripted background"); // T083
  });
});

describe("the page by the job (web.md §4.3's table)", () => {
  it("queued, reading and planning wait for the plan", () => {
    expect(boardState(keeper({ shots: null, job: job({ state: "queued", stage: null }) }))).toBe("waiting");
    expect(boardState(keeper({ shots: null, job: job({ state: "running", stage: "planning" }) }))).toBe("waiting");
  });
  it("rendering is live, done is ready, and done with a frame active is live again", () => {
    expect(boardState(keeper({ job: job({ state: "running", stage: "rendering" }) }))).toBe("live");
    expect(boardState(keeper())).toBe("ready");
    expect(boardState(keeper({ frames: { settled: 6, total: 7, withheld: 1, active: 1 } }))).toBe("live");
  });
  it("a failed job is failed, plan or not", () => {
    expect(boardState(keeper({ job: job({ state: "failed", stage: "rendering", error: "x" }) }))).toBe("failed");
    expect(boardState(keeper({ shots: null, job: job({ state: "failed", stage: "parsing", error: "x" }) }))).toBe("failed");
  });
});

describe("mergeFrames (web.md §4.3: a fresh signed URL never reloads an image on screen)", () => {
  it("keeps the old URL while state and attempt are unchanged, takes the new one otherwise", () => {
    const old = [
      frame({ shot_id: "1.1", state: "passed", image_url: "https://s/old" }),
      frame({ shot_id: "1.2", state: "auditing" }),
    ];
    const fresh = [
      frame({ shot_id: "1.1", state: "passed", image_url: "https://s/new" }),
      frame({ shot_id: "1.2", state: "passed", image_url: "https://s/12" }),
      frame({ shot_id: "1.3", state: "rendering" }),
    ];
    expect(mergeFrames(old, fresh).map((f) => [f.shot_id, f.state, f.image_url])).toEqual([
      ["1.1", "passed", "https://s/old"],
      ["1.2", "passed", "https://s/12"],
      ["1.3", "rendering", null],
    ]);
  });
});
