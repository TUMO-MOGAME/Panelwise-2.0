"""A self-written screenplay, in layout text and as a real PDF. Never a copyrighted script.

Column positions follow the standard screenplay format, as pdfplumber's layout text reports
them: action and headings at the margin, dialogue further in, parentheticals further still,
the cue furthest in, transitions at the right.
"""

from collections.abc import Sequence

from fpdf import FPDF

# Characters of indent in layout text.
NUM, ACTION, DIALOGUE, PAREN, CUE, TRANSITION = 4, 10, 20, 26, 32, 55

type Row = tuple[int, str] | None  # (indent, text); None is a blank line


def layout(rows: Sequence[Row]) -> str:
    return "\n".join("" if r is None else " " * r[0] + r[1] for r in rows)


def heading(number: str, text: str) -> tuple[int, str]:
    # The number sits left of the margin, and is repeated at the far right of the same row.
    left = f"{number:<{ACTION - NUM}}"
    return (NUM, f"{left}{text}".ljust(66 - NUM) + number)


PAGE_1: list[Row] = [
    (CUE - 4, "THE KEEPER'S LIGHT"),
    None,
    (ACTION, "FADE IN:"),
    None,
    heading("1", "INT. LIGHTHOUSE KITCHEN - NIGHT"),
    None,
    (ACTION, "Rain hammers the window. NANDI (60s, oilskin coat)"),
    (ACTION, "pours tea into two chipped mugs."),
    None,
    (ACTION, "DOORS SLAM."),
    None,
    (CUE, "NANDI"),
    (PAREN, "(without turning)"),
    (DIALOGUE, "You came back."),
    None,
    (CUE, "THABO (O.S.)"),
    (DIALOGUE, "The boat didn't. I walked the last"),
    (DIALOGUE, "mile along the cliff."),
    None,
    (TRANSITION, "CUT TO:"),
    None,
    heading("2", "EXT. LIGHTHOUSE GALLERY -- CONTINUOUS"),
    None,
    (ACTION, "THABO steps out into the wind, holding a torn map."),
    None,
    (CUE, "THABO"),
    (DIALOGUE, "It's gone."),
    (PAREN, "(beat)"),
    (DIALOGUE, "All of it."),
    (CUE, "(MORE)"),
]

PAGE_2: list[Row] = [
    (66, "2."),
    (CUE, "THABO (CONT'D)"),
    (DIALOGUE, "The whole coast."),
    None,
    heading("3", "INT. LIGHTHOUSE STAIRWELL"),
    None,
    (ACTION, "Silence."),
]


def two_page_text() -> tuple[str, list[int]]:
    """The screenplay as layout text, plus the 1-based line where page 2 begins."""
    return layout(PAGE_1 + PAGE_2), [len(PAGE_1) + 1]


def pdf_bytes(pages: Sequence[Sequence[Row]]) -> bytes:
    """Render rows onto US-letter pages in 12 pt Courier: 10 characters per inch, so an
    indent of n characters sits n/10 inch right of a 1-inch left edge."""
    pdf = FPDF(unit="pt", format="letter")
    pdf.set_font("Courier", size=12)
    pdf.set_auto_page_break(False)
    for rows in pages:
        pdf.add_page()
        y = 72.0
        for row in rows:
            if row is not None:
                indent, text = row
                pdf.text(72 + indent * 7.2, y, text)
            y += 12
    return bytes(pdf.output())
