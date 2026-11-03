"""T026: the app builds its fal.ai renderer only when asked (`create_app(fal=True)`, the module's
app), with a key, a store and styles that load (storyboard.md §3.5). No network."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main
from app.core.config import Settings
from app.main import create_app
from tests.fakes import FakeVerifier, MemoryStore

pytestmark = pytest.mark.db


def factory_of(app: object) -> object:
    with TestClient(app) as client:  # type: ignore[arg-type]
        return client.app.state.renderer_factory  # type: ignore[attr-defined]


def test_with_a_key_a_store_and_styles_the_app_has_a_renderer(migrated: str) -> None:
    settings = Settings(database_url=migrated, fal_key="k", nebius_api_key="k")
    app = create_app(settings, verifier=FakeVerifier(), store=MemoryStore(), fal=True)
    assert callable(factory_of(app))


def test_never_without_being_asked_without_a_key_or_without_a_store(migrated: str) -> None:
    keyed = Settings(database_url=migrated, fal_key="k", nebius_api_key="k")
    keyless = Settings(database_url=migrated, fal_key="", nebius_api_key="k")
    assert factory_of(create_app(keyed, verifier=FakeVerifier(), store=MemoryStore())) is None
    assert (
        factory_of(create_app(keyless, verifier=FakeVerifier(), store=MemoryStore(), fal=True))
        is None
    )
    assert factory_of(create_app(keyed, verifier=FakeVerifier(), store=None, fal=True)) is None


def test_styles_that_do_not_load_mean_no_renderer_and_an_error_logged(
    migrated: str, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(main, "PUBLIC_STYLES", Path("/nowhere/styles"))
    settings = Settings(database_url=migrated, fal_key="k", nebius_api_key="k")
    with caplog.at_level("ERROR", logger="app.main"):
        app = create_app(settings, verifier=FakeVerifier(), store=MemoryStore(), fal=True)
        assert factory_of(app) is None
    assert any("styles didn't load" in r.getMessage() for r in caplog.records)
