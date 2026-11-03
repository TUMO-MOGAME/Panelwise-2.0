import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";

import { AppBar } from "@/components/AppBar";
import { UNAVAILABLE } from "@/components/script/copy";
import { canExport } from "@/components/storyboard/board";
import { ExportButton } from "@/components/storyboard/ExportButton";
import { type Board, StoryboardPage } from "@/components/storyboard/StoryboardPage";
import { getBoard, getProject } from "@/lib/api/server";
import { currentUser } from "@/lib/supabase/server";

export const metadata: Metadata = { title: "Storyboard — Panelwise" };

export default async function Storyboard({ params }: { params: Promise<{ id: string }> }) {
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
  // The plan's lists exist only once planning has finished: …/lines and …/shots 409 before it.
  let board: Board | null = null;
  if (project.shots !== null && project.job.state !== "failed") {
    const got = await getBoard(user, project.id);
    if (got.kind === "unavailable") return unavailable;
    board = { lines: got.lines, shots: got.shots, frames: got.frames };
  }
  return (
    <>
      <AppBar
        email={user.email}
        project={{ id: project.id, title: project.title }}
        tab="storyboard"
        tools={<ExportButton projectId={project.id} ready={canExport(project)} />}
      />
      <StoryboardPage project={project} board={board} />
    </>
  );
}
