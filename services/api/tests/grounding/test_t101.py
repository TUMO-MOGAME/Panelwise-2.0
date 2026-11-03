"""T101: a bare character name folds into its one titled spelling, a cue or a model name the script
writes whose words are it plus forms of address (grounding.md §3, §6, §9; L022). Each case is its
own self-written script, so no cue is another case's titled spelling; no model."""

from app.characters.sex import Sex
from app.grounding import Entity, EntityKind, ProposedEntity, Source, ground
from app.grounding.filter import (  # pyright: ignore[reportPrivateUsage]
    _fold_titled,  # pyright: ignore[reportPrivateUsage]
    _Group,  # pyright: ignore[reportPrivateUsage]
)
from app.grounding.model import GroundingReport
from app.grounding.text import normalize_for_grounding
from app.script import Screenplay, normalise, parse_text
from tests.script.conftest import ACTION, CUE, DIALOGUE, Row, heading, layout


def script(*rows: Row) -> Screenplay:
    """One scene: its heading, then each row with a blank line after it, except a cue, which its
    speech follows directly."""
    out: list[Row] = [(CUE - 4, "FOLD TESTS"), None, heading("1", "INT. LIGHTHOUSE - NIGHT"), None]
    for row in rows:
        out += [row] if row is not None and row[0] == CUE else [row, None]
    return parse_text(layout(out), [])


def person(name: str, *quotes: str, word: str | None = None) -> ProposedEntity:
    return ProposedEntity.model_validate(
        {"kind": "character", "name": name, "quotes": list(quotes), "sex_word": word}
    )


def prop(name: str, quote: str) -> ProposedEntity:
    return ProposedEntity.model_validate({"kind": "prop", "name": name, "quotes": [quote]})


def grounded(
    screenplay: Screenplay, *proposals: ProposedEntity
) -> tuple[dict[str, Entity], GroundingReport]:
    entities, report = ground(list(proposals), screenplay)
    return {e.name: e for e in entities if e.kind is EntityKind.CHARACTER}, report


CLIMBS = "MR. FORTUIN (70s) climbs the stairs, one hand on the rail."
LAMP = "The lamp has not missed a night."
FORTUIN = script((ACTION, CLIMBS), (CUE, "MR. FORTUIN"), (DIALOGUE, LAMP))


def test_a_bare_name_takes_its_cues_titled_spelling() -> None:
    characters, report = grounded(FORTUIN, person("FORTUIN", CLIMBS))
    assert list(characters) == ["MR. FORTUIN"]
    fortuin = characters["MR. FORTUIN"]
    assert fortuin.source is Source.MODEL
    assert [q.text for q in fortuin.quotes] == [CLIMBS]
    assert fortuin.other_names == ("FORTUIN",)
    assert fortuin.scenes == (0,)
    assert (report.cues_found_by_model, report.cues_total) == (1, 1)
    assert (report.entities_proposed, report.entities_grounded) == (1, 1)


def test_a_bare_name_merges_into_the_models_own_titled_name() -> None:
    characters, report = grounded(
        FORTUIN, person("FORTUIN", CLIMBS), person("MR. FORTUIN", LAMP, CLIMBS)
    )
    assert list(characters) == ["MR. FORTUIN"]
    fortuin = characters["MR. FORTUIN"]
    assert fortuin.source is Source.MODEL
    assert [q.text for q in fortuin.quotes] == [LAMP, CLIMBS]
    assert fortuin.other_names == ("FORTUIN",)
    assert (report.entities_proposed, report.entities_grounded) == (1, 1)
    assert report.quotes_proposed == 2  # the bare group's CLIMBS is already the titled one's


def test_one_unlocated_quote_fails_the_merged_group_but_keeps_it() -> None:
    characters, report = grounded(
        FORTUIN, person("FORTUIN", CLIMBS), person("MR. FORTUIN", "He was never late.")
    )
    assert [q.text for q in characters["MR. FORTUIN"].quotes] == [CLIMBS]
    assert (report.entities_proposed, report.entities_grounded) == (1, 0)


def test_a_titled_model_name_the_script_never_writes_is_no_spelling() -> None:
    bare = script((ACTION, "Mr Fortuin climbs the stairs. The lamp turns."))
    # The titled spelling keeps its full stop, so "Mr Fortuin" doesn't mention it.
    assert "mr. fortuin" not in normalize_for_grounding(bare.text).lower()
    characters, _ = grounded(
        bare,
        person("MR. FORTUIN", "Mr Fortuin climbs the stairs."),
        person("FORTUIN", "Mr Fortuin climbs the stairs."),
    )
    assert "MR. FORTUIN" not in characters
    assert characters["FORTUIN"].source is Source.MODEL


