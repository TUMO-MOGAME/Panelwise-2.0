# T123: a 401 while still signed in (2026-10-19)

Tumo (via Claude), on Tumo's machine, against the local stack on main @ `ba95414` (web and API in
compose, the shared Supabase project's Auth). Free: Supabase Auth calls only, no drawings, no tokens.
Each probe makes a throwaway user with the secret key and deletes it at the end. The web's session
cookie is forged the way `@supabase/ssr` 0.12.7 writes it (`base64-` + base64url of the session
JSON, chunked at 3,180 characters). `expires_at` is set in the past so the proxy must refresh. Refresh
tokens are printed only as an 8-character hash. Each probe calls `GET /api/projects` on the web. That
route answers 200 or 401 by the session alone, so no project is needed.
Design: [docs/design/web.md](../../../docs/design/web.md) §4.0 *A 401 while signed in*, §8, §9 T123.

Run in the API container (it has the Supabase settings; `web` resolves there):
`cd /srv/api && PYTHONPATH=/srv/api .venv/bin/python /tmp/<probe>.py`.

## 1. Reusing a refresh token is not the cause (`probe_401.py`, `probe_401c.py`)

| Case | Answer |
|---|---|
| E1 fresh session | 200, no refresh (the first request took 11.6 s: the local web warming up) |
| E2 expired access token, 5 polls at once | 5 × 200 in 0.33–0.50 s, **all handed the same new refresh token** |
| E3 the old cookie again, 3 s later | 200, the same new token |
| E4 the old cookie again, 15 s later | 200, the same new token |
| E5 the token E2 handed back | 200 (valid), and it refreshes |
| E6 a poll 0.5 s after a refresh, still carrying the old cookie | 200, the same new token |
| E7 the grandparent cookie (two rotations back), 2 s later | 200 |
| **E8 the grandparent cookie, 15 s later** | **401, and the response clears the cookie** (`sb-…-auth-token=`). The newest token still works afterwards |

Supabase Auth accepts the parent of the current refresh token at any time, and older ones for about
10 s (its reuse interval). A browser keeps one cookie jar and stores each rotation as it arrives. So
it never presents a grandparent token: that would take two rotations, an hour apart (the access
token's life), while one request is in flight. This morning's suspicion that a slow refresh reuses
a refresh token (STATUS, 19 Oct) does not hold.

## 2. Supabase Auth out of reach: the session survives, the poll gets a 401 (`probe_401d.py`)

The web container's `/etc/hosts` pointed the Supabase host at 127.0.0.1 (restored after), one
throwaway session, in order:

| Step | Answer |
|---|---|
| Auth reachable, valid access token | 200 in 0.03 s |
| **Auth out of reach**, valid access token | 200 in 0.03 s (the signing keys are cached; no call to Auth) |
| **Auth out of reach**, expired access token | **401 after 50.9 s**, no cookie cleared |
| Auth back, the **same** expired cookie | 200 in 0.40 s, refreshed |
| Then the valid cookie | 200 |

When the proxy's refresh can't reach Auth (a network error or a 5xx), `@supabase/auth-js` 2.117.2
counts it as a retryable failure. It keeps the session (`_callRefreshToken`: `_removeSession` only
for a non-retryable error with the access token already expired), `getClaims()` fails, and the
route handler answers 401. The next request, once Auth answers, refreshes the same cookie. But every
poller sends the browser to `/sign-in` on that first 401. **A judge with a live session is sent to
sign in.** This is the 401 to design for.

When a refresh is refused and the access token has expired, the cookie is cleared (E8). The session
is then gone, and the next request is a 401 as well. So "redirect on the second 401 in a row" still
signs out a dead session, one poll later.
