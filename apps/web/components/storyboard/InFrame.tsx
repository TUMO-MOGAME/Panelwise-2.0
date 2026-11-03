// "In frame" in the frame sheet (web.md §4.4 step 4; storyboard.css `.chips`, `.why-shot`): who
// and what the shot puts in frame, where the accepted audit saw each person, and why the shot.

import type { FrameView, ShotView } from "@/lib/api/types";

import { positions } from "./sheet";

const chip = "rounded-xl bg-desk px-2.5 py-[3px] text-sm";

export function InFrame({ shot, frame }: { shot: ShotView; frame: FrameView | undefined }) {
  const at = positions(frame);
  const none = shot.characters.length === 0 && shot.props.length === 0;
  return (
    <section aria-labelledby="sheet-in-frame" className="border-b border-rule px-5 py-4">
      <h3 id="sheet-in-frame" className="mt-0 mb-2.5 font-display text-[13px] leading-none font-semibold tracking-[0.14em] text-ink-2 uppercase">
        In frame
      </h3>
      {none ? (
        <p className="m-0 text-sm font-bold">No one in frame</p>
      ) : (
        <ul className="m-0 flex list-none flex-wrap gap-2 p-0">
          {shot.characters.map((name) => (
            <li key={name} className={`${chip} font-bold`}>
              {name}
              {at[name] && <span className="ml-1 font-normal text-ink-2">{at[name]}</span>}
            </li>
          ))}
          {shot.props.map((name) => (
            <li key={`prop:${name}`} className={chip}>
              {name}
            </li>
          ))}
        </ul>
      )}
      {shot.rationale && <p className="mt-2.5 mb-0 text-sm text-ink-2">{shot.rationale}</p>}
    </section>
  );
}
