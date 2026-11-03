"""T122: SupabaseStore.signed_urls, a page's links in one request (storyboard.md §6, §9 T122).
No network: httpx2.MockTransport replays Supabase's batch answer as measured on 2026-10-19."""

import json

import httpx2
import pytest

from app.storage import StorageError
from tests.storage.test_store import URL, requests_to, store

SIGN = f"{URL}/storage/v1/object/sign/panelwise-dev"


def signed(path: str) -> dict[str, object]:
    return {"error": None, "path": path, "signedURL": f"/object/sign/panelwise-dev/{path}?token=t"}


def batch_answer(request_paths: list[str]) -> httpx2.Response:
    return httpx2.Response(200, json=[signed(p) for p in request_paths])


def echo() -> tuple[httpx2.MockTransport, list[httpx2.Request]]:
    """Signs whatever paths each request asks for, in their order."""
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return batch_answer(json.loads(request.content)["paths"])

    return httpx2.MockTransport(handler), seen


def link(path: str) -> str:
    return f"{URL}/storage/v1/object/sign/panelwise-dev/{path}?token=t"


async def test_one_request_signs_every_path_in_order() -> None:
    transport, seen = echo()
    paths = ["frames/b.png", "frames/a.png", "frames/c.png"]

    assert await store(transport).signed_urls(paths, 3600) == [link(p) for p in paths]
    (req,) = seen
    assert (req.method, str(req.url)) == ("POST", SIGN)
    assert json.loads(req.content) == {"expiresIn": 3600, "paths": paths}
    assert req.headers["authorization"] == "Bearer sb_secret_x"


async def test_a_path_asked_twice_is_signed_twice_in_its_place() -> None:
    transport, _ = echo()
    paths = ["frames/a.png", "frames/b.png", "frames/a.png"]

    assert await store(transport).signed_urls(paths, 60) == [link(p) for p in paths]


async def test_more_than_a_hundred_paths_go_in_order_in_chunks_of_a_hundred() -> None:
    transport, seen = echo()
    paths = [f"frames/{i:03}.png" for i in range(150)]

    assert await store(transport).signed_urls(paths, 60) == [link(p) for p in paths]
    assert [len(json.loads(r.content)["paths"]) for r in seen] == [100, 50]
    assert json.loads(seen[1].content)["paths"][0] == "frames/100.png"


async def test_no_paths_make_no_request() -> None:
    transport, seen = echo()

    assert await store(transport).signed_urls([], 60) == []
    assert seen == []


async def test_an_unsigned_item_fails_the_call_naming_the_count_not_the_path() -> None:
    answer = [
        signed("frames/a.png"),
        {
            "error": "Either the object does not exist",
            "path": "frames/secret.png",
            "signedURL": None,
        },
    ]
    transport, _ = requests_to(httpx2.Response(200, json=answer))

    with pytest.raises(StorageError) as raised:
        await store(transport).signed_urls(["frames/a.png", "frames/secret.png"], 60)
    assert str(raised.value) == "signed_urls: storage could not sign 1 of 2"
    assert "secret" not in str(raised.value)


async def test_a_refused_request_is_a_storage_error() -> None:
    transport, _ = requests_to(httpx2.Response(403, json={"statusCode": "403"}))

    with pytest.raises(StorageError, match="signed_urls: storage answered 403"):
        await store(transport).signed_urls(["frames/a.png"], 60)


async def test_a_transient_failure_is_tried_again_as_t070() -> None:
    transport, seen = requests_to(
        httpx2.Response(503), batch_answer(["frames/a.png", "frames/b.png"])
    )
    slept: list[float] = []

    links = await store(transport, slept).signed_urls(["frames/a.png", "frames/b.png"], 60)
    assert links == [link("frames/a.png"), link("frames/b.png")]
    assert (len(seen), slept) == (2, [1.0])
