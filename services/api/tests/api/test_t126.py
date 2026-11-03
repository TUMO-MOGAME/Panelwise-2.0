"""T126: a downloaded PDF is named by its screenplay (web.md §4.5). Pure."""

from urllib.parse import parse_qs, urlparse

import pytest

from app.api.v1.downloads import download_name, with_download


@pytest.mark.parametrize(
    ("title", "kind", "want"),
    [
        ("the-borrowed-bicycle", "storyboard", "the-borrowed-bicycle storyboard.pdf"),
        ("The Keeper's Light", "comic", "The Keeper's Light comic.pdf"),
        ('a/b\\c:d*e?f"g<h>i|j', "comic", "a-b-c-d-e-f-g-h-i-j comic.pdf"),  # every unsafe one
        ("tab\there\nnew\x00line", "comic", "tab-here-new-line comic.pdf"),  # control characters
        ("  lots   of\u00a0space  ", "storyboard", "lots of space storyboard.pdf"),
        ("Ụmụ́ akwụkwọ", "comic", "Ụmụ́ akwụkwọ comic.pdf"),  # letters beyond ASCII stay
        ("", "storyboard", "Panelwise storyboard.pdf"),
        ("   ", "comic", "Panelwise comic.pdf"),
    ],
)
def test_download_name(title: str, kind: str, want: str) -> None:
    assert download_name(title, kind) == want  # type: ignore[arg-type]


def test_a_long_title_is_cut_to_80_characters() -> None:
    name = download_name("x" * 200, "storyboard")
    assert name == "x" * 80 + " storyboard.pdf"
    assert (
        download_name("word " * 40, "comic") == ("word " * 16).strip() + " comic.pdf"
    )  # no trailing space


@pytest.mark.parametrize(
    ("url", "joiner"),
    [("https://s/obj/a.pdf?token=t", "&"), ("https://s/obj/a.pdf", "?")],
)
def test_with_download_adds_the_name_to_the_link(url: str, joiner: str) -> None:
    named = with_download(url, "The Keeper's Light comic.pdf")
    assert named.startswith(url + joiner + "download=")
    assert parse_qs(urlparse(named).query)["download"] == ["The Keeper's Light comic.pdf"]
    assert " " not in named  # quoted, so the link stays one URL
