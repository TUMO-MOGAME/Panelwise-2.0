"""Assets on this machine's disk: Panelwise 2.0's local mode (PANELWISE_LOCAL_TOKEN).

The same `AssetStore` seam as `SupabaseStore`. A signed link points at the API's own
`/api/v1/files/...` route and carries an expiry and an HMAC of the path and expiry, so a link
works as Storage's did -- for its hour, and only for the path it names -- with nothing in the
cloud.
"""

import asyncio
import hashlib
import hmac
import os
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from urllib.parse import quote

from app.storage.store import AssetNotFound, StorageError


class LocalStore:
    def __init__(
        self,
        *,
        root: Path,
        secret: str,
        public_url: str,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not secret:
            raise ValueError("the signing secret is empty")
        self._root = root.resolve()
        self._key = hashlib.sha256(b"panelwise-local-files\0" + secret.encode()).digest()
        self._public = public_url.rstrip("/")
        self._clock = clock

    def file(self, path: str) -> Path:
        """The file for an asset path, refusing any path that would leave the root."""
        parts = path.split("/")
        if not path or any(p in ("", ".", "..") or "\\" in p or ":" in p for p in parts):
            raise StorageError("unsafe asset path")
        target = self._root.joinpath(*parts).resolve()
        if not target.is_relative_to(self._root):
            raise StorageError("unsafe asset path")
        return target

    def signature(self, path: str, expires: int) -> str:
        return hmac.new(self._key, f"{path}\n{expires}".encode(), hashlib.sha256).hexdigest()

    def check(self, path: str, expires: int, signature: str) -> bool:
        """True when the link is this store's, for this path, and not yet expired."""
        good = hmac.compare_digest(self.signature(path, expires), signature)
        return good and expires >= self._clock()

    async def exists(self, path: str) -> bool:
        return await asyncio.to_thread(self.file(path).is_file)

    async def get(self, path: str) -> bytes:
        target = self.file(path)
        try:
            return await asyncio.to_thread(target.read_bytes)
        except FileNotFoundError:
            raise AssetNotFound(f"get: no object at {path}") from None

    async def put(self, path: str, data: bytes, content_type: str) -> None:
        """Write without overwriting, as SupabaseStore: an existing path counts as success."""
        del content_type  # the files route serves by extension
        target = self.file(path)

        def write() -> None:
            if target.exists():
                return
            target.parent.mkdir(parents=True, exist_ok=True)
            partial = target.with_name(f".{target.name}.{os.getpid()}.part")
            partial.write_bytes(data)
            try:  # a reader never sees half a file
                partial.replace(target)
            except OSError:
                partial.unlink(missing_ok=True)
                if not target.exists():
                    raise

        await asyncio.to_thread(write)

    async def signed_url(self, path: str, expires_in_s: int) -> str:
        if not await self.exists(path):
            raise StorageError("signed_url: no such object")
        expires = int(self._clock()) + expires_in_s
        signature = self.signature(path, expires)
        return f"{self._public}/api/v1/files/{quote(path)}?expires={expires}&sig={signature}"

    async def signed_urls(self, paths: Sequence[str], expires_in_s: int) -> list[str]:
        return [await self.signed_url(path, expires_in_s) for path in paths]
