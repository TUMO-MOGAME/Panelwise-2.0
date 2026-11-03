# `styles`

Public storyboard and comic styles: **how** a frame is drawn, never **what** is in it
([docs/design/storyboard.md](../docs/design/storyboard.md) §3.2). The hosted demo uses only the
styles in this folder, and draws every frame in the default, `clean`: there is no style picker.

| Key | Label | Medium | Emphasis |
| --- | --- | --- | --- |
| [`clean`](clean.toml) (default) | Clean sketch | storyboard sketch, pencil drawing | none |
| [`ink`](ink.toml) | Storyboard ink | storyboard sketch, pencil drawing | 1.3 |
| [`pencil`](pencil.toml) | Pencil study | pencil sketch, graphite drawing | 1.3 |

All three are FrameFlow's drawn styles (its same-seed A/B of 2026-09-13: none won on every shot,
so the choice belongs to whoever reads the board). They were made public on 2026-09-30 (decided by
the user); FrameFlow's `classic` is dropped (storyboard.md §8), and the private pack is empty.

## The file format

One TOML file per style; the file stem is the key (`[a-z0-9-]+`).

```toml
label = "Clean sketch"                            # required: printed in the PDF's footer
description = "Pencil storyboard. ..."            # required
medium = "storyboard sketch, pencil drawing"      # required: leads every frame prompt
finish = "grayscale, monochrome, loose linework"  # required: straight after the medium
grayscale = true                                  # required: the pixel pass after rendering
emphasis = 1.3                                    # optional: a weight on `medium`; not applied on fal.ai
negative = ""                                     # optional: a negative prompt; not sent to fal.ai
default = true                                    # optional: exactly one public style sets it
```

`load_styles` (`services/api/app/storyboard/styles.py`) rejects, naming the file: a missing,
unknown or mistyped field; `(`, `)` or `:` in `medium`, `finish` or `negative` (weights are the
renderer's); a subject word (`person`, `figure`, `face`, `text`, `logo`, …: `SUBJECT_WORDS`) as a
whole word in `medium` or `finish`; not exactly one default. No negations: CLIP can't read "no"
("no borders" drew borders), so what must not appear is kept out by not being said.

## Private styles

A private pack is a directory of the same files outside this repo, named by
`PANELWISE_PRIVATE_STYLES`. Its styles get the same checks, can't reuse a public key and can't be
the default. The hosted API never sets it.
