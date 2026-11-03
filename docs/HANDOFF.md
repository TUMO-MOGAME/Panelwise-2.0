# `Panelwise` — Handoff

> Earlier handoffs (2026-10-03 Katlego → Tumo, 2026-10-11 Tumo → Katlego, 2026-10-17 Tumo →
> Katlego) are in git history: `git log -- docs/HANDOFF.md`.

**Closed 2026-10-20:** picked up by Tumo; §4.1–4.2 and §5 steps 1–3 done the same day (T030's
seed and hosted run, the bookkeeping, T036, gitleaks: STATUS log 2026-10-20). §1's "Not started"
list is as of writing.

**Written:** 2026-10-20 (SAST) · **By:** Tumo (via Claude), for Katlego · **Why:** Tumo hands the
work to Katlego, who takes it forward and hands back to Tumo for the rest. Every change below is
**merged on main (`7ef94d3`)**; no PR of Tumo's is open. **Branch of this note:**
`docs/handoff-1020`.

---

## 1. What is done (19–20 Oct)

| PR | What | State |
|---|---|---|
| #215 | Hotfix: every hosted storyboard since T107 answered 500 on `GET …/frames` (`DescriptionView` lacked `signature_text`); a guard test now checks every `FrameDescription` field is in the view | merged, **confirmed on the hosted demo** by Tumo (the-borrowed-bicycle's 18 frames load) |
| #212 | T109: the describer's limits in its decoding grammar | merged; **re-scored** (below) |
| #213/#214 | T122: a page's image links signed in one Storage request (21 frames 4.9 s → 0.22 s) | merged |
| #217 | The gate's jscpd ran out of Windows' 8,191-character command line; it now reads a temp copy of the files | merged |
| #218/#219 | T123: a 401 while still signed in. Pollers go to `/sign-in` on the **second** 401 in a row; actions repeat a 401 once after 1 s | merged. The browser outage check was skipped (Tumo's call); known limit in web.md §10 |
| #220 | Your answers on #212 recorded: T003, T025 cut; T110 closed | merged |
| #221 | `signature_text` capped at 5 × 60 (your ask) | merged |
| #222/#223 | T124: a pair the describer describes alike (word overlap ≥ 0.5; not two characters, not two scripted extras) also fails `DRAWN_TWICE` | merged |
| #224 | **`drawn_twice` back off the hosted ladder** (it was on for one night via #223) | merged |

**The T109 re-score** (2026-10-20, Super VL, main `933ba58`, ladder with `drawn_twice`;
`eval/measurements/t124/rescore-2026-10-20/`): the 6 frames that looped on 17 Oct all describe
now; market-day 5.2 still ends `ERROR` with its description and judgement present (not the
describer). Wrong 43 of 57 withheld, right 7 of 40. 6 of those 7 were `drawn_twice`, hence #224.

**Not started:** T113 (narration, stretch: designed in `docs/design/narration.md`, no code), T030's
hosted run and seed, the README/video/submit tail (T033–T035), the placeholder sweep (T036),
gitleaks.

## 2. Decisions already locked (don't reopen)

- **A copy warns, it doesn't withhold.** The hosted ladder is `drawn_sex,no_character,split_panels`
  (render.yaml). Putting `drawn_twice` back waits on a judge that matches the drawn cast.
- **The 401's cause is an unreachable Supabase Auth during the proxy's refresh, not refresh-token
  reuse** (measured, `eval/measurements/t123/`). Don't add a browser Supabase client.
- **T003 and T025 are cut; T110 is closed.** Your answers on #212.
- **T113 is stretch:** only after the submission path is safe; out of the submission unless done
  and tested by **27 Oct**.

## 3. Open PRs

None of Tumo's. Yours: #36 (README draft; its feedback section is the team's to write).

## 4. What needs you (Katlego)

