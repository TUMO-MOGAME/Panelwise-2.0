"""The committed reference pages (comic.md §2, §9 Visual) are a fresh render of the sample."""

import io

from PIL import Image

from app.comic import CaptionKind
from app.script import Dialogue, parse_pdf
from tools.build_comic_reference import REFERENCE, SAMPLE, WITHHELD, build, page_path
from tools.build_samples import SAMPLES


def test_the_committed_reference_pages_are_a_fresh_render() -> None:
    book, pages = build()
    committed = sorted(REFERENCE.glob(f"{SAMPLE}-page-*.png"))
    assert len(committed) == len(pages) == len(book.pages)
    for number, data in enumerate(pages, start=1):
        fresh = Image.open(io.BytesIO(data)).convert("RGB")
        stored = Image.open(page_path(number)).convert("RGB")
        assert fresh.size == stored.size == (1988, 3075)
        # Compared as pixels, not bytes: a zlib change may re-encode, never re-draw.
        assert fresh.tobytes() == stored.tobytes(), f"page {number}: rebuild the reference"


def test_the_reference_letters_every_line_of_the_sample_and_withholds_one_frame() -> None:
    book, _ = build()
    screenplay = parse_pdf((SAMPLES / f"{SAMPLE}.pdf").read_bytes())
    spoken = sorted(
        (scene.index, i, e.text)
        for scene in screenplay.scenes
        for i, e in enumerate(scene.elements)
        if isinstance(e, Dialogue)
    )
    panels = [p for page in book.pages for p in page.panels]
    lettered = sorted(
        [(p.scene_index, b.element, b.text) for p in panels for b in p.bubbles]
        + [
            (p.scene_index, c.element, c.text)
            for p in panels
            for c in p.captions
            if c.kind is CaptionKind.VOICE_OVER and c.element is not None
        ]
    )
    assert lettered == spoken
    withheld = next(p for p in panels if (p.scene_index, p.shot_number) == WITHHELD)
    assert withheld.bubbles  # the card still carries the panel's lines
