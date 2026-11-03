"use client";

// "Try another render" (web.md §4.3; T061, on T021's endpoint): one more audited attempt on a
// withheld frame. Above the card's stretched link (`relative z-10`), so a click reaches it.
// A 401 is asked once more after 1 s; a second one goes to sign in (web.md §4.0, T123).

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import type { FrameView } from "@/lib/api/types";
import { fetchPast401 } from "@/lib/client/signed-out";

export const RETRY_COPY = {
  idle: "Try another render",
  sending: "Starting…",
  unavailable: "Rendering isn't available right now.",
  failed: "That didn't start. Try again in a minute.",
  budgetSpent: "The demo has used this month's model budget.", // T069
  imagesSpent: "The demo has drawn this month's budget of frames.", // T030
} as const;

export function RetryButton({
  projectId,
  sceneIndex,
  number,
  onStarted,
  onMoved,
}: {
  projectId: string;
  sceneIndex: number;
  number: number;
  /** A 202: the frame as the API now has it (rendering, one more attempt). */
  onStarted: (frame: FrameView) => void;
  /** A 409: the frame moved on; the board refetches its frames. */
  onMoved: () => void;
}) {
  const router = useRouter();
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function retry() {
    setSending(true);
    setError(null);
    const url = `/api/projects/${encodeURIComponent(projectId)}/frames/${sceneIndex}/${number}/attempts`;
    try {
      const res = await fetchPast401(url, { method: "POST" });
      if (res.status === 202) {
        // Started either way; a body we can't read just means asking for the frames again.
        const frame = (await res.json().catch(() => null)) as FrameView | null;
        if (frame) onStarted(frame);
        else onMoved();
        return;
      }
      if (res.status === 401) {
        router.push("/sign-in");
        return;
      }
      if (res.status === 409) {
        onMoved();
        return;
      }
      const body = (await res.json().catch(() => null)) as { error?: string } | null;
      if (res.status === 429 && body?.error === "llm_budget_spent") setError(RETRY_COPY.budgetSpent);
      else if (res.status === 429 && body?.error === "image_budget_spent") setError(RETRY_COPY.imagesSpent);
      else setError(res.status === 503 && body?.error === "renderer_unavailable" ? RETRY_COPY.unavailable : RETRY_COPY.failed);
    } catch {
      setError(RETRY_COPY.failed);
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="relative z-10 flex flex-col items-start gap-1.5">
      <Button variant="quiet" className="h-[30px] text-[13px]" disabled={sending} onClick={() => void retry()}>
        {sending ? RETRY_COPY.sending : RETRY_COPY.idle}
      </Button>
      {error && (
        <p role="alert" className="m-0 text-[13px] text-withheld">
          {error}
        </p>
      )}
    </div>
  );
}
