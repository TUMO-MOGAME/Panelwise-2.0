// POST /api/projects (the upload) and GET /api/projects (the list's poll): web.md §4.1a.
// Both proxy the API server-side with the user's token and return its answer unchanged.

import { apiFetch, relay, unauthorized, unreachable } from "@/lib/api/server";
import { currentUser } from "@/lib/supabase/server";

export async function POST(request: Request): Promise<Response> {
  const user = await currentUser();
  if (!user) return unauthorized();

  // The body streams through; the API reads Content-Length before it reads the body (web.md §6).
  const headers = new Headers();
  for (const name of ["Content-Type", "Content-Length"]) {
    const value = request.headers.get(name);
    if (value !== null) headers.set(name, value);
  }
  try {
    const res = await apiFetch("/projects", user, {
      method: "POST",
      headers,
      body: request.body,
      duplex: "half",
    } as RequestInit);
    return relay(res);
  } catch {
    return unreachable();
  }
}

export async function GET(): Promise<Response> {
  const user = await currentUser();
  if (!user) return unauthorized();
  try {
    return relay(await apiFetch("/projects", user));
  } catch {
    return unreachable();
  }
}
