// The frame board (web.md §4.3; storyboard.css `.scene`, `.grid`): a heading per scene, then a
// card per shot in script order.

import type { Dispatch, ReactNode, SetStateAction } from "react";

import type { FrameView, SceneView, ShotView } from "@/lib/api/types";

import { FrameCard } from "./FrameCard";
import { retryable } from "./board";

export function FrameBoard({
  scenes,
  shots,
  frames,
  highlight,
  onHighlight,
  hrefFor,
  onOpen,
  retryFor,
}: {
  scenes: readonly SceneView[];
  shots: readonly ShotView[];
  frames: readonly FrameView[];
  highlight: string | null;
  onHighlight: Dispatch<SetStateAction<string | null>>;
  hrefFor: (id: string) => string;
  onOpen: (id: string) => void;
  retryFor: (shot: ShotView) => ReactNode;
}) {
  const byShot = new Map(frames.map((f) => [f.shot_id, f]));
  const order = new Map(shots.map((s, k) => [s.id, k]));
  return (
    <section aria-label="Frames">
      {scenes.map((scene) => {
        const here = shots.filter((s) => s.scene_index === scene.index);
        if (here.length === 0) return null;
        return (
          <div key={scene.index} className="mb-9 last:mb-0">
            <h2 className="mt-1 mb-3.5 flex items-baseline gap-3 border-b-2 border-ink pb-2 font-display text-xl leading-[1.1] font-extrabold tracking-[0.03em] uppercase">
              <span className="text-sm text-ink-2">{scene.number}</span>
              {scene.heading}
            </h2>
            <div className="grid grid-cols-[repeat(auto-fill,minmax(280px,1fr))] gap-[22px] max-[640px]:grid-cols-1">
              {here.map((shot) => (
                <FrameCard
                  key={shot.id}
                  shot={shot}
                  k={order.get(shot.id) ?? 0}
                  frame={byShot.get(shot.id)}
                  on={shot.id === highlight}
                  onHighlight={onHighlight}
                  href={hrefFor(shot.id)}
                  onOpen={onOpen}
                  retry={retryable(byShot.get(shot.id)?.state) ? retryFor(shot) : null}
                />
              ))}
            </div>
          </div>
        );
      })}
    </section>
  );
}
