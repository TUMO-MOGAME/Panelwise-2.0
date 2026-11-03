// "From the script" in the frame sheet (web.md §4.4 step 3; storyboard.css `.quote.big`, `.cue`):
// each part of the shot's verbatim source, a dialogue part under its speaker, then where it is.

import type { SceneView, ShotView } from "@/lib/api/types";

import { lineColour } from "./lined";
import { sourceBlocks, spanWords } from "./sheet";

export function SourceBlock({ shot, k, scene }: { shot: ShotView; k: number; scene: SceneView | undefined }) {
  return (
    <section aria-labelledby="sheet-source" className="border-b border-rule px-5 py-4">
      <h3 id="sheet-source" className="mt-0 mb-2.5 font-display text-[13px] leading-none font-semibold tracking-[0.14em] text-ink-2 uppercase">
        From the script
      </h3>
      <div className="mb-2 grid gap-2">
        {sourceBlocks(shot).map((part, i) => (
          <div key={i}>
            {/* the speaker sits outside the span, so outside the rule (storyboard.css `.cue`) */}
            {part.speaker && <p className="m-0 mb-1 ml-[15px] font-script text-xs font-bold text-ink-2">{part.speaker}</p>}
            <p className="m-0 border-l-[3px] pl-3 font-script text-[15px] leading-[1.45]" style={{ borderLeftColor: lineColour(k) }}>
              {part.text}
            </p>
          </div>
        ))}
      </div>
      <p className="m-0 text-xs text-ink-2">{spanWords(shot.span, scene)}</p>
    </section>
  );
}
