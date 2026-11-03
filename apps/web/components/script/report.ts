// The report column's numbers and model line (web.md §4.2, §6 copy).

import type { ReportView } from "@/lib/api/types";

export const scoreText = (score: number) => score.toFixed(2);

/** A score card's left edge: pass at 1.00, warn below. */
export const scoreEdge = (score: number): "pass" | "warn" => (score >= 1 ? "pass" : "warn");

export function faithfulnessCopy(r: ReportView): string {
  return `${r.entities_grounded} of ${r.entities_proposed} things the model named are in the script. ${r.quotes_located} of ${r.quotes_proposed} quotes found on the page.`;
}

export function recallCopy(r: ReportView): string {
  return `${r.cues_found_by_model} of ${r.cues_total} speaking characters found by the model. A speaker it misses is still added from their dialogue cues.`;
}

// The models' display names (web.md §4.2); any other id is shown as it is.
const MODEL_NAMES: Record<string, string> = {
  "nvidia/Nemotron-3_5-Lightning": "Nemotron 3.5 Lightning",
  "nvidia/nemotron-3-super-120b-a12b": "Nemotron 3 Super",
};

/** A model's display name; an unknown id as it is, or (`short`) the part after its last "/". */
export function modelName(id: string, { short = false } = {}): string {
  return MODEL_NAMES[id] ?? (short ? id.slice(id.lastIndexOf("/") + 1) : id);
}

const tokens = new Intl.NumberFormat("en-GB");

export function modelLine(r: ReportView): string {
  const names = r.models.map((id) => modelName(id));
  const usage = `${tokens.format(r.prompt_tokens)} tokens in, ${tokens.format(r.completion_tokens)} out`;
  return [...names, usage].join(" · ");
}
