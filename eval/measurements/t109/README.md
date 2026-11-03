# T109: why the describer's answer fails its schema on Super VL (2026-10-17)

Tumo (via Claude), on Tumo's machine, in the API container on `feat/bubbles-t098` @ `eed335d`
(the describer is the same as main's), Super VL with thinking off. Token Factory only, about $0.3;
nothing drawn, nothing written. The design and the numbers: [docs/design/verify.md](../../../docs/design/verify.md)
§ T109 contracts, §8 and §9 T109.

| File | What |
|---|---|
| `looping-frames.txt` | every Super VL `ERROR` with a stored drawing: 7 labelled frames (findings § U8) and rooftop-tomatoes' comic 6.1, as `label asset` |
| `control-frames.txt` | 10 frames that answer fine: today's two held-out storyboards, the most objects first |
| `probe_t109.py` → `1-the-call-as-it-is.out` | the describer's exact first call, 3 times a frame: `finish_reason`, tokens, the validation error |
| `probe_t109b.py` → `2-candidates.out` | one change each (`caps`, `penalty`, `prompt`, `warm`), once a frame, on both lists. `caps` here is the first limits (people 15, objects 20, text 10 × 120 chars, appearance 200, name 40), in the schema the prompt shows **and** the grammar |
| `3-unchanged-call-again.out` | the call with no change (`base`), once more on both lists: the controls' noise floor (9 of 10 the stored answer) and a 4th run of the looping frames |
| `4-grammar-caps-first-values.out` | `capsfmt`: the first limits in the grammar only, the prompt's schema unchanged |
| `5-grammar-caps-final.out` | `capsfmt` with the final limits (people 24, objects 40, text 40 × 100 chars, appearance 200, name 60): 7 of 7 valid, 10 of 10 controls the stored answer. `probe_t109b.py` holds these values now |
| `t109_controls_cmp.py` | compares each candidate's control answers with the stored description (the stored rows exported one a line: the asset, a pipe, the description's JSON) |

The raw answers (the loops: "picture frame" 40 times, "B. B. B. …") were kept on Tumo's machine
only; each `.out` line has the finish reason, tokens and the description's shape.

The limits were checked against every stored description in Tumo's local database: DeepSeek's
1,352 reach 21 people, 32 objects, 15 pieces of text, 77 characters of text, 175 of appearance and
49 of an object name; Super VL's 79 reach 4 people, 16 objects and 33 pieces of text (a calendar's
31 dates on gogos-recipe comic 1.1, an honest answer).
