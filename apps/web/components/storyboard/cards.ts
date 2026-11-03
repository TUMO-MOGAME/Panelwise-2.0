// What a frame card says (web.md §4.3, the card table and its text rules): the camera, who and
// what is in frame, the source, and the state of its frame.

import type { VerdictTone } from "@/components/shared/Verdict";
import type { FrameView, ShotView } from "@/lib/api/types";

const FRAMING: Record<ShotView["framing"], string> = {
  wide: "Wide",
  medium: "Medium",
  close_up: "Close-up",
  extreme_close_up: "Extreme close-up",
  over_shoulder: "Over the shoulder",
  pov: "Point of view",
  insert: "Insert",
};

const MOVEMENT: Record<ShotView["movement"], string> = {
  static: "Static",
  pan: "Pan",
  tilt: "Tilt",
  dolly: "Dolly",
  tracking: "Tracking",
  handheld: "Handheld",
  crane: "Crane",
};

/** Check names in words (web.md §6, Copy). */
const CHECKS: Record<string, string> = {
  unscripted_person: "unscripted person",
  unscripted_object: "unscripted object",
  text_in_frame: "text in frame",
  setting: "wrong setting",
  missing_character: "missing character",
  light: "light",
  framing: "framing",
  signature: "artist's signature",
  no_character: "no character in frame",
  background_object: "unscripted background",
  audit_error: "the audit couldn't run",
};

export const checkWords = (check: string) => CHECKS[check] ?? check.replaceAll("_", " ");
export const sentence = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

export const cameraText = (shot: ShotView) => `${FRAMING[shot.framing]} · ${MOVEMENT[shot.movement]}`;

/** "NANDI · oilskin coat", or "No one in frame" first when no character is in it. */
export function whoText(shot: ShotView): string {
  const people = shot.characters.length > 0 ? shot.characters : ["No one in frame"];
  return [...people, ...shot.props].join(" · ");
}

/** The source's parts, one per covered element (the API joins them with "\n"). */
export const sourceParts = (shot: ShotView) => shot.source.split("\n");

export type CardMedia =
  | { kind: "pending"; text: string; busy: boolean }
  | { kind: "image"; url: string }
  | { kind: "withheld"; why: string }
  | { kind: "failed"; why: string };

export interface CardState {
  media: CardMedia;
  verdict: { tone: VerdictTone; label: string } | null;
  notes: string[]; // the extra lines under the source
}

export const RENDERER_FAILED = "The renderer failed on this frame.";
export const RESTART_FAILED = "Rendering was interrupted by a restart.";

export function cardState(frame: FrameView | undefined): CardState {
  if (!frame) return { media: { kind: "pending", text: "Not rendered yet", busy: false }, verdict: null, notes: [] };
  const of = `attempt ${frame.attempt} of ${frame.max_renders}`;
  switch (frame.state) {
    case "rendering":
      return { media: { kind: "pending", text: `Rendering ${of}`, busy: true }, verdict: { tone: "pending", label: "Rendering" }, notes: [] };
    case "auditing":
      return { media: { kind: "pending", text: `Auditing ${of}`, busy: true }, verdict: { tone: "pending", label: "Auditing" }, notes: [] };
    case "withheld":
      return {
        media: { kind: "withheld", why: `Frame withheld: failed audit (${checkWords(frame.withheld_check ?? "audit_error")})` },
        verdict: { tone: "withheld", label: "Withheld" },
        notes: [],
      };
    case "failed":
      return {
        media: { kind: "failed", why: frame.failure === "restart" ? RESTART_FAILED : RENDERER_FAILED },
        verdict: { tone: "withheld", label: "Render failed" },
        notes: [],
      };
    case "passed":
    case "warned": {
      // The API sends image_url only for these two (web.md §6); without one there is nothing to show.
      const media: CardMedia = frame.image_url
        ? { kind: "image", url: frame.image_url }
        : { kind: "pending", text: "Not rendered yet", busy: false };
      if (frame.state === "passed") {
        return {
          media,
          verdict: { tone: "pass", label: "Passed audit" },
          notes: frame.attempt > 1 ? [`Passed on ${of}`] : [],
        };
      }
      const audit = frame.audits.at(-1);
      // Every failed check: with the rule ladder (T094) a hard one off it is shown, not withheld.
      const failed = (audit?.checks ?? []).filter((c) => !c.ok);
      return {
        media,
        verdict: { tone: "warn", label: "Passed with a warning" },
        notes: failed.map((c) => `${sentence(checkWords(c.check))}: ${c.detail}`),
      };
    }
  }
}
