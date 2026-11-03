"""T026: the fal.ai renderer (storyboard.md §3.5, §9). A scripted fal.ai over httpx2.MockTransport,
an in-memory store, the self-written lighthouse script. No network."""

import io
import json
import logging

import httpx2
import pytest
from PIL import Image
from pydantic import ValidationError

from app.core.config import Settings
from app.grounding import Extraction
from app.script import Screenplay, parse_text
from app.storyboard import StyleRegistry
from app.storyboard.fal import (
    MAX_PIXELS,
    FalRenderer,
    derived_seed,
    fal_draw_size,
    fal_factory,
    fal_request,
)
from app.storyboard.render import RendererError
from app.storyboard.workflow import RENDER_VERSION, fit, postprocess, render_key
from tests.fakes import MemoryStore
from tests.script.conftest import two_page_text
from tests.storyboard.conftest import STYLE, extraction_of, shot_of

KEY = "fal-secret-key"


def png(width: int, height: int, shade: int = 90) -> bytes:
    out = io.BytesIO()
    colour = (0, 0, 0) if shade == 0 else (shade, shade + 20, shade + 40)
    Image.new("RGB", (width, height), colour).save(out, format="PNG")
    return out.getvalue()


class Fal:
    """fal.ai as the renderer sees it: POST /{model} answers an image URL, GET that URL its PNG.
    `statuses` and `flags` script the next answers; every request is kept."""

    def __init__(self) -> None:
        self.posts: list[httpx2.Request] = []
        self.gets: list[httpx2.Request] = []
        self.statuses: list[int] = []
        self.flags: list[bool] = []
        self.size_off = 0  # px the drawing's width is off from the asked width
        self.round_up_h = 0  # px klein-style rounding adds to the height
        self.network_errors = 0
        self.omit_flags = False  # an answer with no safety result
        self.blacks: list[bool] = []  # the next drawings come back all black, unflagged

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        if request.method == "GET":
            self.gets.append(request)
            w, h = (int(x) for x in request.url.path.rsplit("/", 1)[1].split(".")[0].split("x"))
            black = self.blacks.pop(0) if self.blacks else False
            return httpx2.Response(200, content=png(w, h, shade=0) if black else png(w, h))
        self.posts.append(request)
        if self.network_errors:
            self.network_errors -= 1
            raise httpx2.ConnectError("down", request=request)
        status = self.statuses.pop(0) if self.statuses else 200
        if status != 200:
            return httpx2.Response(status, json={"detail": "no"})
        body = json.loads(request.content)
        w, h = body["image_size"]["width"], body["image_size"]["height"]
        flagged = self.flags.pop(0) if self.flags else False
        shown_w, shown_h = w + self.size_off, h + self.round_up_h
        image = {
            "url": f"https://cdn.fal.test/out/{w}x{h}.png",
            "width": shown_w,
            "height": shown_h,
        }
        answer: dict[str, object] = {"images": [image], "seed": body["seed"]}
        if not self.omit_flags:
            answer["has_nsfw_concepts"] = [flagged]
        return httpx2.Response(200, json=answer)


@pytest.fixture
def lighthouse() -> Screenplay:
    return parse_text(*two_page_text())


@pytest.fixture
def cast(lighthouse: Screenplay) -> Extraction:
    return extraction_of(lighthouse, [("NANDI", "NANDI (60s, oilskin coat)")])


@pytest.fixture
def fal() -> Fal:
    return Fal()


@pytest.fixture
def slept() -> list[float]:
    return []


def renderer(
    fal: Fal, store: MemoryStore, screenplay: Screenplay, extraction: Extraction, slept: list[float]
) -> FalRenderer:
    async def sleep(seconds: float) -> None:
        slept.append(seconds)

    return FalRenderer(
        style=STYLE,
        store=store,
        screenplay=screenplay,
        extraction=extraction,
        client=httpx2.AsyncClient(transport=httpx2.MockTransport(fal)),
        key=KEY,
        sleep=sleep,
    )


