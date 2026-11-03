// GET /api/health: is the web app up, and can it reach the API?
// Docker's healthcheck reads this. The contract is TASKS.md T002.

const API_TIMEOUT_MS = 3000;

const unreachable = () =>
  Response.json({ web: "ok", api: null, error: "api unreachable" }, { status: 502 });

export async function GET(): Promise<Response> {
  const apiUrl = process.env.API_URL ?? "http://localhost:8000";

  let res: Response;
  let body: unknown;
  try {
    res = await fetch(`${apiUrl}/api/v1/health`, {
      cache: "no-store",
      signal: AbortSignal.timeout(API_TIMEOUT_MS),
    });
    body = await res.json();
  } catch {
    return unreachable();
  }

  return Response.json({ web: "ok", api: body }, { status: res.status });
}
