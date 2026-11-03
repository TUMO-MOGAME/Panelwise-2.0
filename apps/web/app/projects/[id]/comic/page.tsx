import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";

import { AppBar } from "@/components/AppBar";
import { ComicPage } from "@/components/comic/ComicPage";
import { COMIC_COPY } from "@/components/comic/comic";
import { UNAVAILABLE } from "@/components/script/copy";
import { Button } from "@/components/ui/button";
import type { ComicView } from "@/lib/api/types";
import { getComic, getProject } from "@/lib/api/server";
import { currentUser } from "@/lib/supabase/server";

export const metadata: Metadata = { title: "Comic — Panelwise" };

export default async function Comic({ params }: { params: Promise<{ id: string }> }) {
  const user = await currentUser();
  if (!user) redirect("/sign-in");
  const { id } = await params;
  const read = await getProject(user, id);
  if (read.kind === "not-found") notFound();
  const unavailable = (
    <>
      <AppBar email={user.email} />
      <p className="mx-auto max-w-[1440px] px-4 py-8 text-ink-2 min-[641px]:px-6">{UNAVAILABLE}</p>
    </>
  );
  if (read.kind === "unavailable") return unavailable;
  const { project } = read;
  // …/comic answers 409 before the plan: only asked once the plan exists (web.md §6).
  let view: ComicView | null = null;
  if (project.shots !== null && project.job.state !== "failed") {
    const got = await getComic(user, project.id);
    if (got.kind === "unavailable") return unavailable;
    if (got.kind === "ok") view = got.view;
  }
  const pdf = view?.comic?.pdf_url;
  return (
    <>
      <AppBar
        email={user.email}
        project={{ id: project.id, title: project.title }}
        tab="comic"
        tools={
          pdf ? (
            <Button asChild variant="bar">
              <a href={pdf} download>
                {COMIC_COPY.download}
              </a>
            </Button>
          ) : undefined
        }
      />
      <ComicPage project={project} view={view} />
    </>
  );
}
