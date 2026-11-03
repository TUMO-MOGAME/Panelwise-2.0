# Prep

A long event is won by the team that's still shipping at the last milestone. Most teams in
multi-week online events never submit: they sign up everywhere and only work where they get
traction early. Set up so this team gets traction in the first days.

The kit calls this "the week before"; Panelwise started in week 1 of its own timeline (28 Sep), so
this is the setup checklist as of 2026-09-29, ticked only where STATUS.md shows it done. The event's
times are already in `event.toml [time]` with their source; `./hack kickoff` is not used here.

## Team and time

- [x] Roles decided: Katlego Thapelo Tlhapiso, project leader (Claude, Gemini); Tumo Olorato
      Mogame, co-builder (Claude). AGENTS.md §1 and `event.toml [team]`.
- [ ] Everyone's time zone and working hours written in STATUS.md, with the overlap marked. The
      timeline is in SAST; working hours are not recorded yet (open item, T038).
- [x] One place for decisions: this repo (STATUS.md, TASKS.md, AGENTS.md). Lanes are claimed in
      STATUS.md's taskboard.
- [ ] Both members registered on Devpost and in one team there (frameflow-nebius-hackathon/PLAN.md
      §7 step 5). Confirmed before T035.

## Stack and pipeline

- [x] Boilerplate scaffolded and CI running the gate: the Cultivation kit, then T002's pinned stack;
      `.github/workflows/ci.yml` runs `scripts/gate.sh` (11 checks across 2 projects).
- [x] A deploy pipeline producing a live URL: the hosted demo on Vercel (web, https://panelwise.vercel.app) + Render (API, https://panelwise-api.onrender.com, since 2026-10-16) + Supabase (docs/design/deploy.md), up until 15 Dec. Accounts and wiring T037 (steps in docs/deploy.md); the judge account seeded with the-red-kite's storyboard and comic on 2026-10-20 (T030).
- [x] `event.toml [checks]` points at real commands (`bash scripts/gate.sh`, which runs every check
      itself), and the gate passes. `[checks] smoke` is set by T009.
- [x] Keys in `.env` (never committed), names in `.env.example` (T001 settled every `NEBIUS_*` value).
- [x] Token Factory credit: the $25 event promo (`NEBIUS-DEVPOST-GLOBAL26`) and $25 from the AI
      Builder Program (STATUS.md § Environment).
- [x] ~~The cost of the ComfyUI GPU box checked against the credit, which covers Token Factory calls,
      not a GPU VM (T003).~~ No longer needed: no GPU access came through, so FLUX.2 [klein] on fal.ai
      draws the frames (T026, since 2026-10-11), its spend capped on the hosted demo; T003 was cut on 2026-10-19.

## Rules of the event

- [x] IP terms read on [/rules](https://nebiusglobalaihackathon.devpost.com/rules) (by the team;
      recorded 2026-10-27, Katlego). §7: a Submission stays the IP of those who built it; the
      Sponsor gets a non-exclusive licence to use it for judging, and the Sponsor and Devpost may
      promote it (and use the contributors' names, likeness and voice) for three years. It must be
      our original work, solely owned, infringing no one's rights; open-source dependencies are
      allowed under their licences. No project developed with the Sponsor's funding, contract or
      commercial licence (Builder Program credits are open to every entrant). A project that
      existed before 26 Aug explains what was significantly updated (CHANGES-FROM-FRAMEFLOW.md).
      The demo stays free and unrestricted for judging until 15 Dec, login credentials in the
      testing instructions; the video carries no third-party trademarks or copyrighted music.
      Prizes: one Overall award, or one Track award plus one Bonus award (Most Valuable Feedback
      is judged on the feedback section's completeness, viability and impact).
- [x] Submission requirements noted (Devpost "What to Submit"): a working project on NVIDIA
      Nemotron via Token Factory or AI Cloud; the track (Best Apps and Agents); a project
      description (draft: docs/submission/about.md); a working demo URL (T030); a public YouTube
      video of 3 minutes or less, with audio on how Token Factory and Nemotron were used (T034);
      a public repo with an open-source licence visible at the top (Apache 2.0, in `LICENSE`) and a
      README with setup instructions that highlights Nemotron and Token Factory use (T033, T035);
      feedback on Token Factory and NVIDIA tools (T033); and, for a project that existed before
      the submission period, what was significantly updated (CHANGES-FROM-FRAMEFLOW.md, T034).
      Deadline 30 Oct 2026 10:00 PDT (19:00 SAST); the team submits by 29 Oct.
- [ ] The milestone dates from `./hack schedule` added to everyone's calendar.
