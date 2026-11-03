"""LocalStore and GET /api/v1/files: Panelwise 2.0's local mode, assets on this machine's disk."""

from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from app.core.auth import LOCAL_USER_ID, AuthError, LocalVerifier
from app.core.config import Settings
from app.main import create_app, default_store, default_verifier
from app.storage import AssetNotFound, LocalStore, StorageError

SECRET = "local-secret-for-tests"
NOW = 1_800_000_000.0


def make(root: Path, now: float = NOW) -> LocalStore:
    return LocalStore(root=root, secret=SECRET, public_url="http://api.test/", clock=lambda: now)


async def test_put_get_and_exists(tmp_path: Path) -> None:
    store = make(tmp_path)
    assert not await store.exists("frames/a.png")

    await store.put("frames/a.png", b"png", "image/png")

    assert await store.exists("frames/a.png")
    assert await store.get("frames/a.png") == b"png"
    assert (tmp_path / "frames" / "a.png").read_bytes() == b"png"


async def test_put_never_overwrites(tmp_path: Path) -> None:
    store = make(tmp_path)
    await store.put("frames/a.png", b"first", "image/png")
    await store.put("frames/a.png", b"second", "image/png")

    assert await store.get("frames/a.png") == b"first"


async def test_get_of_a_missing_path_is_not_found(tmp_path: Path) -> None:
    with pytest.raises(AssetNotFound):
        await make(tmp_path).get("frames/missing.png")


@pytest.mark.parametrize(
    "path", ["../escape.png", "frames/../../escape.png", "/abs.png", "a\\b.png", "C:/x.png", ""]
)
async def test_a_path_that_leaves_the_root_is_refused(tmp_path: Path, path: str) -> None:
    with pytest.raises(StorageError):
        await make(tmp_path / "root").put(path, b"x", "image/png")
    assert not (tmp_path / "escape.png").exists()


async def test_a_signed_link_names_the_path_and_checks_until_it_expires(tmp_path: Path) -> None:
    await make(tmp_path).put("frames/a.png", b"png", "image/png")
    url = await make(tmp_path).signed_url("frames/a.png", 3600)

    parts = urlsplit(url)
    query = {k: v[0] for k, v in parse_qs(parts.query).items()}
    assert (
        f"{parts.scheme}://{parts.netloc}{parts.path}"
        == "http://api.test/api/v1/files/frames/a.png"
    )
    expires, sig = int(query["expires"]), query["sig"]
    assert expires == NOW + 3600
    assert make(tmp_path).check("frames/a.png", expires, sig)
    assert not make(tmp_path).check("frames/b.png", expires, sig)  # another path
    assert not make(tmp_path).check("frames/a.png", expires + 1, sig)  # a stretched expiry
    assert not make(tmp_path, now=expires + 1).check("frames/a.png", expires, sig)  # expired


async def test_signing_a_missing_path_fails(tmp_path: Path) -> None:
    with pytest.raises(StorageError):
        await make(tmp_path).signed_urls(["frames/missing.png"], 60)


async def test_the_local_verifier_takes_only_its_token() -> None:
    verifier = LocalVerifier("tok")
    assert (await verifier.verify("tok")).user_id == LOCAL_USER_ID
    with pytest.raises(AuthError):
        await verifier.verify("other")


def test_a_local_token_replaces_supabase(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        panelwise_local_token="tok",
        local_data_dir=str(tmp_path),
        nebius_base_url="http://127.0.0.1:11435/v1",
        database_url="postgresql+asyncpg://panelwise:panelwise@localhost:5433/panelwise",
    )
    client = None  # local mode never uses the HTTP client
    assert isinstance(default_verifier(settings, client), LocalVerifier)  # pyright: ignore[reportArgumentType]
    assert isinstance(default_store(settings, client), LocalStore)  # pyright: ignore[reportArgumentType]


# --- the route --------------------------------------------------------------------


