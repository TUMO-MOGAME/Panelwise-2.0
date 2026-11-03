// A 401 while still signed in (web.md §4.0, T123): when the proxy's refresh can't reach Supabase
// Auth, a request answers 401 though the session cookie survives, and the next request refreshes
// it. So the browser goes to /sign-in on the second 401 in a row, never the first.

export const RETRY_401_MS = 1000;

/** A poller's 401s in a row: saw(status) is true when the browser should go to /sign-in. */
export function unauthorizedStreak(): { saw(status: number): boolean } {
  let count = 0;
  return {
    saw(status) {
      count = status === 401 ? count + 1 : 0;
      return count >= 2;
    },
  };
}

/** fetch(input, init); when that answers 401, wait RETRY_401_MS and fetch(input, init) once more. */
export async function fetchPast401(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const first = await fetch(input, init);
  if (first.status !== 401) return first;
  await new Promise((resolve) => setTimeout(resolve, RETRY_401_MS));
  return fetch(input, init);
}
