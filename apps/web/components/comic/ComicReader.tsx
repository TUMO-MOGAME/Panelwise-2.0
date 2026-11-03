"use client";

// The comic reader (web.md §4.5; comic.png, comic-phone.png): one lettered page at a time, the
// API's own PNG, with hit areas over it from the layout's rects. Selecting any bubble or caption,
// on the page or in the list, traces it and shows its verbatim script line, span and shot: the
// lined script's promise, carried into the comic.

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { uploadedAt } from "@/components/projects/rowState";
import { Quote } from "@/components/shared/Quote";
import { SpanRef, spanText } from "@/components/shared/SpanRef";
import { Button } from "@/components/ui/button";
import type { ComicMade, ComicView } from "@/lib/api/types";
import { cn } from "@/lib/utils";

import { COMIC_COPY, factsLine, hitLabel, parsePage, placed, type Selected, sameSelection, whoWords } from "./comic";

const EYEBROW = "m-0 font-display text-[13px] leading-none font-semibold tracking-[0.14em] text-ink-2 uppercase";

function typing(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
}

export function ComicReader({ projectId, title, comic: initial }: { projectId: string; title: string; comic: ComicMade }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const [comic, setComic] = useState(initial);
  // Both belong to one page: a page change by any route (Next, the keys, a link, the URL) leaves them behind.
  const [selection, setSelection] = useState<(Selected & { page: number }) | null>(null);
  const [brokenPage, setBrokenPage] = useState<number | null>(null);
  const [refetched, setRefetched] = useState(false);

  const count = comic.pages.length;
  const raw = params.get("page");
  const n = parsePage(raw, count);
  const page = comic.pages[n - 1]!;
  const selected: Selected | null = selection?.page === n ? selection : null;
  const broken = brokenPage === n;
  const setSelected = (at: Selected | null) => setSelection(at && { ...at, page: n });
  const panels = comic.pages.reduce((sum, p) => sum + p.panels.length, 0);

  useEffect(() => {
    if (raw !== String(n)) router.replace(`${pathname}?page=${n}`, { scroll: false });
  }, [raw, n, pathname, router]);
  useEffect(() => {
    if (n < count) new Image().src = comic.pages[n]!.image_url; // the next page, ready
  }, [n, count, comic]);

  const go = useCallback(
    (to: number) => {
      router.replace(`${pathname}?page=${to}`, { scroll: false });
      window.scrollTo(0, 0);
    },
    [pathname, router],
  );

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (typing(event.target) || event.defaultPrevented) return;
      // Alt/Cmd + arrow is the browser's back and forward: never also turn the page.
      if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
      if (event.key === "ArrowLeft" && n > 1) go(n - 1);
      else if (event.key === "ArrowRight" && n < count) go(n + 1);
      else if (event.key === "Escape") setSelection(null);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [n, count, go]);

  async function imageFailed() {
    if (refetched) {
      setBrokenPage(n);
      return;
    }
    setRefetched(true); // signed URLs expire: ask for fresh ones once
    try {
      const res = await fetch(`/api/projects/${encodeURIComponent(projectId)}/comic`, { cache: "no-store" });
      const view = res.ok ? ((await res.json()) as ComicView) : null;
      if (view?.comic) setComic(view.comic);
      else setBrokenPage(n);
    } catch {
      setBrokenPage(n);
    }
  }

  const toggle = (at: Selected) => setSelected(sameSelection(selected, at) ? null : at);
  const traced = selected && page.panels[selected.panel]?.lettering[selected.item];
  const tracedPanel = selected && page.panels[selected.panel];
  const storyboardHref = (shotId: string) => `/projects/${encodeURIComponent(projectId)}/storyboard?shot=${shotId}`;

  return (
    <main className="mx-auto grid max-w-[1440px] items-start gap-x-10 gap-y-4 px-4 pt-4 pb-12 min-[901px]:grid-cols-[auto_340px] min-[901px]:grid-rows-[auto_1fr] min-[901px]:justify-center min-[901px]:px-6 min-[901px]:pt-6 min-[901px]:pb-16">
      <div className="min-[901px]:col-start-2 min-[901px]:row-start-1">
        <p className={EYEBROW}>{COMIC_COPY.eyebrow}</p>
        <h1 className="mt-1.5 mb-1 font-display text-[32px] leading-none font-extrabold tracking-[0.03em] uppercase min-[901px]:text-[40px]">
          {title}
        </h1>
        <p className="m-0 text-sm text-ink-2">
          {count} {count === 1 ? "page" : "pages"} · {panels} {panels === 1 ? "panel" : "panels"} · made{" "}
          {/* The viewer's time zone: the server's render may differ, so React keeps the browser's. */}
          <span suppressHydrationWarning>{uploadedAt(comic.made_at)}</span>
        </p>
      </div>

      <div className="grid justify-items-center gap-3.5 min-[901px]:col-start-1 min-[901px]:row-span-2 min-[901px]:row-start-1">
        <figure
          aria-label={`Page ${n} of ${count}`}
          className="relative m-0 w-full bg-white shadow-page min-[901px]:h-[min(calc(100vh-154px),1100px)] min-[901px]:w-auto"
          style={{ aspectRatio: `${page.width} / ${page.height}` }}
        >
          {broken ? (
            <p className="m-0 p-6 text-sm text-ink-2">{COMIC_COPY.pageFailed}</p>
          ) : (
            // A signed Storage URL that expires: not one for next/image to cache (as FrameMedia).
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={page.image_url}
              alt={`Comic page ${n} of ${count}. Its lettering is listed beside the page.`}
              className="block h-full w-full"
              onError={() => void imageFailed()}
              onLoad={() => setRefetched(false)} // a later expiry gets its own fresh URLs
            />
          )}
          {!broken &&
            page.panels.map((panel, p) => (
              <div key={panel.shot_id} className="contents">
                <Link
                  href={storyboardHref(panel.shot_id)}
                  aria-label={`Shot ${panel.shot_id} in the storyboard${panel.withheld ? ", frame not shown" : ""}`}
                  className="group absolute block no-underline hover:bg-[rgb(44_110_158/0.07)] hover:outline-2 hover:-outline-offset-2 hover:outline-pencil hover:outline-dashed focus-visible:bg-[rgb(44_110_158/0.07)] focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-pencil focus-visible:outline-dashed"
                  style={placed(panel.rect, page)}
                >
                  <span className="absolute right-1.5 bottom-1.5 rounded-paper bg-pencil px-1.5 py-0.5 font-body text-xs font-bold text-white opacity-0 group-hover:opacity-100 group-focus-visible:opacity-100">
                    Shot {panel.shot_id}
                  </span>
                </Link>
                {panel.lettering.map((item, k) => {
                  const on = sameSelection(selected, { panel: p, item: k });
                  return (
                    <button
                      key={k}
                      type="button"
                      aria-pressed={on}
                      aria-label={hitLabel(item)}
                      onClick={() => toggle({ panel: p, item: k })}
                      className={cn(
                        "absolute cursor-pointer border-0 bg-transparent p-0 hover:outline-2 hover:outline-offset-[3px] hover:outline-pencil hover:outline-dashed",
                        item.kind === "scene" || item.kind === "voice_over" ? "rounded-none" : "rounded-[22px]",
                        on && "outline-3 outline-offset-4 outline-pencil outline-solid hover:outline-solid",
                      )}
                      style={placed(item.rect, page)}
                    >
                      {on && (
                        <span className="absolute bottom-[calc(100%+7px)] -left-1 rounded-paper bg-pencil px-1.5 py-0.5 font-body text-[11px] font-bold whitespace-nowrap text-white">
                          {spanText(item.span)}
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>
            ))}
        </figure>
        <nav aria-label="Pages" className="flex items-center gap-3 text-sm font-medium text-ink-2">
          <Button variant="quiet" className="h-8 px-3" disabled={n <= 1} onClick={() => go(n - 1)}>
            {COMIC_COPY.previous}
          </Button>
          <span>
            Page <b className="text-ink">{n}</b> of {count}
          </span>
          <Button variant="quiet" className="h-8 px-3" disabled={n >= count} onClick={() => go(n + 1)}>
            {COMIC_COPY.next}
          </Button>
        </nav>
      </div>

      <aside aria-label="Lettering" className="grid gap-4 min-[901px]:sticky min-[901px]:top-4 min-[901px]:col-start-2 min-[901px]:row-start-2">
        <section aria-live="polite" className="border-l-4 border-pencil bg-paper px-4 pt-3.5 pb-4 shadow-page">
          <p className={cn(EYEBROW, "mb-2.5")}>{COMIC_COPY.traced}</p>
          {traced && tracedPanel ? (
            <>
              {traced.cue && <p className="m-0 pl-[9ch] font-script text-sm">{traced.cue}</p>}
              <p className="mt-0.5 mb-2.5">
                <Quote>{traced.text}</Quote>
              </p>
              <p className="mt-0 mb-3 text-[13px] text-ink-2">{factsLine(traced, tracedPanel.shot_id)}</p>
              <Button asChild variant="quiet">
                <Link href={storyboardHref(tracedPanel.shot_id)}>Open shot {tracedPanel.shot_id} in the storyboard</Link>
              </Button>
            </>
          ) : (
            <p className="m-0 text-sm text-ink-2">{COMIC_COPY.traceEmpty}</p>
          )}
        </section>
        <section className="bg-paper pt-3.5 pb-1.5 shadow-page">
          <p className={cn(EYEBROW, "mx-4 mb-2")}>{COMIC_COPY.lettering}</p>
          <ol className="m-0 list-none p-0">
            {page.panels.flatMap((panel, p) =>
              panel.lettering.map((item, k) => {
                const on = sameSelection(selected, { panel: p, item: k });
                return (
                  <li key={`${p}-${k}`} className="border-t border-rule">
                    <button
                      type="button"
                      aria-pressed={on}
                      onClick={() => toggle({ panel: p, item: k })}
                      className={cn(
                        "grid w-full cursor-pointer grid-cols-[1fr_auto] gap-x-2.5 gap-y-0.5 border-0 bg-transparent px-4 py-2 text-left text-ink",
                        on && "bg-pencil-soft shadow-[inset_3px_0_0_var(--color-pencil)]",
                      )}
                    >
                      <span className="font-body text-xs font-bold tracking-[0.04em] text-ink-2 uppercase">
                        {whoWords(item)}
                      </span>
                      <span className="col-start-1 font-script text-[13px] leading-[1.45]">{item.text}</span>
                      <span className="col-start-2 row-span-2 row-start-1 self-center">
                        <SpanRef span={item.span} />
                      </span>
                    </button>
                  </li>
                );
              }),
            )}
          </ol>
        </section>
      </aside>
    </main>
  );
}
