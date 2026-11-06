"""Panelwise 2.0's renderer: FLUX.2 [klein] through QVAC's /v1/images/generations. A scripted
QVAC over httpx2.MockTransport, an in-memory store, the self-written lighthouse script."""

import base64
import io
import json
from pathlib import Path

import httpx2
import pytest
from PIL import Image

from app.core.config import Settings
from app.grounding import Extraction
from app.llm import NebiusChatModel, Tier
from app.main import default_renderer
from app.script import Screenplay, parse_text
from app.storage import LocalStore
from app.storyboard import StyleRegistry
from app.storyboard.qvac import QvacRenderer, qvac_draw_size, qvac_request
from app.storyboard.render import RendererError
from app.verify.audit import audit_frame
from app.verify.model import RenderedFrame, Verdict
from tests.fakes import MemoryStore
from tests.script.conftest import two_page_text
from tests.storyboard.conftest import STYLE, extraction_of, shot_of

URL = "http://127.0.0.1:11435/v1"


def png(width: int, height: int, shade: int = 90) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (width, height), (shade, shade, shade)).save(out, format="PNG")
    return out.getvalue()


class Qvac:
    """QVAC's images route as the renderer sees it: every request kept, answers scripted."""

    def __init__(self) -> None:
        self.bodies: list[dict[str, object]] = []
        self.blacks: list[bool] = []
        self.status = 200
        self.unloaded: list[str] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        if request.method == "DELETE":
            self.unloaded.append(str(request.url).removeprefix(f"{URL}/models/"))
            return httpx2.Response(200, json={"deleted": True})
        assert str(request.url) == f"{URL}/images/generations"
        body = json.loads(request.content)
        self.bodies.append(body)
        if self.status != 200:
            return httpx2.Response(self.status, json={"error": {"code": "no"}})
        w, h = (int(n) for n in str(body["size"]).split("x"))
        black = self.blacks.pop(0) if self.blacks else False
        b64 = base64.b64encode(png(w, h, shade=0 if black else 90)).decode()
        return httpx2.Response(200, json={"created": 1, "data": [{"b64_json": b64}]})


@pytest.fixture
def lighthouse() -> Screenplay:
    return parse_text(*two_page_text())


@pytest.fixture
def cast(lighthouse: Screenplay) -> Extraction:
    return extraction_of(lighthouse, [("NANDI", "NANDI (60s, oilskin coat)")])


def renderer(
    qvac: Qvac,
    store: MemoryStore,
    screenplay: Screenplay,
    extraction: Extraction,
    free_first: tuple[str, ...] = (),
) -> QvacRenderer:
    return QvacRenderer(
        style=STYLE,
        store=store,
        screenplay=screenplay,
        extraction=extraction,
        client=httpx2.AsyncClient(transport=httpx2.MockTransport(qvac)),
        base_url=URL,
        model="draw",
        max_pixels=409_600,
        free_first=free_first,
    )


def test_the_drawing_size_is_capped_and_in_sixteens() -> None:
    assert qvac_draw_size(1280, 720, 409_600) == (848, 480)
    assert qvac_draw_size(320, 160, 409_600) == (320, 160)  # never scaled up
    w, h = qvac_draw_size(1280, 720, 409_600)
    assert w * h <= 409_600 and w % 16 == 0 and h % 16 == 0


def test_the_request_is_klein_at_four_steps_seeded_and_inline() -> None:
    assert qvac_request("draw", "a person pours tea", 7, (848, 464)) == {
        "model": "draw",
        "prompt": "a person pours tea",
        "size": "848x464",
        "seed": 7,
        "steps": 4,
        "n": 1,
        "response_format": "b64_json",
    }


async def test_a_render_draws_once_and_stores_the_frame_fitted_to_the_size_asked(
    lighthouse: Screenplay, cast: Extraction
) -> None:
    qvac, store = Qvac(), MemoryStore()
    shot = shot_of(lighthouse, 0, [0])

    frame = await renderer(qvac, store, lighthouse, cast).render(shot, 1, 42, 1280, 720)

    assert len(qvac.bodies) == 1 and qvac.bodies[0]["seed"] == 42
    with Image.open(io.BytesIO(frame.png)) as image:
        assert image.size == (1280, 720)
    assert len(store.objects) == 1


