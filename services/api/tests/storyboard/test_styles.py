"""The style registry: storyboard.md §3.2 and §9. Temporary directories, no network."""

from pathlib import Path

import pytest

from app.storyboard import (
    PUBLIC_STYLES,
    SUBJECT_WORDS,
    Style,
    StyleError,
    StyleOrigin,
    load_styles,
)

GOOD = """\
label = "Test sketch"
description = "A test style."
medium = "storyboard sketch, pencil drawing"
finish = "grayscale, monochrome"
grayscale = true
"""


def write(directory: Path, key: str, body: str, *, default: bool = False) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{key}.toml"
    path.write_text(body + ("default = true\n" if default else ""), encoding="utf-8")
    return path


@pytest.fixture
def public(tmp_path: Path) -> Path:
    directory = tmp_path / "public"
    write(directory, "clean", GOOD, default=True)
    return directory


def test_the_repo_styles_are_clean_ink_and_pencil_all_public_with_clean_the_default() -> None:
    registry = load_styles(PUBLIC_STYLES, None)
    assert [s.key for s in registry.public()] == ["clean", "ink", "pencil"]
    assert registry.default == "clean"
    assert registry.get(None).key == "clean"
    assert all(s.origin is StyleOrigin.PUBLIC for s in registry.styles.values())
    ink = registry.get("ink")
    assert ink.emphasis == 1.3
    assert ink.grayscale


def test_a_file_loads_into_a_style_with_optional_fields_defaulted(public: Path) -> None:
    registry = load_styles(public, None)
    assert registry.get("clean") == Style(
        key="clean",
        label="Test sketch",
        description="A test style.",
        medium="storyboard sketch, pencil drawing",
        finish="grayscale, monochrome",
        emphasis=None,
        negative="",
        grayscale=True,
        default=True,
        origin=StyleOrigin.PUBLIC,
    )


def test_private_styles_load_as_private_and_origin_comes_from_the_directory(
    public: Path, tmp_path: Path
) -> None:
    private = tmp_path / "private"
    write(private, "noir", GOOD + 'origin = "public"\n')
    with pytest.raises(StyleError, match=r"noir\.toml"):
        load_styles(public, private)  # `origin` is not a field a file can set

    write(private, "noir", GOOD + "emphasis = 1.2\n")
    registry = load_styles(public, private)
    assert registry.get("noir").origin is StyleOrigin.PRIVATE
    assert [s.key for s in registry.public()] == ["clean"]


def test_unknown_key_is_a_style_error(public: Path) -> None:
    with pytest.raises(StyleError, match="nope"):
        load_styles(public, None).get("nope")


@pytest.mark.parametrize(
    ("body", "why"),
    [
        (GOOD.replace('finish = "grayscale, monochrome"\n', ""), "finish"),  # missing
        (GOOD + 'colour = "blue"\n', "colour"),  # unknown
        (GOOD.replace("grayscale = true", 'grayscale = "yes"'), "grayscale"),  # mistyped
        (GOOD + 'emphasis = "1.3"\n', "emphasis"),  # mistyped
        (GOOD + "emphasis = true\n", "emphasis"),  # a bool is not a weight
        (GOOD + "emphasis = nan\n", "emphasis"),
        (GOOD + "emphasis = inf\n", "emphasis"),
        (GOOD + "emphasis = 0.0\n", "emphasis"),
        (GOOD.replace('label = "Test sketch"', "label = 3"), "label"),
        (GOOD.replace('medium = "storyboard sketch, pencil drawing"', 'medium = ""'), "medium"),
        (GOOD + "default = 1\n", "default"),
        ("label = [", "TOML"),  # not TOML at all
    ],
)
def test_a_missing_unknown_or_mistyped_field_fails_naming_the_file(
    public: Path, body: str, why: str
) -> None:
    write(public, "bad", body)
    with pytest.raises(StyleError, match=r"bad\.toml") as error:
        load_styles(public, None)
    assert why in str(error.value)


