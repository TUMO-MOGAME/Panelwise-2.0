// The scenes column (web.md §4.2; script.css `.scenes`).

import Link from "next/link";

import { Button } from "@/components/ui/button";
import type { SceneView } from "@/lib/api/types";

import { sceneDetail } from "./scenes";

export function SceneIndex({ scenes, storyboard }: { scenes: readonly SceneView[]; storyboard: string }) {
  return (
    <nav aria-label="Scenes" data-area="scenes" className="[grid-area:scenes] min-[1101px]:sticky min-[1101px]:top-4">
      <h2 className="m-0 mb-2.5 font-display text-lg leading-[1.1] font-extrabold tracking-[0.03em] uppercase">
        Scenes
      </h2>
      <ol className="m-0 mb-[18px] grid list-none gap-2.5 p-0">
        {scenes.map((scene, i) => (
          <li key={scene.index} className="grid grid-cols-[28px_1fr] gap-x-2 gap-y-0.5">
            <b className="row-span-2 font-display text-[22px] leading-none font-extrabold text-ink-2">{scene.number}</b>
            <span className="font-script text-[13px] font-bold">{scene.heading}</span>
            <em className="text-xs text-ink-2 not-italic">{sceneDetail(scenes, i)}</em>
          </li>
        ))}
      </ol>
      <Button asChild>
        <Link href={storyboard}>Open the storyboard</Link>
      </Button>
    </nav>
  );
}
