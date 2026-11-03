"""Assets behind one seam: Supabase Storage, or this machine's disk in local mode.
docs/design/storyboard.md §6, deploy.md §7."""

from app.storage.local import LocalStore
from app.storage.store import AssetNotFound, AssetStore, StorageError, SupabaseStore

__all__ = ["AssetNotFound", "AssetStore", "LocalStore", "StorageError", "SupabaseStore"]
