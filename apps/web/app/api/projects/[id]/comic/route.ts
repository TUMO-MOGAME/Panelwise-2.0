// GET and POST /api/projects/[id]/comic: the comic view, and "Make the comic" (web.md §4.5, §6;
// T024 on T064's endpoints). The API's answer passes through unchanged.

import { apiFetch, isDotSegment, projectPath, relay, unauthorized, unreachable } from "@/lib/api/server";
import { currentUser } from "@/lib/supabase/server";

type Context = { params: Promise<{ id: string }> };

async function forward(method: "GET" | "POST", { params }: Context): Promise<Response> {
  const user = await currentUser();
  if (!user) return unauthorized();
  const { id } = await params;
  if (isDotSegment(id)) return Response.json({ error: "not_found" }, { status: 404 });
  try {
    return relay(await apiFetch(`${projectPath(id)}/comic`, user, { method }));
  } catch {
    return unreachable();
  }
}

export function GET(_request: Request, context: Context): Promise<Response> {
  return forward("GET", context);
}

export function POST(_request: Request, context: Context): Promise<Response> {
  return forward("POST", context);
}
