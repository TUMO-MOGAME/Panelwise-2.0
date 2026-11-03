import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";

import { AppBar } from "@/components/AppBar";
import { UNAVAILABLE } from "@/components/script/copy";
import { ScriptPage } from "@/components/script/ScriptPage";
import { getProject } from "@/lib/api/server";
import { currentUser } from "@/lib/supabase/server";

export const metadata: Metadata = { title: "Script — Panelwise" };

export default async function Script({ params }: { params: Promise<{ id: string }> }) {
  const user = await currentUser();
  if (!user) redirect("/sign-in");
  const { id } = await params;
  const read = await getProject(user, id);
  if (read.kind === "not-found") notFound();
  if (read.kind === "unavailable") {
    return (
      <>
        <AppBar email={user.email} />
        <p className="mx-auto max-w-[1440px] px-4 py-8 text-ink-2 min-[641px]:px-6">{UNAVAILABLE}</p>
      </>
    );
  }
  const { project } = read;
  return (
    <>
      <AppBar email={user.email} project={{ id: project.id, title: project.title }} tab="script" />
      <ScriptPage project={project} />
    </>
  );
}
