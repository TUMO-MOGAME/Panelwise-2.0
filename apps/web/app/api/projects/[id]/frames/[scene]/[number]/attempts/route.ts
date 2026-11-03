// POST /api/projects/[id]/frames/[scene]/[number]/attempts: "Try another render" (web.md §6, T061).
// The API's answer passes through unchanged: 202 with the frame, 404, 409, 503.

import { apiFetch, isDotSegment, projectPath, relay, unauthorized, unreachable } from "@/lib/api/server";
import { currentUser } from "@/lib/supabase/server";

type Params = { id: string; scene: string; number: string };

export async function POST(_request: Request, { params }: { params: Promise<Params> }): Promise<Response> {
  const user = await currentUser();
  if (!user) return unauthorized();
  const { id, scene, number } = await params;
  if (isDotSegment(id) || !/^\d+$/.test(scene) || !/^\d+$/.test(number)) {
    return Response.json({ error: "not_found" }, { status: 404 });
  }
  try {
    return relay(await apiFetch(`${projectPath(id)}/frames/${scene}/${number}/attempts`, user, { method: "POST" }));
  } catch {
    return unreachable();
  }
}
