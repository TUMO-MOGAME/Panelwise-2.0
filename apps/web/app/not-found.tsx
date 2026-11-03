// The not-found page (web.md §4.2, script-states.png): a project the API answers 404 for, or any
// unknown route. It doesn't say which: missing and someone else's are the same answer (§6).

import Link from "next/link";

import { AppBar } from "@/components/AppBar";
import { Button } from "@/components/ui/button";
import { currentUser } from "@/lib/supabase/server";

export default async function NotFound() {
  const user = await currentUser();
  return (
    <>
      <AppBar email={user?.email ?? null} />
      <main className="grid place-items-center px-4 py-[72px]">
        <section className="w-full max-w-[440px] border-t-4 border-line-1 bg-paper p-7 shadow-page">
          <h1 className="m-0 font-display text-[30px] leading-none font-extrabold tracking-[0.03em] uppercase">
            This screenplay isn&apos;t here
          </h1>
          <p className="mt-2.5 mb-0 text-ink-2">It may have been deleted, or it belongs to another account.</p>
          <Button asChild variant="quiet" className="mt-5">
            <Link href="/projects">Back to your screenplays</Link>
          </Button>
        </section>
      </main>
    </>
  );
}
