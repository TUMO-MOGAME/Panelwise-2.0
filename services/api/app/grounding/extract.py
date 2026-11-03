"""Entity extraction on Nemotron, chunked by scene, then grounded. docs/design/grounding.md §4.

Chunked because one call over a whole feature returns a fraction of the cast (FrameFlow: 15
entities from a script with 77 speaking characters). Chunks never split a scene: a cue cut off
from its scene loses what identifies it. Chunks run concurrently -- TPM, not RPM, is the limit
on the fast tier (findings U4).
"""

import asyncio
from collections.abc import Sequence

from pydantic import ValidationError

from app.grounding.filter import ground
from app.grounding.model import Extraction, ExtractionError
from app.grounding.schema import ChunkEntities
from app.llm import LLMError, NebiusChatModel, StructuredResult, Tier, Usage, structured_chat
from app.script import Dialogue, Scene, Screenplay

# Positive framing: say what to extract. Grounding is then enforced in code, not trusted.
SYSTEM_PROMPT = (
    "You read part of a screenplay. List every character and every prop that this text names or "
    "describes, including characters who never speak. A prop is an object someone handles or "
    "that the action singles out. Leave out locations. "
    "For each one, give its name exactly as the screenplay writes it, and one to three quotes "
    "that show who or what it is. Copy each quote character for character from a single action "
    "paragraph or a single line of dialogue, with the original spelling, punctuation and "
    "capitalisation: quotes are matched against the screenplay, and one that is not word for "
    "word in the text is discarded. Quote dialogue without the speaker's name above it and "
    "without its parenthetical: only the words spoken. Never join a scene heading, a second "
    "paragraph or another speech onto a quote. "
    "If a character is an animal, give in species the word the screenplay uses for what it is, "
    "copied from one of its quotes; otherwise species is null. Whenever the screenplay gives a "
    "character or a prop a name of its own besides the one you list it under -- a nickname, or "
    "a name someone gives a pet, a toy or a vehicle, even if only in dialogue -- put that name "
    "in the entity's other_names, copied exactly; otherwise leave other_names empty. "
    "For a character who is a person, give in sex_word one word the screenplay writes about this "
    "character that shows whether they are female or male -- she, he, her, his, or a noun such as "
    "woman, girl, man, boy or fisherman -- copied exactly, best from one of its quotes from an "
    "action paragraph that names this character and no one else; null only when the screenplay "
    "never shows it. Never guess: copy only a word the screenplay writes about them."
)


def render_chunk(scenes: Sequence[Scene]) -> str:
    """The scenes as the model reads them: heading, then each element in order, verbatim."""
    blocks: list[str] = []
    for scene in scenes:
        parts = [scene.heading]
        for element in scene.elements:
            if isinstance(element, Dialogue):
                cue = f"{element.cue} ({element.extension})" if element.extension else element.cue
                paren = [f"({element.parenthetical})"] if element.parenthetical else []
                parts.append("\n".join([cue, *paren, element.text]))
            else:
                parts.append(element.text)
        blocks.append("\n\n".join(parts))
    return "\n\n".join(blocks)


def chunk_scenes(screenplay: Screenplay, chunk_chars: int) -> list[tuple[Scene, ...]]:
    """Whole scenes, in order, up to `chunk_chars` per chunk. A scene longer than the budget is
    a chunk on its own; it is never cut."""
    chunks: list[tuple[Scene, ...]] = []
    current: list[Scene] = []
    size = 0
    for scene in screenplay.scenes:
        length = len(render_chunk([scene]))
        if current and size + length > chunk_chars:
            chunks.append(tuple(current))
            current, size = [], 0
        current.append(scene)
        size += length
    if current:
        chunks.append(tuple(current))
    return chunks


async def extract(
    model: NebiusChatModel,
    screenplay: Screenplay,
    *,
    chunk_chars: int = 12_000,
    max_chunks: int = 40,
    concurrency: int = 4,
    temperature: float = 0.0,
) -> Extraction:
    chunks = chunk_scenes(screenplay, chunk_chars)
    if len(chunks) > max_chunks:
        raise ExtractionError(
            f"The script splits into {len(chunks)} chunks, above the {max_chunks} ceiling. "
            "Each chunk is a billed call; raise max_chunks deliberately."
        )

    gate = asyncio.Semaphore(concurrency)

    async def one(chunk: tuple[Scene, ...]) -> StructuredResult[ChunkEntities]:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": render_chunk(chunk)},
        ]
        async with gate:
            try:
                return await structured_chat(
                    model,
                    messages,
                    ChunkEntities,
                    Tier.FAST,
                    temperature=temperature,
                    max_tokens=8192,
                )
            except (LLMError, ValidationError) as exc:
                # An LLMError names status and model only; a ValidationError would quote the
                # model's output, which quotes the script -- so its type alone.
                detail = str(exc) if isinstance(exc, LLMError) else type(exc).__name__
                raise ExtractionError(
                    f"The chunk with scenes {chunk[0].number}-{chunk[-1].number} failed: {detail}",
                    scene=chunk[0].number,
                ) from exc

    # A TaskGroup cancels the remaining chunks on the first failure: no spending on a result
    # that will be thrown away, and no partial cast.
    try:
        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(one(chunk)) for chunk in chunks]
    except* ExtractionError as failures:
        raise failures.exceptions[0] from None

    results = [task.result() for task in tasks]
    entities, report = ground([e for r in results for e in r.value.entities], screenplay)
    return Extraction(
        entities=entities,
        report=report,
        models=tuple(dict.fromkeys(r.chat.model for r in results)),
        usage=Usage(
            prompt_tokens=sum(r.chat.usage.prompt_tokens for r in results),
            completion_tokens=sum(r.chat.usage.completion_tokens for r in results),
            reasoning_tokens=sum(r.chat.usage.reasoning_tokens for r in results),
        ),
    )
