"""SupabaseStore against Supabase Storage's REST API, as it answered on 2026-10-02 (T053;
storyboard.md §6). No network: httpx2.MockTransport replays those answers."""

import json
import logging

import httpx2
import pytest

from app.storage import AssetNotFound, StorageError, SupabaseStore

URL = "https://example.supabase.co"
OBJ = f"{URL}/storage/v1/object/panelwise-dev"
DUPLICATE = {"statusCode": "409", "error": "Duplicate", "message": "The resource already exists"}
MISSING = {"statusCode": "404", "error": "not_found", "message": "Object not found"}


def store(handler: httpx2.MockTransport, slept: list[float] | None = None) -> SupabaseStore:
    """A store whose waits between attempts are recorded in `slept`, never slept."""
    client = httpx2.AsyncClient(transport=handler)
    record = [] if slept is None else slept

    async def sleep(seconds: float) -> None:
        record.append(seconds)

    return SupabaseStore(
        url=URL, secret_key="sb_secret_x", bucket="panelwise-dev", client=client, sleep=sleep
    )


def requests_to(
    *answers: httpx2.Response | Exception,
) -> tuple[httpx2.MockTransport, list[httpx2.Request]]:
    """Each request gets the next answer; an exception is raised as the transport's."""
    seen: list[httpx2.Request] = []
    queue = list(answers)

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        answer = queue.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    return httpx2.MockTransport(handler), seen


async def test_put_uploads_without_upsert_using_the_secret_key() -> None:
    transport, seen = requests_to(httpx2.Response(200, json={"Key": "k"}))
    await store(transport).put("scripts/u/p.pdf", b"%PDF-1.7", "application/pdf")
    (req,) = seen
    assert (req.method, str(req.url)) == ("POST", f"{OBJ}/scripts/u/p.pdf")
    assert req.headers["authorization"] == "Bearer sb_secret_x"
    assert req.headers["apikey"] == "sb_secret_x"
    assert req.headers["x-upsert"] == "false"
    assert req.headers["content-type"] == "application/pdf"
    assert req.read() == b"%PDF-1.7"


@pytest.mark.parametrize(
    "answer", [httpx2.Response(400, json=DUPLICATE), httpx2.Response(409, json=DUPLICATE)]
)
async def test_put_of_an_existing_path_is_a_success(answer: httpx2.Response) -> None:
    transport, _ = requests_to(answer)
    await store(transport).put("a.png", b"x", "image/png")  # idempotent: no error


async def test_put_failing_otherwise_raises() -> None:
    transport, _ = requests_to(*[httpx2.Response(500, json={"message": "boom"})] * 3)
    with pytest.raises(StorageError):
        await store(transport).put("a.png", b"x", "image/png")


async def test_get_returns_the_bytes_and_a_missing_object_is_not_found() -> None:
    transport, seen = requests_to(
        httpx2.Response(200, content=b"one"), httpx2.Response(400, json=MISSING)
    )
    s = store(transport)
    assert await s.get("scripts/u/p.pdf") == b"one"
    with pytest.raises(AssetNotFound):
        await s.get("scripts/u/missing.pdf")
    assert [r.method for r in seen] == ["GET", "GET"]


async def test_exists_is_a_head_request() -> None:
    transport, seen = requests_to(httpx2.Response(200), httpx2.Response(400), httpx2.Response(404))
    s = store(transport)
    assert await s.exists("a.png") is True
    assert await s.exists("b.png") is False
    assert await s.exists("c.png") is False
    assert {r.method for r in seen} == {"HEAD"}


async def test_exists_on_an_outage_raises_rather_than_answering_no() -> None:
    transport, _ = requests_to(*[httpx2.Response(503)] * 3)
    with pytest.raises(StorageError):
        await store(transport).exists("a.png")


async def test_signed_url_is_the_full_url_storage_signs() -> None:
    signed = "/object/sign/panelwise-dev/a.png?token=abc"
    transport, seen = requests_to(httpx2.Response(200, json={"signedURL": signed}))
    assert await store(transport).signed_url("a.png", 300) == f"{URL}/storage/v1{signed}"
    (req,) = seen
    assert str(req.url) == f"{URL}/storage/v1/object/sign/panelwise-dev/a.png"
    assert json.loads(req.read()) == {"expiresIn": 300}


