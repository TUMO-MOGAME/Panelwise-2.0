"""Phase runner for the 401-when-Supabase-is-unreachable probe: init | poll <expired|valid> | cleanup.

State (the throwaway user's id and session) lives in /tmp/probe_401d.json inside the API container.
"""

import asyncio
import json
import secrets
import sys

sys.path.insert(0, "/tmp")
from probe_401c import ADMIN, S, cookies_for, h, httpx, poll  # noqa: E402

STATE = "/tmp/probe_401d.json"


async def main(argv: list[str]) -> None:
    async with httpx.AsyncClient(timeout=60) as c:
        if argv[0] == "init":
            email = f"probe-401-{secrets.token_hex(4)}@panelwise.dev"
            password = secrets.token_urlsafe(24)
            r = await c.post(f"{S.supabase_url}/auth/v1/admin/users", headers=ADMIN,
                             json={"email": email, "password": password, "email_confirm": True})
            r.raise_for_status()
            uid = r.json()["id"]
            r = await c.post(f"{S.supabase_url}/auth/v1/token?grant_type=password",
                             headers={"apikey": S.supabase_secret_key}, json={"email": email, "password": password})
            r.raise_for_status()
            json.dump({"uid": uid, "session": r.json()}, open(STATE, "w"))
            print(f"init: refresh {h(r.json()['refresh_token'])}")
        elif argv[0] == "poll":
            st = json.load(open(STATE))
            new = await poll(c, cookies_for(st["session"], argv[1] == "expired"), f"{argv[1]} cookie")
            if new:
                st["session"] = new
                json.dump(st, open(STATE, "w"))
        elif argv[0] == "cleanup":
            st = json.load(open(STATE))
            d = await c.delete(f"{S.supabase_url}/auth/v1/admin/users/{st['uid']}", headers=ADMIN)
            print(f"throwaway user deleted: {d.status_code}")


asyncio.run(main(sys.argv[1:]))
