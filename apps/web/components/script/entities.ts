// What was found, by kind (web.md §4.2): sections, source tags and where each thing appears.

import type { EntityView, SceneView } from "@/lib/api/types";

const SECTIONS = [
  { kind: "character", title: "Characters" },
  { kind: "prop", title: "Props" },
  { kind: "location", title: "Locations" },
] as const;

export interface EntitySectionData {
  kind: EntityView["kind"];
  title: string;
  entities: EntityView[];
}

/** Characters, props, locations, each in extraction order; a kind with nothing is left out. */
export function entitySections(entities: readonly EntityView[]): EntitySectionData[] {
  return SECTIONS.map(({ kind, title }) => ({
    kind,
    title,
    entities: entities.filter((e) => e.kind === kind),
  })).filter((section) => section.entities.length > 0);
}

const TAGS: Record<EntityView["source"], string> = {
  model: "Found by the model",
  cue: "Added from dialogue cues",
  heading: "From the heading",
};

/** Props carry no tag: only the model names props, so it would say nothing. */
export function entityTag(entity: EntityView): string | null {
  return entity.kind === "prop" ? null : TAGS[entity.source];
}

/** "Scene 1" / "Scenes 1, 2, 3" by printed number; none for a location, whose quote is its heading. */
export function entityWhere(entity: EntityView, scenes: readonly SceneView[]): string | null {
  if (entity.kind === "location" || entity.scenes.length === 0) return null;
  const numbers = entity.scenes.map((index) => scenes[index]?.number ?? String(index + 1));
  return `${numbers.length === 1 ? "Scene" : "Scenes"} ${numbers.join(", ")}`;
}