# --- sizes and the request ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("asked", "drawn"),
    [((1280, 720), (1280, 720)), ((1748, 986), (1328, 736)), ((930, 789), (928, 784)),
     ((2000, 2000), (992, 992)), ((40, 30), (32, 16))],
)  # fmt: skip
def test_a_drawing_is_never_more_than_a_megapixel_and_in_sixteens(
    asked: tuple[int, int], drawn: tuple[int, int]
) -> None:
    assert fal_draw_size(*asked) == drawn
    w, h = drawn
    assert w * h <= MAX_PIXELS and w % 16 == 0 and h % 16 == 0


def test_the_request_is_plain_seeded_and_png() -> None:
    assert fal_request("a person pours tea", 7, (1280, 720)) == {
        "prompt": "a person pours tea",
        "image_size": {"width": 1280, "height": 720},
        "seed": 7,
        "num_inference_steps": 4,
        "num_images": 1,
        "output_format": "png",
    }


def test_fit_makes_exactly_the_size_asked_for() -> None:
    assert fit(png(1328, 736), 1748, 986).size == (1748, 986)
    assert fit(png(1280, 720), 1280, 720).size == (1280, 720)
    assert postprocess(fit(png(64, 64), 32, 32), grayscale=True).mode == "L"


def test_the_render_key_names_everything_that_changes_the_pixels() -> None:
    graph = {"model": "m", "request": fal_request("p", 1, (1280, 720))}
    base = render_key(graph, 1280, 720, "grayscale")
    assert base == render_key(dict(reversed(graph.items())), 1280, 720, "grayscale")  # canonical
    others = {
        render_key({**graph, "model": "n"}, 1280, 720, "grayscale"),
        render_key(
            {"model": "m", "request": fal_request("p", 2, (1280, 720))}, 1280, 720, "grayscale"
        ),
        render_key(graph, 1279, 720, "grayscale"),
        render_key(graph, 1280, 720, "none"),
    }
    assert base not in others and len(others) == 4 and RENDER_VERSION == 1


# --- render ---------------------------------------------------------------------------------------


async def test_a_render_calls_fal_once_and_stores_the_fitted_frame_before_returning(
    fal: Fal, lighthouse: Screenplay, cast: Extraction, slept: list[float]
) -> None:
    store = MemoryStore()
    r = renderer(fal, store, lighthouse, cast, slept)
    shot = shot_of(lighthouse, 0, [0])
    frame = await r.render(shot, 1, 1234, 1748, 986)

    (post,) = fal.posts
    assert str(post.url) == "https://fal.run/fal-ai/flux/schnell"
    assert post.headers["Authorization"] == f"Key {KEY}"
    body = json.loads(post.content)
    assert body == fal_request(frame.prompt, 1234, (1328, 736))
    # the script's own words, unescaped and unweighted (FLUX reads no ComfyUI syntax); no names
    assert "a person (60s, oilskin coat) pours tea" in frame.prompt
    assert r"\(" not in frame.prompt and ":1." not in frame.prompt and "NANDI" not in frame.prompt
    assert "Authorization" not in fal.gets[0].headers  # the key goes to fal.ai, not its CDN
    assert (frame.width, frame.height, frame.seed, frame.attempt) == (1748, 986, 1234, 1)
    assert Image.open(io.BytesIO(frame.png)).size == (1748, 986)

    record = r.record((0, 1), 1)
    key = render_key({"model": "fal-ai/flux/schnell", "request": body}, 1748, 986, "grayscale")
    assert (record.key, record.asset, record.cached) == (key, f"frames/{key}.png", False)
    assert store.objects[record.asset] == (frame.png, "image/png")
    assert record.prompt.text() == frame.prompt and slept == []


async def test_a_stored_drawing_is_never_paid_for_twice(
    fal: Fal, lighthouse: Screenplay, cast: Extraction, slept: list[float]
) -> None:
    store = MemoryStore()
    shot = shot_of(lighthouse, 0, [0])
    first = await renderer(fal, store, lighthouse, cast, slept).render(shot, 1, 99, 1280, 720)
    again = renderer(fal, store, lighthouse, cast, slept)
    second = await again.render(shot, 1, 99, 1280, 720)
    assert len(fal.posts) == 1 and second.png == first.png
    assert again.record((0, 1), 1).cached and again.record((0, 1), 1).seconds is None


