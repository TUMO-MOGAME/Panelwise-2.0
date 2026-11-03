// GET /api/projects/[id]/frames: the project's frames, for the storyboard's poll (web.md §4.3).
// The API's answer passes through unchanged, its 404 and 503 included.

import { apiFetch, isDotSegment, projectPath, relay, unauthorized, unreachable } from "@/lib/api/server";
import { currentUser } from "@/lib/supabase/server";

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }): Promise<Response> {
  const user = await currentUser();
  if (!user) return unauthorized();
  const { id } = await params;
  if (isDotSegment(id)) return Response.json({ error: "not_found" }, { status: 404 });
  try {
    return relay(await apiFetch(`${projectPath(id)}/frames`, user));
  } catch {
    return unreachable();
  }
}
