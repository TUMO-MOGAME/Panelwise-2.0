"""Assets in Supabase Storage: uploaded PDFs (T053) and, from T026, frame images.

storyboard.md §6 `AssetStore` / `SupabaseStore`. The bucket is private; only the secret key
reads or writes it, and a browser gets an image only through a signed URL (storyboard.md §8).
Supabase Storage answers some errors as 400 with the real status inside the body
(`"statusCode": "409"` for an existing object, `"404"` for a missing one; checked 2026-10-02).
A transient failure (429, a 5xx, Cloudflare's 520-524, a dropped connection) is tried again, as the
LLM client does (T070; storyboard.md §4).
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import Protocol, cast
from urllib.parse import quote

import httpx2

log = logging.getLogger(__name__)

_RETRYABLE = frozenset({429, 500, 502, 503, 504, 520, 521, 522, 523, 524})
_SIGN_BATCH = 100  # paths a batch-sign request carries (T122): our limit, to keep a request small


class StorageError(RuntimeError):
    """Storage refused or failed. The message names the operation and status, never a key."""


class AssetNotFound(StorageError):
    pass


class AssetStore(Protocol):
    async def exists(self, path: str) -> bool: ...
    async def get(self, path: str) -> bytes: ...
    async def put(self, path: str, data: bytes, content_type: str) -> None: ...  # idempotent
    async def signed_url(self, path: str, expires_in_s: int) -> str: ...
    async def signed_urls(self, paths: Sequence[str], expires_in_s: int) -> list[str]: ...


def _inner_status(response: httpx2.Response) -> str | None:
    """The status Supabase puts in the body of a 400 (or a real 4xx), if any."""
    try:
        body: object = response.json()
    except ValueError:
        return None
    if not isinstance(body, dict):
        return None
    status: object = cast(dict[str, object], body).get("statusCode")
    return None if status is None else str(status)


class SupabaseStore:
    def __init__(
        self,
        *,
        url: str,
        secret_key: str,
        bucket: str,
        client: httpx2.AsyncClient,
        max_attempts: int = 3,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._base = f"{url.rstrip('/')}/storage/v1"
        self._bucket = bucket
        self._client = client
        self._headers = {"apikey": secret_key, "Authorization": f"Bearer {secret_key}"}
        self._max_attempts = max_attempts
        self._sleep = sleep

    def _object(self, path: str, kind: str = "object") -> str:
        return f"{self._base}/{kind}/{quote(self._bucket)}/{quote(path, safe='/')}"

    async def _send(
        self, op: str, request: Callable[[], Awaitable[httpx2.Response]]
    ) -> httpx2.Response:
        """The first answer that isn't transient. A transient one is tried again, 1 s then 2 s
        later; out of attempts it's a StorageError. The log names the operation, never the key or
        the path."""
        backoff = 1.0
        status: int | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                response = await request()
            except httpx2.TransportError as exc:
                status = None
                reason = type(exc).__name__
            else:
                if response.status_code not in _RETRYABLE:
                    return response
                status = response.status_code
                reason = f"HTTP {status}"
            if attempt < self._max_attempts:
                log.warning(
                    "storage %s: %s (attempt %d of %d)", op, reason, attempt, self._max_attempts
                )
                await self._sleep(backoff)
                backoff *= 2
        if status is None:
            raise StorageError(f"{op}: storage unreachable after {self._max_attempts} attempts")
        raise StorageError(f"{op}: storage answered {status} after {self._max_attempts} attempts")

    async def exists(self, path: str) -> bool:
        response = await self._send(
            "exists", lambda: self._client.head(self._object(path), headers=self._headers)
        )
        if response.status_code == 200:
            return True
        if response.status_code in (400, 404):  # Storage says "missing" as a bare 400 to HEAD
            return False
        raise StorageError(f"exists: storage answered {response.status_code}")

    async def get(self, path: str) -> bytes:
        response = await self._send(
            "get", lambda: self._client.get(self._object(path), headers=self._headers)
        )
        if response.status_code == 200:
            return response.content
        if response.status_code == 404 or _inner_status(response) == "404":
            raise AssetNotFound(f"get: no object at {path}")
        raise StorageError(f"get: storage answered {response.status_code}")

    async def put(self, path: str, data: bytes, content_type: str) -> None:
        """Upload without overwriting. An existing path is left as is and counts as success:
        paths are content-addressed or unique (storyboard.md §6)."""
        response = await self._send(
            "put",
            lambda: self._client.post(
                self._object(path),
                content=data,
                headers=self._headers | {"Content-Type": content_type, "x-upsert": "false"},
            ),
        )
        if response.status_code == 200:
            return
        if response.status_code == 409 or _inner_status(response) == "409":
            return
        raise StorageError(f"put: storage answered {response.status_code}")

    async def signed_url(self, path: str, expires_in_s: int) -> str:
        response = await self._send(
            "signed_url",
            lambda: self._client.post(
                self._object(path, "object/sign"),
                json={"expiresIn": expires_in_s},
                headers=self._headers,
            ),
        )
        if response.status_code != 200:
            raise StorageError(f"signed_url: storage answered {response.status_code}")
        return f"{self._base}{response.json()['signedURL']}"

    async def signed_urls(self, paths: Sequence[str], expires_in_s: int) -> list[str]:
        """T122: one link per path, in order, from one batch request per 100 paths (signing them
        one by one took 4.9 s for 21 frames, one batch 0.22 s). All or nothing, as signed_url:
        a path storage can't sign (a missing object) fails the call, naming the count only."""
        links: list[str] = []
        url = f"{self._base}/object/sign/{quote(self._bucket)}"
        for start in range(0, len(paths), _SIGN_BATCH):  # no paths: no request (Supabase 400s)
            chunk = list(paths[start : start + _SIGN_BATCH])

            def request(chunk: list[str] = chunk) -> Awaitable[httpx2.Response]:
                body = {"expiresIn": expires_in_s, "paths": chunk}
                return self._client.post(url, json=body, headers=self._headers)

            response = await self._send("signed_urls", request)
            if response.status_code != 200:
                raise StorageError(f"signed_urls: storage answered {response.status_code}")
            items = cast(list[dict[str, object]], response.json())
            signed = [item.get("signedURL") for item in items]
            if len(signed) != len(chunk) or not all(isinstance(s, str) for s in signed):
                missing = len(chunk) - sum(isinstance(s, str) for s in signed)
                raise StorageError(f"signed_urls: storage could not sign {missing} of {len(paths)}")
            links += [f"{self._base}{s}" for s in signed]
        return links
