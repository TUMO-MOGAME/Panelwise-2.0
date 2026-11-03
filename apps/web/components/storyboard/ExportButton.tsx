"use client";

// Export PDF, in the bar (web.md §4.3; storyboard.png; T027). Disabled until the storyboard job is
// done and every frame has settled; then it asks for the PDF (built on demand) and opens its
// signed URL. A frame that went live again since the page was drawn answers 409, which says why.
// A 401 is asked once more after 1 s; a second one goes to sign in (web.md §4.0, T123).

import { useRouter } from "next/navigation";
import { useId, useState } from "react";

import { Button } from "@/components/ui/button";
import type { StoryboardPdfView } from "@/lib/api/types";
import { fetchPast401 } from "@/lib/client/signed-out";

export const EXPORT_COPY = {
  idle: "Export PDF",
  busy: "Making the PDF…",
  waiting: "Available when every frame has settled",
  failed: "The PDF couldn't be made. Try again in a minute.",
} as const;

export function ExportButton({
  projectId,
  ready,
  go = (url) => window.location.assign(url),
}: {
  projectId: string;
  /** web.md §4.3's rule (`canExport`), as the page last read it. */
  ready: boolean;
  /** Opens the signed URL; a test passes its own. */
  go?: (url: string) => void;
}) {
  const router = useRouter();
  const why = useId();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function exportPdf() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetchPast401(`/api/projects/${encodeURIComponent(projectId)}/storyboard/pdf`, { cache: "no-store" });
      if (res.status === 401) {
        router.push("/sign-in");
        return;
      }
      if (res.status === 409) {
        setError(EXPORT_COPY.waiting);
        return;
      }
      const body = res.ok ? ((await res.json().catch(() => null)) as StoryboardPdfView | null) : null;
      if (body?.pdf_url) go(body.pdf_url);
      else setError(EXPORT_COPY.failed);
    } catch {
      setError(EXPORT_COPY.failed);
    } finally {
      setBusy(false);
    }
  }

  if (!ready) {
    // A disabled button takes no focus, so the reason is also its description, not only a tooltip.
    return (
      <span title={EXPORT_COPY.waiting}>
        <Button variant="bar" disabled aria-describedby={why}>
          {EXPORT_COPY.idle}
        </Button>
        <span id={why} className="sr-only">
          {EXPORT_COPY.waiting}
        </span>
      </span>
    );
  }
  return (
    <span className="relative inline-flex items-center">
      <Button variant="bar" disabled={busy} onClick={() => void exportPdf()}>
        {busy ? EXPORT_COPY.busy : EXPORT_COPY.idle}
      </Button>
      {error && (
        <span
          role="alert"
          className="absolute top-full right-0 mt-1.5 w-max max-w-65 rounded-sm bg-paper px-2 py-1 text-[12px] text-withheld shadow-sm"
        >
          {error}
        </span>
      )}
    </span>
  );
}
