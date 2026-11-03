// GET /api/projects/[id]/storyboard/pdf: the storyboard PDF's signed URL (web.md §4.3, §6; T027
// on its API endpoint). JSON, not a redirect: the button fetches it, and a fetch can't follow a
// redirect to Storage's origin. The API's answer passes through unchanged.

import { apiFetch, isDotSegment, projectPath, relay, unauthorized, unreachable } from "@/lib/api/server";
import { currentUser } from "@/lib/supabase/server";

type Context = { params: Promise<{ id: string }> };

export async function GET(_request: Request, { params }: Context): Promise<Response> {
  const user = await currentUser();
  if (!user) return unauthorized();
  const { id } = await params;
  if (isDotSegment(id)) return Response.json({ error: "not_found" }, { status: 404 });
  try {
    return relay(await apiFetch(`${projectPath(id)}/storyboard/pdf`, user));
  } catch {
    return unreachable();
  }
}
