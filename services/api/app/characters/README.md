# `characters`

Characters in frame prompts: names taken out, labels for animals and props, and the sex words and titles the prompt and audit read.
Design: [docs/design/characters.md](../../../../docs/design/characters.md).

- `redact.py` (T008): `redact_names` and `redact_all` take character names out of text before it enters any image prompt (rules 1 and 2).
- `labels.py` (T052): `redaction_labels`, `animals`: each name token's label (`a person`, `the <species>`, `the <prop>`, `it`).
- `sex.py` (T079, T082): `Sex`, `SEX_WORDS`, `CONFLICT_WORDS`, `SEX_TITLES`.
- Reference portraits (T025) were cut 2026-10-19 and never built; a character's look comes from the script's words (T079's `LOOK`).
