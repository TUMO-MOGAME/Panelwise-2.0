// The scenes column's detail lines (web.md §4.2, script.png).

import type { SceneView } from "@/lib/api/types";

const count = (n: number, one: string) => `${n} ${one}${n === 1 ? "" : "s"}`;

/** "EARLY MORNING" → "Early morning". */
function sentenceCase(text: string): string {
  const lower = text.toLowerCase();
  return lower.charAt(0).toUpperCase() + lower.slice(1);
}

/**
 * The scene whose own heading set a carried time: the nearest earlier scene with a time it didn't
 * carry. resolve_times carries the clock from there (app/script/scene_time.py).
 */
export function carriedFrom(scenes: readonly SceneView[], i: number): SceneView | null {
  if (!scenes[i]?.time_carried) return null;
  for (let j = i - 1; j >= 0; j--) {
    if (!scenes[j].time_carried && scenes[j].time_of_day !== null) return scenes[j];
  }
  return null;
}

export function sceneDetail(scenes: readonly SceneView[], i: number): string {
  const scene = scenes[i];
  const parts: string[] = [];
  const source = carriedFrom(scenes, i);
  if (source && scene.time_of_day) {
    parts.push(`${sentenceCase(scene.time_of_day)}, carried from scene ${source.number}`);
  }
  parts.push(i === 0 ? count(scene.elements, "action and dialogue block") : count(scene.elements, "block"));
  if (scene.shots !== null) parts.push(count(scene.shots, "shot"));
  return parts.join(" · ");
}
