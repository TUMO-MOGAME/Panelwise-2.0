// A frame's image in its 16:9 slot (web.md §4.3; storyboard.css `.media`), shared by the card and
// T045's sheet. Only a passed or warned frame has one: the API sends no URL for any other (§6).

import { Quote } from "@/components/shared/Quote";
import type { ShotView } from "@/lib/api/types";

import { sourceParts } from "./cards";

export const MEDIA_BOX = "aspect-video overflow-hidden border-b border-rule bg-[#f1f3f1]";

/** The verbatim source inside “ ”, each part (one per covered element) on its own line. */
export function SourceText({ shot }: { shot: ShotView }) {
  const parts = sourceParts(shot);
  return (
    <Quote>
      {parts.map((part, i) => (
        <span key={i}>
          {i === 0 && "“"}
          {part}
          {i === parts.length - 1 ? "”" : <br />}
        </span>
      ))}
    </Quote>
  );
}

export function FrameMedia({ url, shot }: { url: string; shot: ShotView }) {
  return (
    <div className={MEDIA_BOX}>
      {/* A signed Storage URL that expires in an hour: not one for next/image to cache. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={url} alt={`Frame for shot ${shot.id}`} className="block size-full object-cover" />
    </div>
  );
}