def test_the_folded_name_reads_its_own_pronouns() -> None:
    naidoo = script(
        (ACTION, "MS. NAIDOO (50s) waits. Ms. Naidoo checks her logbook."),
        (CUE, "MS. NAIDOO"),
        (DIALOGUE, "Nine o'clock. All quiet."),
    )
    characters, _ = grounded(naidoo, person("NAIDOO", "MS. NAIDOO (50s) waits."))
    assert list(characters) == ["MS. NAIDOO"]
    assert characters["MS. NAIDOO"].sex is Sex.FEMALE


PIPE = script(
    (ACTION, "MR. FORTUIN (70s) waits. Fortuin taps his pipe."),
    (CUE, "MR. FORTUIN"),
    (DIALOGUE, "Evening."),
)


def test_a_sentence_opening_with_the_folded_bare_name_is_his() -> None:
    characters, _ = grounded(PIPE, person("FORTUIN", "MR. FORTUIN (70s) waits.", word="he"))
    assert characters["MR. FORTUIN"].sex is Sex.MALE
    assert characters["MR. FORTUIN"].sex_quote is not None
    assert characters["MR. FORTUIN"].sex_quote.text == "Fortuin taps his pipe."


def test_an_other_name_that_was_not_folded_opens_nothing() -> None:
    kazi = script(
        (ACTION, "SIPHOKAZI (17) waits. Kazi taps her pen."),
        (CUE, "SIPHOKAZI"),
        (DIALOGUE, "Ready."),
    )
    proposal = ProposedEntity.model_validate(
        {
            "kind": "character",
            "name": "SIPHOKAZI",
            "quotes": ["SIPHOKAZI (17) waits."],
            "other_names": ["Kazi"],
            "sex_word": "she",
        }
    )
    characters, _ = grounded(kazi, proposal)
    assert characters["SIPHOKAZI"].sex is None


def test_sex_words_that_disagree_across_the_two_groups_give_no_sex() -> None:
    characters, _ = grounded(
        PIPE,
        person("FORTUIN", "MR. FORTUIN (70s) waits.", word="she"),
        person("MR. FORTUIN", "Evening.", word="he"),
    )
    # Without the bare group's "she", the "he" claim and "Fortuin taps his pipe." give male.
    assert characters["MR. FORTUIN"].sex is None


def test_a_name_with_a_particle_folds() -> None:
    merwe = script(
        (ACTION, "MR. VAN DER MERWE (60s) counts the till."),
        (CUE, "MR. VAN DER MERWE"),
        (DIALOGUE, "Short again."),
    )
    characters, _ = grounded(
        merwe, person("VAN DER MERWE", "MR. VAN DER MERWE (60s) counts the till.")
    )
    assert list(characters) == ["MR. VAN DER MERWE"]
    assert characters["MR. VAN DER MERWE"].other_names == ("VAN DER MERWE",)


def test_a_kinship_word_is_no_title() -> None:
    thembi = script(
        (ACTION, "THEMBI (8) skips past MAMA THEMBI (60s), who sweeps the shop step."),
        (CUE, "MAMA THEMBI"),
        (DIALOGUE, "We open at seven."),
    )
    characters, _ = grounded(thembi, person("THEMBI", "THEMBI (8) skips past"))
    assert characters["THEMBI"].source is Source.MODEL
    assert characters["MAMA THEMBI"].source is Source.CUE


def test_two_titled_spellings_fold_nothing() -> None:
    dubes = script(
        (ACTION, "MR. DUBE (60s) and MRS. DUBE (60s) sit at the table. Dube pours the tea."),
        (CUE, "MR. DUBE"),
        (DIALOGUE, "Sugar?"),
        (CUE, "MRS. DUBE"),
        (DIALOGUE, "Two."),
    )
    characters, _ = grounded(dubes, person("DUBE", "Dube pours the tea."))
    assert characters["DUBE"].source is Source.MODEL
    assert characters["MR. DUBE"].source is Source.CUE
    assert characters["MRS. DUBE"].source is Source.CUE


def test_a_bare_cue_folds_nothing() -> None:
    both = script(
        (ACTION, "DUBE (20s) and MR. DUBE (60s) sit at the table."),
        (CUE, "DUBE"),
        (DIALOGUE, "Morning, Pa."),
        (CUE, "MR. DUBE"),
        (DIALOGUE, "Morning."),
    )
    characters, _ = grounded(both, person("DUBE", "DUBE (20s) and MR. DUBE (60s)"))
    assert characters["DUBE"].source is Source.MODEL
    assert characters["MR. DUBE"].source is Source.CUE


def test_a_superset_name_folds_nothing() -> None:
    shared = script(
        (ACTION, "THABO DUBE (9) runs to MR. DUBE (60s). Dube catches him."),
        (CUE, "MR. DUBE"),
        (DIALOGUE, "Slowly!"),
    )
    characters, _ = grounded(
        shared,
        person("DUBE", "Dube catches him."),
        person("THABO DUBE", "THABO DUBE (9) runs to"),
    )
    assert characters["DUBE"].source is Source.MODEL
    assert characters["MR. DUBE"].source is Source.CUE


