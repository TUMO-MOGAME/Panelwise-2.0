// The audit log's words (web.md §4.4 step 5 and T061's rules for it): each attempt's verdict, what
// the describer saw, who the judge called each person, the checks, and the models.

import { modelName } from "@/components/script/report";
import type { VerdictTone } from "@/components/shared/Verdict";
import type { AuditView } from "@/lib/api/types";

import { checkWords, sentence } from "./cards";

export const VERDICTS: Record<AuditView["verdict"], { label: string; tone: VerdictTone }> = {
  pass: { label: "Passed", tone: "pass" },
  warn: { label: "Passed with a warning", tone: "warn" },
  fail: { label: "Failed", tone: "withheld" },
  error: { label: "Audit error", tone: "withheld" },
};

/** The attempt's left edge: pass for an accepted attempt, withheld otherwise. */
export const accepted = (a: AuditView) => a.verdict === "pass" || a.verdict === "warn";

const NUMBERS = ["No one", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten"];
const SETTING: Record<string, string> = { interior: "Interior", exterior: "Exterior", unclear: "Setting unclear" };
const LIGHT: Record<string, string> = { day: "day", night: "night", dawn_or_dusk: "dawn or dusk", unclear: "light unclear" };
const SIZE: Record<string, string> = {
  wide: "wide",
  medium: "medium",
  close: "close",
  extreme_close: "extreme close",
  unclear: "size unclear",
};

/** "Two people: left, an older woman; right, a man. Interior, night, medium." */
export function seenWords(a: AuditView): string {
  const d = a.description;
  if (d === null) return "The audit couldn't run.";
  const n = d.people.length;
  const count = n === 0 ? "No one" : `${NUMBERS[n] ?? n} ${n === 1 ? "person" : "people"}`;
  const people = n === 0 ? count : `${count}: ${d.people.map((p) => `${p.position}, ${p.appearance}`).join("; ")}`;
  const scene = [SETTING[d.setting] ?? d.setting, LIGHT[d.light] ?? d.light, SIZE[d.shot_size] ?? d.shot_size];
  return `${people}. ${scene.join(", ")}.`;
}

/** "person 0 is NANDI · person 1 is no one in the shot"; null when there is nothing to say. */
export function judgedWords(a: AuditView): string | null {
  const people = a.judgement?.people ?? [];
  if (people.length === 0) return null;
  return people
    .map((p) => `person ${p.person} is ${p.character ?? "no one in the shot"}`)
    .join(" · ");
}

/** The failed checks with their details, then how many others passed. */
export function checkLines(a: AuditView): { failed: { name: string; detail: string }[]; rest: string | null } {
  const failed = a.checks.filter((c) => !c.ok).map((c) => ({ name: sentence(checkWords(c.check)), detail: c.detail }));
  const passed = a.checks.length - failed.length;
  if (a.checks.length === 0) return { failed, rest: null };
  const s = passed === 1 ? "" : "s";
  const rest = failed.length === 0 ? `All ${passed} check${s} passed` : `${passed} other check${s} passed`;
  return { failed, rest };
}

/** "Described by Nemotron-3.5-Super-VL · judged by Nemotron 3 Super"; null without both models. */
export function modelsWords(a: AuditView): string | null {
  const [describer, judge] = a.models;
  if (!describer) return null;
  const by = `Described by ${modelName(describer, { short: true })}`;
  return judge ? `${by} · judged by ${modelName(judge, { short: true })}` : by;
}

export const attemptsTitle = (n: number) => `Audit · ${n} attempt${n === 1 ? "" : "s"}`;
