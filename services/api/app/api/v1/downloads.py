"""A downloaded PDF is named by its screenplay (web.md §4.5, T126).

A browser ignores `download` on a link to another origin, so a PDF used to save under its Storage
key. Supabase Storage names a signed download itself when the link carries `download=<name>`.
"""

import re
import unicodedata
from typing import Literal
from urllib.parse import quote

_UNSAFE = set('\\/:*?"<>|')  # refused in a file name by Windows, macOS or Linux
_MAX_TITLE = 80


def download_name(title: str, kind: Literal["storyboard", "comic"]) -> str:
    """`"{title} storyboard.pdf"` or `"{title} comic.pdf"`, the title made safe for a file name:
    unsafe and control characters become `-`, white space one space, at most 80 characters, and
    an empty title `Panelwise`."""
    safe = "".join("-" if c in _UNSAFE or unicodedata.category(c) == "Cc" else c for c in title)
    safe = re.sub(r"\s+", " ", safe).strip()[:_MAX_TITLE].rstrip()
    return f"{safe or 'Panelwise'} {kind}.pdf"


def with_download(url: str, filename: str) -> str:
    """The signed link, asking Storage to send it as an attachment named `filename`."""
    return f"{url}{'&' if '?' in url else '?'}download={quote(filename)}"