@pytest.mark.parametrize("field", ["medium", "finish", "negative"])
@pytest.mark.parametrize("syntax", ["(", ")", ":"])
def test_weight_syntax_is_rejected(public: Path, field: str, syntax: str) -> None:
    body = GOOD + 'negative = "blurry"\n'
    line = next(line for line in body.splitlines() if line.startswith(f"{field} ="))
    write(public, "weighted", body.replace(line, line[:-1] + f' pencil{syntax}1.2"'))
    with pytest.raises(StyleError, match=r"weighted\.toml"):
        load_styles(public, None)


@pytest.mark.parametrize("field", ["medium", "finish"])
@pytest.mark.parametrize("word", ["Woman", "figures", "LOGO", "text"])
def test_a_subject_word_in_medium_or_finish_is_rejected(
    public: Path, field: str, word: str
) -> None:
    line = next(line for line in GOOD.splitlines() if line.startswith(f"{field} ="))
    write(public, "subject", GOOD.replace(line, line[:-1] + f', {word}-drawing"'))
    with pytest.raises(StyleError, match=r"subject\.toml") as error:
        load_styles(public, None)
    assert word.lower() in str(error.value)


def test_subject_words_inside_other_words_and_in_the_negative_are_fine(public: Path) -> None:
    body = GOOD.replace("pencil drawing", "manga pencil drawing, signed-off linework")
    write(public, "fine", body + 'negative = "text, watermark, people"\n')
    assert load_styles(public, None).get("fine").negative == "text, watermark, people"


def test_subject_words_are_the_designed_list() -> None:
    assert frozenset(
        {
            "person", "people", "man", "men", "woman", "women", "boy", "girl", "child",
            "children", "figure", "figures", "crowd", "character", "face", "portrait", "animal",
            "text", "letters", "words", "caption", "logo", "sign", "signature", "watermark",
        }
    ) == SUBJECT_WORDS  # fmt: skip


def test_a_private_style_cannot_shadow_a_public_one(public: Path, tmp_path: Path) -> None:
    write(tmp_path / "private", "clean", GOOD)
    with pytest.raises(StyleError, match=r"clean\.toml"):
        load_styles(public, tmp_path / "private")


def test_the_default_cannot_be_private(tmp_path: Path) -> None:
    write(tmp_path / "public", "clean", GOOD)
    write(tmp_path / "private", "noir", GOOD, default=True)
    with pytest.raises(StyleError, match=r"noir\.toml"):
        load_styles(tmp_path / "public", tmp_path / "private")


def test_exactly_one_default(public: Path, tmp_path: Path) -> None:
    write(public, "ink", GOOD, default=True)
    with pytest.raises(StyleError, match="default"):
        load_styles(public, None)
    write(tmp_path / "none", "clean", GOOD)
    with pytest.raises(StyleError, match="default"):
        load_styles(tmp_path / "none", None)


def test_no_public_style_fails(tmp_path: Path) -> None:
    (tmp_path / "empty").mkdir()
    write(tmp_path / "private", "noir", GOOD, default=True)
    with pytest.raises(StyleError, match="no public style"):
        load_styles(tmp_path / "empty", tmp_path / "private")


def test_a_missing_directory_fails(public: Path, tmp_path: Path) -> None:
    with pytest.raises(StyleError, match="missing"):
        load_styles(tmp_path / "missing", None)
    with pytest.raises(StyleError, match="elsewhere"):
        load_styles(public, tmp_path / "elsewhere")


# "Ink", not "Clean": on a case-insensitive filesystem (Windows, macOS) Clean.toml
# would overwrite the fixture's clean.toml
@pytest.mark.parametrize("stem", ["Ink", "ink_2", "pencil study"])
def test_a_key_must_be_lower_case_letters_digits_and_hyphens(public: Path, stem: str) -> None:
    write(public, stem, GOOD)
    with pytest.raises(StyleError, match=stem):
        load_styles(public, None)