async def test_a_path_is_quoted_segment_by_segment() -> None:
    transport, seen = requests_to(httpx2.Response(200, content=b""))
    await store(transport).get("scripts/a b/c#d.pdf")
    assert str(seen[0].url) == f"{OBJ}/scripts/a%20b/c%23d.pdf"


# --- T070: a transient failure is tried again (storyboard.md §4, §6) ------------------------------


def dropped(request_url: str = OBJ) -> httpx2.ConnectError:
    return httpx2.ConnectError("connection reset", request=httpx2.Request("POST", request_url))


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504, 520, 521, 522, 523, 524])
async def test_a_transient_status_on_put_is_tried_again_after_a_second(status: int) -> None:
    transport, seen = requests_to(httpx2.Response(status), httpx2.Response(200, json={"Key": "k"}))
    slept: list[float] = []
    await store(transport, slept).put("frames/a.png", b"x", "image/png")
    assert len(seen) == 2 and slept == [1.0]


async def test_a_put_that_landed_before_its_520_comes_back_409_which_is_success() -> None:
    transport, seen = requests_to(httpx2.Response(520), httpx2.Response(400, json=DUPLICATE))
    await store(transport).put("frames/a.png", b"x", "image/png")
    assert len(seen) == 2


async def test_three_failures_raise_naming_the_status_and_the_attempts_after_1_and_2_s() -> None:
    transport, seen = requests_to(*[httpx2.Response(503)] * 3)
    slept: list[float] = []
    with pytest.raises(StorageError, match=r"^put: storage answered 503 after 3 attempts$"):
        await store(transport, slept).put("frames/a.png", b"x", "image/png")
    assert len(seen) == 3 and slept == [1.0, 2.0]


async def test_a_dropped_connection_is_tried_again() -> None:
    transport, seen = requests_to(dropped(), httpx2.Response(200, content=b"png"))
    assert await store(transport).get("frames/a.png") == b"png"
    assert len(seen) == 2


async def test_a_storage_that_stays_unreachable_raises_storage_error_not_the_httpx_one() -> None:
    transport, _ = requests_to(dropped(), dropped(), dropped())
    with pytest.raises(StorageError, match=r"^get: storage unreachable after 3 attempts$") as err:
        await store(transport).get("frames/a.png")
    assert not isinstance(err.value, httpx2.TransportError)


@pytest.mark.parametrize("status", [400, 401, 403, 413])
async def test_a_4xx_is_answered_at_once(status: int) -> None:
    transport, seen = requests_to(httpx2.Response(status, json={"message": "no"}))
    slept: list[float] = []
    with pytest.raises(StorageError, match=f"^put: storage answered {status}$"):
        await store(transport, slept).put("frames/a.png", b"x", "image/png")
    assert len(seen) == 1 and slept == []


async def test_exists_and_signed_url_are_tried_again_too() -> None:
    signed = "/object/sign/panelwise-dev/a.png?token=abc"
    transport, seen = requests_to(
        httpx2.Response(502),
        httpx2.Response(200),
        dropped(),
        httpx2.Response(200, json={"signedURL": signed}),
    )
    s = store(transport)
    assert await s.exists("a.png") is True
    assert await s.signed_url("a.png", 60) == f"{URL}/storage/v1{signed}"
    assert len(seen) == 4


async def test_a_retry_is_logged_without_the_key_or_the_path(
    caplog: pytest.LogCaptureFixture,
) -> None:
    transport, _ = requests_to(
        httpx2.Response(520), dropped(), httpx2.Response(200, json={"Key": "k"})
    )
    with caplog.at_level(logging.WARNING, logger="app.storage.store"):
        await store(transport).put("frames/secret-path.png", b"x", "image/png")
    messages = [r.getMessage() for r in caplog.records]
    assert messages == [
        "storage put: HTTP 520 (attempt 1 of 3)",
        "storage put: ConnectError (attempt 2 of 3)",
    ]
    assert not any("sb_secret_x" in m or "secret-path" in m for m in messages)
