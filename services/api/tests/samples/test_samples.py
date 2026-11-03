"""The sample screenplays in samples/ (T031): each committed PDF is a fresh build of its source,
parses with the real parser, and reads the way samples/README.md says it does."""

import pytest

from app.grounding.text import locate, normalize_for_grounding
from app.script import Dialogue, Screenplay, parse_pdf
from tools.build_samples import OPTIONS, SAMPLES, build, speakers

NAMES = sorted(OPTIONS)


def committed(name: str) -> Screenplay:
    return parse_pdf((SAMPLES / f"{name}.pdf").read_bytes())


def readme_row(name: str) -> dict[str, str]:
    """The README table row for a sample, as {column header: cell}."""
    lines = (SAMPLES / "README.md").read_text(encoding="utf-8").splitlines()
    header = next(line for line in lines if line.startswith("| Sample |"))
    row = next(line for line in lines if line.startswith(f"| [`{name}`]"))
    cells = [c.strip() for c in row.strip("|").split("|")]
    return dict(zip([h.strip() for h in header.strip("|").split("|")], cells, strict=True))


def test_every_sample_has_a_source_a_pdf_and_build_options() -> None:
    sources = {p.stem for p in SAMPLES.glob("*.fountain")}
    pdfs = {p.stem for p in SAMPLES.glob("*.pdf")}
    assert sources == pdfs == set(OPTIONS)


@pytest.mark.parametrize("name", NAMES)
def test_committed_pdf_is_a_fresh_build_of_its_source(name: str) -> None:
    # Compared as parsed, not as bytes: an fpdf2 upgrade may change the bytes, never the text.
    assert committed(name) == parse_pdf(build(name))


@pytest.mark.parametrize("name", NAMES)
def test_counts_match_the_readme(name: str) -> None:
    screenplay = committed(name)
    row = readme_row(name)
    assert int(row["Pages"]) == screenplay.page_count
    assert int(row["Scenes"]) == len(screenplay.scenes)
    assert int(row["Speaking characters"]) == len(speakers(screenplay))


# The elements whose text is not their span's lines joined by plain spaces: each one joins a
# line-break hyphen, and nothing else (script.md §3, §9; T048). Keyed by the span's first line.
JOINED_AT_A_HYPHEN = {
    "the-red-kite": {},
    "lost-property": {440: "on the nine-fifteen."},
    "sipho-and-siphokazi": {
        79: "a sea-green oilskin",
        88: "nineteen-ninety-something",
        213: "in the teeth of a south-westerly.",
    },
    "the-night-taxi": {210: "The prize-giving was tonight?"},
    "market-day": {},
    "the-lighthouse-inspector": {},
    "the-borrowed-bicycle": {},
    "rooftop-tomatoes": {},
    "load-shedding": {},
    "gogos-recipe": {},
    "stormwater": {},
    "the-choir": {},
    "final-whistle": {},
}


@pytest.mark.parametrize("name", NAMES)
def test_only_a_line_break_hyphen_changes_an_element_from_its_span_lines(name: str) -> None:
    screenplay = committed(name)
    lines = screenplay.text.split("\n")
    changed: dict[int, str] = {}
    for scene in screenplay.scenes:
        for element in scene.elements:
            source = lines[element.span.line_start - 1 : element.span.line_end]
            if " ".join(line.strip() for line in source) != element.text:
                changed[element.span.line_start] = element.text
    expected = JOINED_AT_A_HYPHEN[name]
    assert changed.keys() == expected.keys()
    for line, words in expected.items():
        assert words in changed[line]


@pytest.mark.parametrize("name", NAMES)
def test_every_element_normalises_to_its_span_lines(name: str) -> None:
    # script.md §9 (T048): a quote copied from element text is always located at its span.
    screenplay = committed(name)
    lines = screenplay.text.split("\n")
    for scene in screenplay.scenes:
        for element in scene.elements:
            source = "\n".join(lines[element.span.line_start - 1 : element.span.line_end])
            assert normalize_for_grounding(element.text) == normalize_for_grounding(source)
            # The first match in script order: a repeated line may sit at an earlier span.
            assert locate(element.text, screenplay) is not None


def test_line_break_hyphens_are_joined_in_the_tricky_sample() -> None:
    texts = [e.text for s in committed("sipho-and-siphokazi").scenes for e in s.elements]
    assert any("a sea-green oilskin" in t for t in texts)
    assert any("in the teeth of a south-westerly." in t for t in texts)
    assert not any(" sea- " in t or "south- " in t for t in texts)
    signs = [e.text for s in committed("lost-property").scenes for e in s.elements]
    assert any("LOST PROPERTY - PLATFORM 9" in t for t in signs)


def test_the_choir_splits_its_long_speech_over_a_page() -> None:
    elements = [e for s in committed("the-choir").scenes for e in s.elements]
    speeches = [e for e in elements if isinstance(e, Dialogue)]
    split = next(i for i, d in enumerate(speeches) if d.extension == "CONT'D")
    before, after = speeches[split - 1], speeches[split]
    assert before.cue == after.cue == "MAMA GRACE"
    assert after.span.page == before.span.page + 1


@pytest.mark.parametrize("name", NAMES)
def test_page_starts_mark_each_page_of_the_text(name: str) -> None:
    screenplay = committed(name)
    starts = screenplay.page_starts
    assert starts[0] == 1
    assert len(starts) == screenplay.page_count
    assert list(starts) == sorted(set(starts))
    assert starts[-1] <= len(screenplay.text.split("\n"))
    # Every element sits on the page whose lines contain its first line.
    for scene in screenplay.scenes:
        for element in scene.elements:
            page = element.span.page
            end = starts[page] if page < len(starts) else len(screenplay.text.split("\n")) + 1
            assert starts[page - 1] <= element.span.line_start < end


def test_the_demo_script_has_what_the_demo_shows() -> None:
    screenplay = committed("the-red-kite")
    times = {scene.time_of_day for scene in screenplay.scenes}
    assert {"DAY", "NIGHT", "CONTINUOUS"} <= times
    assert {scene.int_ext.value for scene in screenplay.scenes} == {"INT", "EXT"}
    speeches = [e for s in screenplay.scenes for e in s.elements if isinstance(e, Dialogue)]
    assert {"O.S.", "V.O.", "CONT'D"} <= {d.extension for d in speeches}
    assert any(d.parenthetical for d in speeches)
    # The (MORE) / (CONT'D) split: one speaker's speech continues at the top of the next page.
    split = next(i for i, d in enumerate(speeches) if d.extension == "CONT'D")
    before, after = speeches[split - 1], speeches[split]
    assert before.cue == after.cue
    assert after.span.page == before.span.page + 1
