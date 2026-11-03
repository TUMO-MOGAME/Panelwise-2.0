// What was found, by kind: every name with every quote it came from (web.md §4.2; script.css
// `.entities`). Dropped entities never reach here: the API leaves them out (SPEC US1).

import { Quote } from "@/components/shared/Quote";
import { SpanRef } from "@/components/shared/SpanRef";
import type { EntityView, SceneView } from "@/lib/api/types";
import { cn } from "@/lib/utils";

import { type EntitySectionData, entityTag, entityWhere } from "./entities";

function EntityCard({ entity, scenes, id, small }: { entity: EntityView; scenes: readonly SceneView[]; id: string; small: boolean }) {
  const tag = entityTag(entity);
  const where = entityWhere(entity, scenes);
  return (
    <article aria-labelledby={id} className={cn("bg-paper px-4 py-3.5 shadow-page", small ? "m-0" : "mb-3.5")}>
      <header className="flex flex-wrap items-baseline gap-3">
        <h3 id={id} className={cn("m-0 font-body font-bold", small ? "text-[15px]" : "text-lg")}>
          {entity.name}
        </h3>
        {tag && (
          <span className="rounded-[10px] bg-pencil-soft px-2 py-0.5 text-xs font-bold text-pencil">{tag}</span>
        )}
        {where && <span className="ml-auto text-[13px] text-ink-2">{where}</span>}
      </header>
      <ul className="m-0 mt-2.5 grid list-none gap-1 p-0">
        {entity.quotes.map((quote, i) => (
          <li key={i}>
            <Quote>“{quote.text}”</Quote> <SpanRef span={quote.span} />
          </li>
        ))}
      </ul>
    </article>
  );
}

export function EntitySection({ section, scenes }: { section: EntitySectionData; scenes: readonly SceneView[] }) {
  const small = section.kind !== "character";
  const cards = section.entities.map((entity, i) => (
    <EntityCard key={`${entity.name}-${i}`} entity={entity} scenes={scenes} id={`${section.kind}-${i}`} small={small} />
  ));
  return (
    <>
      <h2 className="m-0 mt-7 mb-3 border-b-2 border-ink pb-1.5 font-display text-[22px] leading-[1.1] font-extrabold tracking-[0.03em] uppercase first:mt-0">
        {section.title}
      </h2>
      {small ? <div className="grid grid-cols-[repeat(auto-fill,minmax(230px,1fr))] gap-3.5">{cards}</div> : cards}
    </>
  );
}