def test_a_superset_cue_folds_nothing() -> None:
    shared = script(
        (ACTION, "MR. DUBE (60s) waits. Dube checks the clock."),
        (CUE, "MR. DUBE"),
        (DIALOGUE, "Late."),
        (CUE, "THABO DUBE"),
        (DIALOGUE, "Sorry, Pa."),
    )
    characters, _ = grounded(shared, person("DUBE", "Dube checks the clock."))
    assert characters["DUBE"].source is Source.MODEL
    assert characters["MR. DUBE"].source is Source.CUE


def test_two_folds_in_one_script_keep_their_places() -> None:
    two = script(
        (ACTION, "MS. NAIDOO (50s) and MR. FORTUIN (70s) climb the stairs. ZOLA (9) waits."),
        (CUE, "MS. NAIDOO"),
        (DIALOGUE, "Mind the step."),
        (CUE, "MR. FORTUIN"),
        (DIALOGUE, "I know the step."),
    )
    entities, report = ground(
        [
            person("NAIDOO", "MS. NAIDOO (50s) and MR. FORTUIN (70s) climb the stairs."),
            person("ZOLA", "ZOLA (9) waits."),
            person("FORTUIN", "MS. NAIDOO (50s) and MR. FORTUIN (70s) climb the stairs."),
            person("MR. FORTUIN", "I know the step."),
        ],
        two,
    )
    characters = [e for e in entities if e.kind is EntityKind.CHARACTER]
    assert [(c.name, c.source) for c in characters] == [
        ("MR. FORTUIN", Source.MODEL),
        ("MS. NAIDOO", Source.MODEL),
        ("ZOLA", Source.MODEL),
    ]
    assert report.entities_proposed == 3
    assert (report.cues_found_by_model, report.cues_total) == (2, 2)
    # ground sorts its output, so the places are read from the fold itself.
    groups = {
        ("character", normalise(n)): _Group(n, EntityKind.CHARACTER)
        for n in ("NAIDOO", "ZOLA", "FORTUIN", "MR. FORTUIN")
    }
    folded, bare = _fold_titled(groups, two, normalize_for_grounding(two.text))
    assert [g.name for g in folded.values()] == ["MS. NAIDOO", "ZOLA", "MR. FORTUIN"]
    assert list(folded) == [
        ("character", "MS NAIDOO"),
        ("character", "ZOLA"),
        ("character", "MR FORTUIN"),
    ]
    assert bare == {"MS NAIDOO": ("NAIDOO",), "MR FORTUIN": ("FORTUIN",)}


def test_a_first_name_against_a_full_name_folds_nothing() -> None:
    thabo = script(
        (ACTION, "THABO (9) kicks a ball against the wall."),
        (CUE, "THABO MOLEFE"),
        (DIALOGUE, "Again!"),
    )
    characters, _ = grounded(thabo, person("THABO", "THABO (9) kicks a ball against the wall."))
    assert characters["THABO"].source is Source.MODEL
    assert characters["THABO"].other_names == ()
    assert characters["THABO MOLEFE"].source is Source.CUE


def test_a_bare_name_with_no_titled_spelling_is_unchanged() -> None:
    alone = script(
        (ACTION, "FORTUIN (70s) climbs the stairs."), (CUE, "FORTUIN"), (DIALOGUE, "Evening.")
    )
    characters, report = grounded(alone, person("FORTUIN", "FORTUIN (70s) climbs the stairs."))
    assert list(characters) == ["FORTUIN"]
    assert characters["FORTUIN"].other_names == ()
    assert report.cues_found_by_model == 1


def test_a_cue_of_title_words_alone_is_no_titled_spelling() -> None:
    nurse = script(
        (ACTION, "A NURSE (30s) checks the drip. SMITH (80s) sleeps."),
        (CUE, "NURSE"),
        (DIALOGUE, "Rest now."),
    )
    characters, _ = grounded(nurse, person("SMITH", "SMITH (80s) sleeps."))
    assert characters["SMITH"].other_names == ()
    assert characters["NURSE"].source is Source.CUE


def test_a_prop_never_folds() -> None:
    kite = script(
        (ACTION, "MR. KITE (40s) flies a red KITE."), (CUE, "MR. KITE"), (DIALOGUE, "Higher!")
    )
    entities, _ = ground([prop("KITE", "flies a red KITE")], kite)
    assert [(e.kind, e.name) for e in entities if e.kind is not EntityKind.LOCATION] == [
        (EntityKind.CHARACTER, "MR. KITE"),
        (EntityKind.PROP, "KITE"),
    ]