async def test_busy_and_down_are_retried_and_a_refusal_is_not(
    fal: Fal, lighthouse: Screenplay, cast: Extraction, slept: list[float]
) -> None:
    shot = shot_of(lighthouse, 0, [0])
    fal.statuses = [429]
    fal.network_errors = 0
    await renderer(fal, MemoryStore(), lighthouse, cast, slept).render(shot, 1, 1, 1280, 720)
    assert slept == [1.0] and len(fal.posts) == 2

    slept.clear()
    fal.statuses = [503, 502, 500]
    with pytest.raises(RendererError, match="after 3 tries \\(500\\)") as failed:
        await renderer(fal, MemoryStore(), lighthouse, cast, slept).render(shot, 1, 2, 1280, 720)
    assert slept == [1.0, 2.0]

    fal.statuses = [401]
    with pytest.raises(RendererError, match="answered 401 for fal-ai/flux/schnell") as refused:
        await renderer(fal, MemoryStore(), lighthouse, cast, slept).render(shot, 1, 3, 1280, 720)
    for error in (failed.value, refused.value):  # never the key, never the script
        assert KEY not in str(error) and "pours" not in str(error)

    fal.network_errors = 3
    with pytest.raises(RendererError, match="no answer"):
        await renderer(fal, MemoryStore(), lighthouse, cast, slept).render(shot, 1, 4, 1280, 720)


async def test_every_retry_is_logged_without_the_key_or_the_prompt(
    fal: Fal,
    lighthouse: Screenplay,
    cast: Extraction,
    slept: list[float],
    caplog: pytest.LogCaptureFixture,
) -> None:
    # The first live run (2026-10-10) lost a frame with nothing in the logs to say why.
    caplog.set_level(logging.WARNING, logger="app.storyboard.fal")
    fal.statuses = [503, 429]
    fal.network_errors = 0
    await renderer(fal, MemoryStore(), lighthouse, cast, slept).render(
        shot_of(lighthouse, 0, [0]), 1, 6, 1280, 720
    )
    lines = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(lines) == 2
    assert "503" in lines[0] and "429" in lines[1] and "fal-ai/flux/schnell" in lines[0]
    assert all(KEY not in line and "pours" not in line for line in lines)


async def test_a_network_error_retry_names_the_errors_type(
    fal: Fal,
    lighthouse: Screenplay,
    cast: Extraction,
    slept: list[float],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="app.storyboard.fal")
    fal.network_errors = 1
    await renderer(fal, MemoryStore(), lighthouse, cast, slept).render(
        shot_of(lighthouse, 0, [0]), 1, 7, 1280, 720
    )
    (line,) = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert "ConnectError" in line and "try 1 of 3" in line and KEY not in line


@pytest.mark.parametrize("value", [0, -1])
def test_a_concurrency_below_one_is_refused_at_startup(value: int) -> None:
    # Semaphore(0) would leave every shot waiting forever, silently (review of #91).
    with pytest.raises(ValidationError, match="fal_concurrency"):
        Settings(fal_concurrency=value)


async def test_an_image_of_another_size_is_refused(
    fal: Fal, lighthouse: Screenplay, cast: Extraction, slept: list[float]
) -> None:
    fal.size_off = 32  # past klein's rounding: the model ignored the size
    store = MemoryStore()
    with pytest.raises(RendererError, match=r"1312 x 720 .* not the 1280 x 720"):
        await renderer(fal, store, lighthouse, cast, slept).render(
            shot_of(lighthouse, 0, [0]), 1, 5, 1280, 720
        )
    assert store.objects == {}


async def test_a_smaller_image_is_refused(
    fal: Fal, lighthouse: Screenplay, cast: Extraction, slept: list[float]
) -> None:
    fal.size_off = -16
    with pytest.raises(RendererError, match=r"1264 x 720 .* not the 1280 x 720"):
        await renderer(fal, MemoryStore(), lighthouse, cast, slept).render(
            shot_of(lighthouse, 0, [0]), 1, 5, 1280, 720
        )


