# T110: absent characters let through on Super VL (2026-10-17)

Tumo (via Claude), on Tumo's machine. **Result: no code change.** Closed as measured on 2026-10-19
(Katlego agreed on #212; Tumo decided): the levers are the extraction (L017) and drawn-twice frames, not
the presence agent.

**The question** (findings § U8, on #194): on the 109 labelled frames, `no_character` withheld 4 of
the 8 `absent` frames on DeepSeek but 1 on Super VL. The 6 that only DeepSeek withheld were
final-whistle 2.3 and 4.3, lost-property 7.4 and 9.6, the-bread-van 4.4, and the-lighthouse-inspector 7.5.

**How:** `probe_t110.py` ran `audit_frame` 3 times on each of the 6, in the API container on
`feat/bubbles-t098` @ `eed335d` (main + T102, T104, T097, T098), Super VL with thinking off, ladder
`drawn_sex,no_character,split_panels`. Each run prints the described people, the judge's calls,
the sex answers (`seen`), the presence answers (`found`) and the failed checks. About $0.05 of
Token Factory; nothing written, nothing drawn. Results: `absent-frames-super-vl.out`, one JSON line
per run.

| Frame | Label | Super VL, 3 runs | Why it's shown |
|---|---|---|---|
| the-lighthouse-inspector 7.5 | Mr. Fortuin drawn as an old woman | the judge matches the old woman as FORTUIN, 3 of 3 | the stored extraction predates T101: its bare `FORTUIN` has no sex. A new run folds it into MR. FORTUIN ("male"), so the sex agent asks and `drawn_sex` fails it (T101, T102's measurement) |
| lost-property 7.4 | one man, no Tebogo or officer | the judge matches the man as TEBOGO and a background figure as OFFICER MOLOI, 3 of 3 | the extraction gives TEBOGO no sex and no age, so nothing in the script rules the man out |
| final-whistle 4.3 | Lindi drawn, not Palesa | matched or found as PALESA in 3 of 3 (once the judge said "Lindi") | both are teenage girls; Palesa's armband and bandaged wrist aren't drawn, and "a detail the drawing leaves out doesn't rule anyone out" (T099, by design) |
| final-whistle 2.3 | no crowd | CROWD found or matched on one person, 3 of 3 | CROWD is extracted as a character (L017) |
| the-bread-van 4.4 | three boys for Theo | THEO found or matched, 3 of 3 | one person drawn several times: the drawn-twice problem, not presence |
| lost-property 9.6 | a split frame | **withheld**, 3 of 3 (`split_panels`) | T104 catches it now |

**Reading:** the presence agent finds people, as designed. What lets these frames through is the
stored extraction (no sex or age for TEBOGO, a sexless FORTUIN before T101, CROWD as a person) and
one person drawn several times. DeepSeek withholding more was partly noise: the same lighthouse 7.5
attempt flips between withheld and shown across runs on one model (findings § U8).

**So:** no change to the presence agent. The levers are the extraction (L017: a crowd or team as a
character) and drawn-twice frames (T104's `drawn_twice` caught 2 of 5 copies on gogos-recipe and
only warns).