1. **Render read-back:** `LLM_MONTHLY_TOKEN_CAP` (2,800,000), `IMAGE_MONTHLY_GENERATION_CAP` (800)
   and `AUDIT_WITHHOLD_CHECKS` (expect `drawn_sex,no_character,split_panels`, from render.yaml
   after #224). Issue #216 has the steps.
2. **T030's seed needs three hosted settings, not two:** `SUPABASE_URL`, `SUPABASE_SECRET_KEY`
   (creating the judge) **and `DATABASE_URL`** (the session pooler, port 5432) for `--from`, which
   copies a project (seed.py `main`). In Render's Shell they're already set. Never in chat or the repo.
3. **T113's inputs**, if you take it on: the ElevenLabs key, the monthly character cap, the voices,
   the model (narration.md §10).
4. **The models are as intended** (checked free 2026-10-19): Token Factory lists
   `nvidia/Nemotron-3_5-Lightning` (fast), `nvidia/nemotron-3-super-120b-a12b` (judge),
   `nvidia/Nemotron-3.5-Super-VL` (vision, thinking off); fal: `fal-ai/flux-2/klein/4b`. render.yaml
   sets no model variable, so Render runs the code's defaults unless the dashboard overrides one:
   worth a glance while you're in it.

## 5. Next steps, in order

1. **T030** (critical path; deploy.md §9): the caps read back; the judge seed in Render's Shell
   (`read -s JUDGE_PASSWORD; export JUDGE_PASSWORD; export JUDGE_EMAIL=…; cd /srv/api &&
   .venv/bin/python -m app.demo.seed`); one hosted run of the-red-kite, storyboard and comic (about
   22–44 drawings: announce the spend); `seed --from <its id>`; sign in as the judge and check;
   `event.toml`'s demo URL. Watching that run also closes #215's "frames appear as they're drawn".
2. **Task bookkeeping:** about 18 tasks are merged but unticked in TASKS.md (T082, T083, T089,
   T091, T093–T096, T099–T105, T109, T122–T124). Tick the ones whose Done is met; say which still
   wait on a measurement (T082, T083: a held-out script).
3. **T036** placeholder sweep; **gitleaks** over the commits since 2026-10-05.
4. **The judge sample** on the hosted stack (23 Oct).
5. **the-choir**, the last held-out script (don't open it before its run). It also measures T124's
   warning and the judge's misses.
6. **The audit's next lever: the judge misses a drawn cast** (look-alike characters, people in a
   crowd). It is why `drawn_twice` can't withhold. Free start: `eval/measurements/t124/rules2.py`
   shows "count a described-alike pair only when exactly one of the two is a known character"
   removes every right-frame flag on both stored samples (6 of 10 copies on Super VL), but the
   layout agent's own false calls (the-night-taxi 2.1) need their own look.
7. **T113** if the above is safe before 27 Oct.
8. The tail: README (T033, #36), video and ported-code table (T034), make public and submit
   (T035) on **29 Oct**. fal top-ups: **$10 before 1 Nov, $5 before 1 Dec**.

## 6. How to run it

- **Local stack** (Tumo's machine): the API built from `933ba58` (the same API code as main) with a
  compose override: Super VL, thinking off, klein, 3 attempts, the hosted ladder:

  ```yaml
  services:
    api:
      mem_limit: 512m
      environment:
        NEBIUS_MODEL_VISION: nvidia/Nemotron-3.5-Super-VL
        NEBIUS_VISION_THINKING: "false"
        FAL_CONCURRENCY: "2"
        RENDER_MAX_ATTEMPTS: "3"
        FAL_MODEL: fal-ai/flux-2/klein/4b
        LLM_MAX_ATTEMPTS: "5"
        AUDIT_WITHHOLD_CHECKS: "drawn_sex,no_character,split_panels"
  ```

  `docker compose -f docker-compose.yml -f <that file> up -d --build api`. Local DB at 0010.
- **Test database** `pw-t062-pg` on 127.0.0.1:55432. Gate: push with
  `TEST_DATABASE_URL=postgresql://postgres:pw@127.0.0.1:55432/panelwise_test PANELWISE_REQUIRE_DB=1`;
  11 checks on code, 10 on docs only. Never two gates at once.
- **Probes in the API container:** `docker cp` (forward-slash paths, `MSYS_NO_PATHCONV=1`), then
  `cd /srv/api && PYTHONPATH=/srv/api .venv/bin/python /tmp/x.py`. To run a branch's code there
  without rebuilding: `tar --force-local -cf app.tar app` in `services/api`, copy it to `/tmp`,
  untar, and run with `PYTHONPATH=/tmp/<dir>` (how T124's `recheck` ran).
- **`recheck`** (free, no model call): `python -m app.verify.recheck <project-id>` with
  `AUDIT_WITHHOLD_CHECKS` set to the ladder to measure.
- **`score_labels.py`** (paid, about $0.25): copy `eval/tools/score_labels.py`,
  `eval/frame-labels.json` **and `eval/labelled/`** to `/tmp/work/eval/…` in the container, then
  `score_labels.py /tmp/work --json /tmp/out.json`.

## 7. Verified facts

- The 401: with Auth unreachable, a poll with an expired access token answers 401 after 51 s and
  the cookie survives; the next request refreshes it. A refresh token's parent is accepted any
  time; a grandparent older than ~10 s is refused **and its 401 clears the cookie**.
- On 17 Oct's runs the described-alike rule caught 6 of 7 copies and flagged no right frame; on the
  harder 109 labelled frames `drawn_twice` (both detectors) withheld 6 of 40 right frames.
- Render's Blueprint applies `render.yaml`'s non-secret values from main (T104's ladder arrived
  that way).
- Docker Desktop stops when Tumo's machine sleeps: start it, then `docker start pw-t062-pg` and the
  compose stack.

## 8. Gotchas

- Never read the repo-root `.env` or `apps/web/.env.local`.
- On Windows `tar` needs `--force-local` for a `C:` path; `sed -i` in Git Bash turns CRLF files to
  LF (repo files are CRLF).
- A pytest worker can hang when the machine is busy; killing the gate's processes needs the
  machine owner's OK.
- Changing a PR's base doesn't start the gate workflow; push to start it.
- The local Postgres password isn't the compose file's: run DB tools inside the API container.

## 9. Corrections

- **T124's ladder entry (#223) was wrong:** it withheld right frames; #224 reverted it the next day.
- **19 Oct's suspicion that a slow refresh reuses a refresh token** (STATUS log) was wrong; the
  cause is above.
- **The seed needs `DATABASE_URL` for `--from`**, not only the two Supabase keys.
