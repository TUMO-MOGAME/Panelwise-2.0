// The proxy's session refresh and redirects (web.md §4.0). An optimistic check only: pages and
// route handlers verify the user again (lib/supabase/server.ts), and the API checks the token.

import { createServerClient } from "@supabase/ssr";
import { type NextRequest, NextResponse } from "next/server";

import { supabaseEnv } from "./env";

/** Where a request goes instead, or null to let it through. /api/* is never redirected. */
export function decide(pathname: string, signedIn: boolean): string | null {
  if (pathname === "/api" || pathname.startsWith("/api/")) return null;
  if (pathname === "/") return signedIn ? "/projects" : "/sign-in";
  if (pathname === "/sign-in") return signedIn ? "/projects" : null;
  return signedIn ? null : "/sign-in";
}

type Written = { name: string; value: string; options: object };

export async function updateSession(request: NextRequest): Promise<NextResponse> {
  let response = NextResponse.next({ request });
  let written: Written[] = [];
  let headers: Record<string, string> = {};

  let signedIn = false;
  const env = supabaseEnv();
  if (env) {
    const supabase = createServerClient(env.url, env.key, {
      cookies: {
        getAll: () => request.cookies.getAll(),
        setAll(cookiesToSet, cacheHeaders) {
          // The request carries the refreshed cookies on to the page it renders; the response
          // carries them back to the browser.
          cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value));
          response = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) => response.cookies.set(name, value, options));
          Object.entries(cacheHeaders).forEach(([key, value]) => response.headers.set(key, value));
          written = cookiesToSet;
          headers = cacheHeaders;
        },
      },
    });
    const { data, error } = await supabase.auth.getClaims();
    signedIn = !error && Boolean(data?.claims);
  }

  const to = decide(request.nextUrl.pathname, signedIn);
  if (to === null) return response;

  // A redirect that drops the refreshed cookies would lose the session (web.md §4.0).
  const redirect = NextResponse.redirect(new URL(to, request.url));
  written.forEach(({ name, value, options }) => redirect.cookies.set(name, value, options));
  Object.entries(headers).forEach(([key, value]) => redirect.headers.set(key, value));
  return redirect;
}