def served(tmp_path: Path) -> tuple[TestClient, LocalStore]:
    store = LocalStore(root=tmp_path, secret=SECRET, public_url="http://testserver")
    app = create_app(Settings(_env_file=None))  # pyright: ignore[reportCallIssue]
    app.state.store = store  # what the lifespan sets; a bare TestClient doesn't run it
    return TestClient(app), store


async def test_the_route_serves_a_signed_link(tmp_path: Path) -> None:
    client, store = served(tmp_path)
    await store.put("frames/a.png", b"\x89PNG", "image/png")
    url = await store.signed_url("frames/a.png", 60)

    res = client.get(url)

    assert res.status_code == 200
    assert res.content == b"\x89PNG"
    assert res.headers["content-type"] == "image/png"
    assert res.headers["x-content-type-options"] == "nosniff"


async def test_a_download_link_is_an_attachment_with_its_name(tmp_path: Path) -> None:
    client, store = served(tmp_path)
    await store.put("storyboards/x.pdf", b"%PDF", "application/pdf")
    url = await store.signed_url("storyboards/x.pdf", 60)

    res = client.get(f"{url}&download=Kite%20storyboard.pdf")

    assert res.status_code == 200
    assert res.headers["content-disposition"].startswith("attachment")
    assert "Kite%20storyboard.pdf" in res.headers["content-disposition"]  # RFC 5987, as encoded


async def test_a_tampered_or_unsigned_link_is_404(tmp_path: Path) -> None:
    client, store = served(tmp_path)
    await store.put("frames/a.png", b"png", "image/png")
    await store.put("frames/b.png", b"png", "image/png")
    url = await store.signed_url("frames/a.png", 60)

    assert client.get(url.replace("frames/a.png", "frames/b.png")).status_code == 404
    assert client.get("/api/v1/files/frames/a.png?expires=9999999999&sig=00").status_code == 404
    assert client.get("/api/v1/files/frames/a.png").status_code == 422


def test_without_local_mode_the_route_is_404(tmp_path: Path) -> None:
    app = create_app(Settings(_env_file=None))  # pyright: ignore[reportCallIssue]
    app.state.store = None
    client = TestClient(app)
    assert client.get("/api/v1/files/frames/a.png?expires=1&sig=00").status_code == 404


LOCAL_DB = "postgresql+asyncpg://panelwise:panelwise@localhost:5433/panelwise"


def test_local_mode_never_draws_in_the_cloud_even_with_a_fal_key(tmp_path: Path) -> None:
    # 2026-11-03: a FAL_KEY left in .env drew 36 frames on fal.ai from a "local" run.
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        panelwise_local_token="tok",
        local_data_dir=str(tmp_path),
        fal_key="fal-key-that-must-not-be-used",
        nebius_base_url="http://127.0.0.1:1/v1",
        database_url="postgresql+asyncpg://nobody:nothing@127.0.0.1:1/none",
    )
    app = create_app(settings, fal=True)
    with TestClient(app):
        assert isinstance(app.state.store, LocalStore)
        assert app.state.renderer_factory is None


def test_local_mode_drops_every_cloud_key() -> None:
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        panelwise_local_token="tok",
        nebius_base_url="http://127.0.0.1:11435/v1",
        database_url=LOCAL_DB,
        nebius_api_key="nb-key",
        fal_key="fal-key",
        supabase_url="https://x.supabase.co",
        supabase_secret_key="sb-key",
    )
    assert (settings.nebius_api_key, settings.fal_key) == ("", "")
    assert (settings.supabase_url, settings.supabase_secret_key) == ("", "")
    assert settings.nebius_model_vision == ""  # no QVAC vision path yet: never another model


@pytest.mark.parametrize(
    ("base_url", "database_url"),
    [
        ("https://api.tokenfactory.nebius.com/v1", LOCAL_DB),
        ("http://127.0.0.1:11435/v1", "postgresql://u:p@db.supabase.co:5432/postgres"),
    ],
)
def test_local_mode_refuses_a_model_server_or_database_elsewhere(
    base_url: str, database_url: str
) -> None:
    with pytest.raises(ValueError, match="must point at this machine"):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            panelwise_local_token="tok",
            nebius_base_url=base_url,
            database_url=database_url,
        )
