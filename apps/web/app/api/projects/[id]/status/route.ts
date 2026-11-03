// GET /api/projects/[id]/status: the project's summary, for the script page's poll and the
// storyboard's (web.md §4.2, §4.3). The API's 404 and every other answer pass through.

import { apiFetch, isDotSegment, projectPath, unauthorized, unreachable } from "@/lib/api/server";
import type { Project, ProjectSummary } from "@/lib/api/types";
import { currentUser } from "@/lib/supabase/server";

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }): Promise<Response> {
  const user = await currentUser();
  if (!user) return unauthorized();
  const { id } = await params;
  if (isDotSegment(id)) return Response.json({ error: "not_found" }, { status: 404 });
  let res: Response;
  try {
    res = await apiFetch(projectPath(id), user);
  } catch {
    return unreachable();
  }
  if (!res.ok) return Response.json(await res.json().catch(() => null), { status: res.status });
  // The page's stage columns are large; the poll needs only the summary.
  const { scene_list, entities, report, ...summary } = (await res.json()) as Project;
  void scene_list;
  void entities;
  void report;
  return Response.json(summary satisfies ProjectSummary);
}
