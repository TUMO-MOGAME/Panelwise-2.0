"""Who is calling: a Supabase access token, verified locally. web.md §6 *API internals* (T053).

The project signs its tokens with ES256 and publishes the public keys as a JWKS, so a token is
checked against those keys here, with no call to Supabase per request. The cost, accepted: a
token stays valid until its `exp` (at most an hour) after the user signs out.
"""

import asyncio
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, cast

import httpx2
import jwt
from fastapi import Request

from app.api.errors import ApiError

_ALGORITHMS = frozenset({"ES256", "RS256"})  # asymmetric only: never HS256, never `none`
_REQUIRED = ["exp", "iat", "sub", "aud", "iss"]
_LEEWAY_S = 30
_MIN_REFETCH_S = 60.0


@dataclass(frozen=True)
class Caller:
    user_id: uuid.UUID  # the token's `sub`: the Supabase Auth user id, `projects.owner`


class AuthError(Exception):
    """Any reason a token is refused. Never told to the client, which sees 401."""


class AuthUnavailable(Exception):
    """No keys to check against (Supabase unreachable and nothing cached): 503, not 401, so an
    outage never signs a user out."""


class TokenVerifier(Protocol):
    async def verify(self, token: str) -> Caller: ...


class SupabaseJwtVerifier:
    def __init__(
        self,
        *,
        supabase_url: str,
        client: httpx2.AsyncClient,
        jwks_ttl_s: float = 600,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        base = supabase_url.rstrip("/")
        self._issuer = f"{base}/auth/v1"
        self._jwks_url = f"{self._issuer}/.well-known/jwks.json"
        self._client = client
        self._ttl = jwks_ttl_s
        self._clock = clock
        self._keys: dict[str, jwt.PyJWK] | None = None
        self._fetched_at = -float("inf")
        self._attempted_at = -float("inf")
        self._lock = asyncio.Lock()

    async def verify(self, token: str) -> Caller:
        try:
            kid = jwt.get_unverified_header(token).get("kid")
        except jwt.PyJWTError as exc:
            raise AuthError("malformed token") from exc
        if not isinstance(kid, str):
            raise AuthError("no kid")
        key = await self._key(kid)
        if key is None:
            raise AuthError("unknown kid")
        # The algorithm is the key's, never the token header's claim alone.
        if key.algorithm_name not in _ALGORITHMS:
            raise AuthError("key algorithm not allowed")
        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                key=key.key,
                algorithms=[key.algorithm_name],
                audience="authenticated",
                issuer=self._issuer,
                leeway=_LEEWAY_S,
                options={"require": _REQUIRED},
            )
        except jwt.PyJWTError as exc:
            raise AuthError("invalid token") from exc
        if claims.get("role") != "authenticated" or claims.get("is_anonymous") is True:
            raise AuthError("not a signed-in user")
        try:
            return Caller(user_id=uuid.UUID(str(claims["sub"])))
        except ValueError as exc:
            raise AuthError("sub is not a user id") from exc

    async def _key(self, kid: str) -> jwt.PyJWK | None:
        now = self._clock()
        stale = now - self._fetched_at > self._ttl
        unknown = self._keys is not None and kid not in self._keys
        if self._keys is None or stale or unknown:
            await self._refresh()
        if self._keys is None:
            raise AuthUnavailable("no signing keys")
        return self._keys.get(kid)

    async def _refresh(self) -> None:
        """At most one fetch a minute, shared by every request behind one lock: a flood of random
        kids costs one request a minute. A failed fetch keeps the keys already cached."""
        async with self._lock:
            now = self._clock()
            if now - self._attempted_at < _MIN_REFETCH_S:
                return
            self._attempted_at = now
            try:
                response = await self._client.get(self._jwks_url, timeout=10)
                response.raise_for_status()
                published: object = response.json()["keys"]
            except httpx2.HTTPError, ValueError, KeyError, TypeError:
                return
            keys: dict[str, jwt.PyJWK] = {}
            for entry in cast(
                list[dict[str, Any]], published if isinstance(published, list) else []
            ):
                try:  # one key we can't read (a new key type) must not hide the others
                    keys[entry["kid"]] = jwt.PyJWK(entry)
                except KeyError, TypeError, jwt.PyJWTError:
                    continue
            if not keys:
                return
            self._keys, self._fetched_at = keys, now


async def current_caller(request: Request) -> Caller:
    """FastAPI dependency: `Authorization: Bearer <token>` → the caller, or a §6 error."""
    verifier: TokenVerifier | None = getattr(request.app.state, "verifier", None)
    if verifier is None:
        raise ApiError(503, "auth_unavailable")
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise ApiError(401, "unauthorized", headers={"WWW-Authenticate": "Bearer"})
    try:
        return await verifier.verify(token.strip())
    except AuthUnavailable as exc:
        raise ApiError(503, "auth_unavailable") from exc
    except AuthError as exc:
        raise ApiError(401, "unauthorized", headers={"WWW-Authenticate": "Bearer"}) from exc
