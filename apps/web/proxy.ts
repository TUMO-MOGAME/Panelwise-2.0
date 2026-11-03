// Next.js 16's proxy (formerly middleware): refreshes the Supabase session and redirects pages
// by it (web.md §4.0). Route handlers under /api answer a signed-out caller themselves.

import type { NextRequest } from "next/server";

import { updateSession } from "@/lib/supabase/proxy";

export async function proxy(request: NextRequest) {
  return updateSession(request);
}

export const config = {
  // Everything but build assets, image optimisation, the favicon and any path with a file
  // extension; /api/* stays in so the refreshed cookie reaches route handlers.
  matcher: ["/((?!_next/static|_next/image|favicon\\.ico|.*\\.[a-zA-Z0-9]+$).*)"],
};