async def test_klein_s_rounding_up_is_cropped_to_the_asked_size(
    fal: Fal, lighthouse: Screenplay, cast: Extraction, slept: list[float]
) -> None:
    """klein draws in multiples of 32: 720 comes back 736, and fit crops it (storyboard.md §3.5)."""
    fal.round_up_h = 16
    frame = await renderer(fal, MemoryStore(), lighthouse, cast, slept).render(
        shot_of(lighthouse, 0, [0]), 1, 5, 1280, 720
    )
    assert (frame.width, frame.height) == (1280, 720)


async def test_a_blacked_out_drawing_is_drawn_again_with_a_derived_seed(
    fal: Fal, lighthouse: Screenplay, cast: Extraction, slept: list[float]
) -> None:
    fal.flags = [True, False]
    store = MemoryStore()
    r = renderer(fal, store, lighthouse, cast, slept)
    frame = await r.render(shot_of(lighthouse, 0, [0]), 2, 77, 1280, 720)
    seeds = [json.loads(p.content)["seed"] for p in fal.posts]
    assert seeds == [77, derived_seed(77, 1)] and frame.seed == derived_seed(77, 1)
    assert len(fal.gets) == 1  # the flagged drawing was never fetched, stored or audited
    assert r.record((0, 1), 2).key in r.record((0, 1), 2).asset and len(store.objects) == 1

    fal.flags = [True, True, True]
    with pytest.raises(RendererError, match="safety checker blocked every drawing"):
        await renderer(fal, MemoryStore(), lighthouse, cast, slept).render(
            shot_of(lighthouse, 0, [0]), 1, 78, 1280, 720
        )


def test_the_factory_makes_a_renderer_in_the_default_style(
    lighthouse: Screenplay, cast: Extraction
) -> None:
    registry = StyleRegistry({STYLE.key: STYLE}, STYLE.key)
    client = httpx2.AsyncClient()
    settings = Settings(fal_key=KEY, fal_model="fal-ai/x", fal_timeout_s=9, comfyui_max_words=40)
    made = fal_factory(registry, MemoryStore(), client, settings)(lighthouse, cast)
    assert isinstance(made, FalRenderer)
    assert (made.style, made.key, made.model, made.timeout_s, made.max_words) == (
        STYLE,
        KEY,
        "fal-ai/x",
        9,
        40,
    )


async def test_a_shot_whose_first_seed_was_flagged_costs_nothing_next_time(
    fal: Fal, lighthouse: Screenplay, cast: Extraction, slept: list[float]
) -> None:
    store = MemoryStore()
    shot = shot_of(lighthouse, 0, [0])
    fal.flags = [True, False]
    first = await renderer(fal, store, lighthouse, cast, slept).render(shot, 1, 5, 1280, 720)
    posts = len(fal.posts)
    again = renderer(fal, store, lighthouse, cast, slept)
    second = await again.render(shot, 1, 5, 1280, 720)
    assert len(fal.posts) == posts == 2  # the re-run found redraw 1 in the store: no call at all
    assert (second.png, second.seed) == (first.png, derived_seed(5, 1))
    assert again.record((0, 1), 1).cached


async def test_no_safety_result_is_an_error_never_assumed_clean(
    fal: Fal, lighthouse: Screenplay, cast: Extraction, slept: list[float]
) -> None:
    fal.omit_flags = True
    store = MemoryStore()
    with pytest.raises(RendererError, match="no safety result"):
        await renderer(fal, store, lighthouse, cast, slept).render(
            shot_of(lighthouse, 0, [0]), 1, 6, 1280, 720
        )
    assert store.objects == {} and fal.gets == []


async def test_an_all_black_drawing_is_redrawn_even_unflagged_and_never_stored(
    fal: Fal, lighthouse: Screenplay, cast: Extraction, slept: list[float]
) -> None:
    fal.blacks = [True]
    store = MemoryStore()
    frame = await renderer(fal, store, lighthouse, cast, slept).render(
        shot_of(lighthouse, 0, [0]), 1, 8, 1280, 720
    )
    assert frame.seed == derived_seed(8, 1) and len(store.objects) == 1
    brightest = Image.open(io.BytesIO(frame.png)).convert("L").getextrema()[1]
    assert isinstance(brightest, int) and brightest > 0
