"""Reproduce the 401 on a session refresh (free: Supabase auth calls only, no drawings, no tokens).

A throwaway user in the dev Supabase project, deleted at the end. The web's session cookie is
forged exactly as @supabase/ssr 0.12 writes it ("base64-" + base64url(JSON session), chunked at
3180), with expires_at in the past so the web's proxy must refresh it. Nothing secret is printed:
refresh tokens appear only as a short hash.
"""

import asyncio
import base64
import hashlib
import json
import secrets
import time
from urllib.parse import urlparse

try:
    import httpx
except ImportError:  # the API's pinned fork
    import httpx2 as httpx  # type: ignore[no-redef]

from app.core.config import Settings

WEB = "http://web:3000"
S = Settings()
REF = urlparse(S.supabase_url).hostname.split(".")[0]
NAME = f"sb-{REF}-auth-token"
ADMIN = {"apikey": S.supabase_secret_key, "Authorization": f"Bearer {S.supabase_secret_key}"}


def h(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()[:8]


def cookies_for(session: dict, expired: bool) -> dict[str, str]:
    s = dict(session)
    if expired:
        s["expires_at"] = int(time.time()) - 60
    raw = "base64-" + base64.urlsafe_b64encode(json.dumps(s).encode()).decode().rstrip("=")
    if len(raw) <= 3180:
        return {NAME: raw}
    return {f"{NAME}.{i}": raw[i * 3180 : (i + 1) * 3180] for i in range((len(raw) + 3179) // 3180)}


def session_from(set_cookies: list[str]) -> dict | None:
    """The session a response's Set-Cookie headers carry (joined chunks), or None."""
    parts: dict[str, str] = {}
    for line in set_cookies:
        name, _, rest = line.partition("=")
        value = rest.split(";", 1)[0]
        if name.startswith(NAME) and value:
            parts[name] = value
    if not parts:
        return None
    raw = parts.get(NAME) or "".join(parts[k] for k in sorted(parts, key=lambda k: int(k.rsplit(".", 1)[1])))
    raw = raw.removeprefix("base64-")
    return json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))


async def poll(client: httpx.AsyncClient, jar: dict[str, str], label: str) -> dict | None:
    t = time.perf_counter()
    r = await client.get(f"{WEB}/api/projects", cookies=jar)
    new = session_from(r.headers.get_list("set-cookie"))
    rt = h(new["refresh_token"]) if new else "-"
    print(f"  {label}: {r.status_code} in {time.perf_counter() - t:.2f}s, new refresh {rt}")
    return new


async def main() -> None:
    email = f"probe-401-{secrets.token_hex(4)}@panelwise.dev"
    password = secrets.token_urlsafe(24)
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(f"{S.supabase_url}/auth/v1/admin/users", headers=ADMIN,
                         json={"email": email, "password": password, "email_confirm": True})
        r.raise_for_status()
        uid = r.json()["id"]
        try:
            async def sign_in() -> dict:
                r = await c.post(f"{S.supabase_url}/auth/v1/token?grant_type=password",
                                 headers={"apikey": S.supabase_secret_key},
                                 json={"email": email, "password": password})
                r.raise_for_status()
                return r.json()

            s0 = await sign_in()
            print(f"session 0: refresh {h(s0['refresh_token'])}")
            print("E1 fresh session, one poll (expect 200, no refresh)")
            await poll(c, cookies_for(s0, False), "fresh")

            print("E2 expired access token, 5 concurrent polls (the storyboard's status + frames + …)")
            news = await asyncio.gather(*(poll(c, cookies_for(s0, True), f"concurrent {i}") for i in range(5)))
            s1 = next((n for n in news if n), None)

            print("E3 the old cookie again 3 s later (inside GoTrue's reuse interval?)")
            await asyncio.sleep(3)
            await poll(c, cookies_for(s0, True), "stale +3s")

            print("E4 the old cookie again 15 s later (outside it: a lost Set-Cookie)")
            await asyncio.sleep(12)
            await poll(c, cookies_for(s0, True), "stale +15s")

            print("E5 then the cookie E2 handed back (did E4 revoke the whole session?)")
            if s1:
                await poll(c, cookies_for(s1, False), "E2's session, access token still valid")
                await poll(c, cookies_for(s1, True), "E2's session, forced refresh")

            print("E6 a new session; one poll refreshes; the next poll 0.5 s later still has the old cookie")
            s2 = await sign_in()
            await poll(c, cookies_for(s2, True), "first")
            await asyncio.sleep(0.5)
            await poll(c, cookies_for(s2, True), "second, stale")
        finally:
            d = await c.delete(f"{S.supabase_url}/auth/v1/admin/users/{uid}", headers=ADMIN)
            print(f"throwaway user deleted: {d.status_code}")


asyncio.run(main())
