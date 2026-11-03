"use client";

// The frame sheet (web.md §4.4, steps 1–4; storyboard-frame.png): a right-hand sheet over the
// board with the frame, the words it came from and who is in it. Radix Dialog traps focus and
// closes on Esc, ×, or the scrim. The audit (step 5, T061) is absent with no attempts, not empty.

import * as Dialog from "@radix-ui/react-dialog";
import type { ReactNode } from "react";

import { Verdict } from "@/components/shared/Verdict";
import type { FrameView, SceneView, ShotView } from "@/lib/api/types";

import { AuditLog } from "./AuditLog";
import { cardState } from "./cards";
import { PendingMedia } from "./FrameCard";
import { FrameMedia, MEDIA_BOX } from "./FrameMedia";
import { InFrame } from "./InFrame";
import { sheetCamera } from "./sheet";
import { SourceBlock } from "./SourceBlock";

/** A withheld or failed frame in the sheet: its reason only, since "From the script" follows. */
function ReasonPanel({ why, action }: { why: string; action?: ReactNode }) {
  return (
    <div className={MEDIA_BOX}>
      <div className="grid h-full place-content-center justify-items-center gap-3 border border-b-0 border-dashed border-withheld bg-paper px-6 text-center">
        <p className="m-0 text-sm font-bold text-withheld">{why}</p>
        {action}
      </div>
    </div>
  );
}

export function FrameSheet({
  shot,
  k,
  frame,
  scene,
  onClose,
  onCloseFocus,
  retry,
}: {
  shot: ShotView;
  k: number;
  frame: FrameView | undefined;
  scene: SceneView | undefined;
  onClose: () => void;
  /** Where focus goes once the sheet has closed: the card that opened it. */
  onCloseFocus: () => void;
  /** "Try another render", for a withheld frame (null otherwise). */
  retry: ReactNode;
}) {
  const { media, verdict } = cardState(frame);
  return (
    <Dialog.Root open onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        {/* z-50: above a card's `relative z-10` Try another render, which painted through the sheet */}
        <Dialog.Overlay data-sheet-scrim className="fixed inset-0 z-50 bg-[rgb(26_34_44/0.35)]" />
        <Dialog.Content
          aria-describedby={undefined}
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            onCloseFocus();
          }}
          className="fixed inset-y-0 right-0 z-50 w-[min(520px,100vw)] overflow-auto bg-paper shadow-[-18px_0_40px_-20px_rgb(26_34_44/0.5)] focus:outline-none"
        >
          <header className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-rule px-5 py-4">
            <Dialog.Title className="m-0 font-display text-[28px] leading-none font-extrabold">
              {/* named "Shot 1.4" for assistive tech; the eye reads the id alone */}
              <span className="sr-only">Shot {shot.id}</span>
              <span aria-hidden>{shot.id}</span>
            </Dialog.Title>
            <span className="text-[13px] text-ink-2">{sheetCamera(shot)}</span>
            {verdict && (
              <span className="ml-auto">
                <Verdict tone={verdict.tone}>{verdict.label}</Verdict>
              </span>
            )}
            <Dialog.Close
              aria-label="Close"
              className={`cursor-pointer border-0 bg-transparent px-1 text-[26px] leading-none text-ink-2 ${verdict ? "" : "ml-auto"}`}
            >
              ×
            </Dialog.Close>
          </header>
          {media.kind === "image" && <FrameMedia url={media.url} shot={shot} />}
          {media.kind === "pending" && <PendingMedia text={media.text} busy={media.busy} />}
          {media.kind === "withheld" && <ReasonPanel why={media.why} action={retry} />}
          {media.kind === "failed" && <ReasonPanel why={media.why} action={retry} />}
          <SourceBlock shot={shot} k={k} scene={scene} />
          <InFrame shot={shot} frame={frame} />
          <AuditLog audits={frame?.audits ?? []} />
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
