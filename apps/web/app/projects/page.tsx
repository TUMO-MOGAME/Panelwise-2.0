import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { signOut } from "@/app/(auth)/sign-in/actions";
import { AppBar } from "@/components/AppBar";
import { ProjectsPage } from "@/components/projects/ProjectsPage";
import { Button } from "@/components/ui/button";
import { listProjects } from "@/lib/api/server";
import { currentUser } from "@/lib/supabase/server";

export const metadata: Metadata = { title: "Screenplays — Panelwise" };

export default async function Projects() {
  const user = await currentUser();
  if (!user) redirect("/sign-in");
  const projects = await listProjects(user);
  return (
    <>
      <AppBar
        email={user.email}
        actions={
          <form action={signOut}>
            <Button type="submit" variant="bar">
              Sign out
            </Button>
          </form>
        }
      />
      <ProjectsPage initial={projects} />
    </>
  );
}