async def test_a_second_render_of_the_same_shot_is_read_from_the_store(
    lighthouse: Screenplay, cast: Extraction
) -> None:
    qvac, store = Qvac(), MemoryStore()
    shot = shot_of(lighthouse, 0, [0])
    await renderer(qvac, store, lighthouse, cast).render(shot, 1, 42, 1280, 720)

    again = renderer(qvac, store, lighthouse, cast)
    await again.render(shot, 1, 42, 1280, 720)

    assert len(qvac.bodies) == 1
    assert again.record((0, shot.number), 1).cached


async def test_a_black_drawing_is_drawn_again_with_a_derived_seed(
    lighthouse: Screenplay, cast: Extraction
) -> None:
    qvac, store = Qvac(), MemoryStore()
    qvac.blacks = [True, False]

    await renderer(qvac, store, lighthouse, cast).render(
        shot_of(lighthouse, 0, [0]), 1, 42, 1280, 720
    )

    assert len(qvac.bodies) == 2 and qvac.bodies[0]["seed"] != qvac.bodies[1]["seed"]


async def test_a_server_error_is_a_renderer_error_without_the_prompt(
    lighthouse: Screenplay, cast: Extraction
) -> None:
    qvac, store = Qvac(), MemoryStore()
    qvac.status = 503

    with pytest.raises(RendererError) as caught:
        await renderer(qvac, store, lighthouse, cast).render(
            shot_of(lighthouse, 0, [0]), 1, 42, 1280, 720
        )
    assert "503" in str(caught.value) and "NANDI" not in str(caught.value)


def test_local_mode_draws_with_qvac_only_when_an_alias_is_set(tmp_path: Path) -> None:
    def settings(**kw: object) -> Settings:
        return Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            panelwise_local_token="tok",
            nebius_base_url=URL,
            database_url="postgresql+asyncpg://p:p@localhost:5433/p",
            fal_key="fal-key",
            **kw,  # pyright: ignore[reportArgumentType]
        )

    store = LocalStore(root=tmp_path, secret="s", public_url="http://localhost:8000")
    styles = StyleRegistry({STYLE.key: STYLE}, STYLE.key)
    client = httpx2.AsyncClient()
    assert default_renderer(settings(), styles, store, client) is None  # never fal.ai
    factory = default_renderer(settings(qvac_draw_model="draw"), styles, store, client)
    assert factory is not None


async def test_with_no_vision_model_a_frame_is_shown_unaudited_and_nothing_is_called(
    lighthouse: Screenplay, cast: Extraction
) -> None:
    calls: list[httpx2.Request] = []

    def anything(request: httpx2.Request) -> httpx2.Response:
        calls.append(request)
        return httpx2.Response(500)

    model = NebiusChatModel(
        api_key="",
        base_url=URL,
        models={Tier.FAST: "fast", Tier.REASONING: "reasoning", Tier.VISION: ""},
        transport=httpx2.MockTransport(anything),
    )
    shot = shot_of(lighthouse, 0, [0])
    frame = RenderedFrame((0, shot.number), 1, 42, png(64, 36), 64, 36, "prompt")

    audit = await audit_frame(model, frame, shot, lighthouse, cast)

    assert audit.verdict is Verdict.WARN and audit.checks == () and audit.models == ()
    assert calls == []


async def test_the_text_models_are_unloaded_once_before_the_first_drawing(
    lighthouse: Screenplay, cast: Extraction
) -> None:
    qvac, store = Qvac(), MemoryStore()
    drawer = renderer(qvac, store, lighthouse, cast, free_first=("qwen3-4b", "qwen3-4b"))

    await drawer.render(shot_of(lighthouse, 0, [0]), 1, 42, 1280, 720)
    await drawer.render(shot_of(lighthouse, 0, [0]), 2, 43, 1280, 720)

    assert qvac.unloaded == ["qwen3-4b"]  # once, and the alias named twice only once
    assert len(qvac.bodies) == 2


async def test_a_cached_frame_unloads_nothing(lighthouse: Screenplay, cast: Extraction) -> None:
    qvac, store = Qvac(), MemoryStore()
    shot = shot_of(lighthouse, 0, [0])
    await renderer(qvac, store, lighthouse, cast).render(shot, 1, 42, 1280, 720)

    await renderer(qvac, store, lighthouse, cast, free_first=("qwen3-4b",)).render(
        shot, 1, 42, 1280, 720
    )

    assert qvac.unloaded == []
