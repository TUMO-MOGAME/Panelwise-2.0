"""What the describer and the judge are told. docs/design/verify.md §3.

The describer never sees the shot: told what to expect, it would agree. The judge sees the shot's
grounded spec and the description, never the image, and may only call and quote.
"""

from app.characters.labels import animals
from app.grounding import EntityKind, Extraction
from app.script import Scene, Screenplay
from app.shots import Shot
from app.verify.schema import FrameDescription

DESCRIBE_PROMPT = (
    "Describe this image exactly as it is. Report only what is visible; never guess a story or "
    "name anyone. List every person you can see, including anyone partly visible or in the "
    "background, with where they stand (the left, centre or right third of the image) and a "
    "short phrase for what they look like that starts with how old they look: a child, a "
    "teenager, an adult, an old man or an old woman. Say whether the scene is interior or "
    "exterior: exterior when the place is open to the sky (a rooftop, a balcony, a yard, a "
    "street), even if the sky is left blank; interior only when walls and a ceiling close it in; "
    "unclear when you can't tell. Give its light: day, night, dawn_or_dusk, or unclear. "
    "Give the shot size: wide (whole bodies "
    "and their surroundings), medium (people from the waist up), close (a head and shoulders) "
    "or extreme_close (part of a face, or one object filling the frame). List every notable "
    "object a viewer would notice, each with a category from the list and whether someone in "
    "the image holds it. Don't list what a person wears: put it in that person's appearance. "
    "Don't list the place itself or its structure: walls, floor, ceiling, sky, windows, doors, "
    "roofs, chimneys, stairs. Don't list marks of the drawing itself as objects: shading, "
    "hatching, outlines, sketch lines, shadows or the frame's border. Set has_text to true "
    "if any letters, words, numbers or "
    "writing-like marks appear anywhere: on signs, screens, paper, clothing or anything else. "
    "Under text, write out word for word each piece of writing you can read in the scene, as it "
    "is written: signs, labels, screens, paper, clothing, sound effects. Leave out scribbles, "
    "marks that aren't letters, and the artist's signature or initials even when you can read "
    "them: those go under signature, not text. "
    "Set signature to true if a signature, initials or an artist's mark appears anywhere, "
    "readable or not. When unsure, say unclear."
)

JUDGE_PROMPT = (
    "You check one storyboard frame against the screenplay. You are given the shot as the "
    "script writes it, and a description of the frame by someone who has not read the script. "
    "Call every described person and every described object exactly once, by its number.\n"
    "People: set `character` to the name from 'Characters in this shot' that the person is, or "
    "null if they are none of them. One character is at most one person. A person whose "
    "apparent age plainly contradicts a character's age in its quotes (a child drawn as an "
    "adult, an old man drawn young), or whose apparent sex or look plainly contradicts what its "
    "quotes say (a boy for a character they call 'she', short hair for one they give braids), "
    "is not that character: set `character` to null; a look the quotes don't mention is no "
    "contradiction. A character's 'sex (from the script)' line, when there is one, is the "
    "script's own word for their sex: a person drawn as the other sex is not that character. "
    "For a "
    "person who is "
    "no character, set `support` to a verbatim quote from the shot text or from a quote below "
    "that puts such a person there (for example 'a crowd gathers'), or null if nothing does.\n"
    "Objects: `scripted_prop` when the script puts it in this shot, with `support` a verbatim "
    "quote from the shot text or from a quote below that names it; `set_dressing` when it is an "
    "ordinary furnishing the location in the scene heading would hold, with `support` the "
    "heading's words for that location; `unscripted` otherwise. An ordinary thing the place "
    "would hold is `set_dressing`: a workshop's clock, boxes and tools; a roof's bucket, pipes "
    "and vents; the sky, clouds and puddles outdoors. Weather that happens (lightning, rain, "
    "snow, a storm) is an event: `scripted_prop` only with a verbatim quote that has it, else "
    "`unscripted`.\n"
    "An animal listed under 'Animals in this shot' is described among the objects: call it "
    "`scripted_prop`, with `support` a verbatim quote that names it. A person is never one of "
    "those animals.\n"
    "Quote exactly, never paraphrase. Anything you can't support with a quote is unscripted."
)


def _quoted(extraction: Extraction, kind: EntityKind, names: tuple[str, ...]) -> list[str]:
    lines: list[str] = []
    for name in names:
        entity = next((e for e in extraction.entities if e.kind is kind and e.name == name), None)
        quotes = "; ".join(f'"{q.text}"' for q in entity.quotes) if entity else ""
        lines.append(f"- {name}: {quotes}" if quotes else f"- {name}")
    return lines or ["- none"]


def _animals(extraction: Extraction, pets: tuple[str, ...], beings: dict[str, str]) -> list[str]:
    """Each animal as `- NAME (species): "quote"`, like the characters' lines."""
    lines = _quoted(extraction, EntityKind.CHARACTER, pets)
    if not pets:
        return lines
    return [
        line.replace(f"- {name}", f"- {name} ({beings[name]})", 1)
        for name, line in zip(pets, lines, strict=True)
    ]


def _sexed(
    lines: list[str], names: tuple[str, ...], screenplay: Screenplay, extraction: Extraction
) -> list[str]:
    """Each person's line, then their sex and its evidence when the script gives one (T082)."""
    # Imported here, as audit_frame does: app.storyboard's renderer modules import app.verify.
    from app.storyboard.prompt import character_sex

    out: list[str] = []
    for line, name in zip(lines, names, strict=True):
        out.append(line)
        if (found := character_sex(name, screenplay, extraction)) is not None:
            out.append(f'  sex (from the script): {found[0].value}, "{found[1]}"')
    return out


def render_spec(
    shot: Shot,
    scene: Scene,
    screenplay: Screenplay,
    extraction: Extraction,
    description: FrameDescription,
) -> str:
    # Animals are described as objects, so the judge sees them apart from the people (T052).
    beings = animals(extraction)
    people = tuple(c for c in shot.characters if c not in beings)
    pets = tuple(c for c in shot.characters if c in beings)
    lines = [
        f"Scene heading: {scene.heading}",
        f"Time of day: {shot.time_of_day or 'not stated'}",
        "",
        "Shot text:",
        shot.source,
        "",
        "Characters in this shot:",
        *(
            _sexed(
                _quoted(extraction, EntityKind.CHARACTER, people), people, screenplay, extraction
            )
            if people
            else _quoted(extraction, EntityKind.CHARACTER, people)
        ),
        "Animals in this shot:",
        *_animals(extraction, pets, beings),
        "Props in this shot:",
        *_quoted(extraction, EntityKind.PROP, shot.props),
        "",
        "The frame, as described:",
        "People:",
        *(
            [f"[{i}] {p.position}: {p.appearance}" for i, p in enumerate(description.people)]
            or ["none"]
        ),
        "Objects:",
        *(
            [
                f"[{i}] {o.name} ({o.category}, {'held' if o.held else 'not held'})"
                for i, o in enumerate(description.objects)
            ]
            or ["none"]
        ),
    ]
    return "\n".join(lines)
