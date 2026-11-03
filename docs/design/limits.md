# Design — `limits` (the hosted demo's caps and its judge account)

**Status:** built and live (T069; T030's image cap) · **Owner:** Tumo (Claude) · **Tasks:** T069 (split from T030 on 2026-10-10:
T030 keeps the hosting itself and the image-spend cap, §4) ·
**Spec:** [SPEC.md](../../SPEC.md) US1, US3

---

## 1. What this covers

What keeps the hosted demo standing from submission to the end of judging (15 Dec 2026) on a
project with little money: Token Factory's $25 credit pays every model call, fal top-ups pay the
drawings, and every upload, "Try another render" and "Make the comic" spends both.

- **A monthly token budget** for every Token Factory call the API makes, counted per calendar month
  (UTC); at the budget, new work that would call a model is refused with a clear message.
- **Uploads per account per day**: 3 on the hosted demo.
- **Pages per script**: 15 on the hosted demo.
- **The judge account**: one shared login, made by an idempotent seed script, holding a ready-made
  copy of the sample project so a judge sees a finished storyboard and comic without spending
  anything.

Decided by Tumo on 2026-10-10: one shared judge account, 3 uploads a day, 15 pages, a monthly token
cap. All four are settings; unset, each is off, so local development is unchanged.

**Not covered:** the hosting itself (T037, T063; deploy.md); sign-up (off, web.md §10). **Covered
since T030** (2026-10-15): the image renderer's spend, as a monthly count of drawings (§4).

## 2. Reference material

| Kind | Where |
|---|---|
| The model client | `services/api/app/llm/client.py` `NebiusChatModel.chat` → `ChatResult.usage` (prompt, completion, reasoning tokens) |
| The routes that spend | web.md §6: `POST /projects` (the upload's job: extract, plan, render, audit), `POST …/frames/{s}/{n}/attempts` (T021: render + audit), `POST …/comic` (T064: render + audit per panel) |
| Supabase Auth admin | `POST /auth/v1/admin/users` (create, `email_confirm`), `GET /auth/v1/admin/users` (list, paged), `PUT /auth/v1/admin/users/{id}` (password); the secret key in the `apikey` header |
| Prior art in the repo | T062's `app/frames/check.py` copies a planned project for a throwaway run; this copies a finished one |
| Ported | nothing |

## 3. Domain model

```mermaid
classDiagram
    class Limits {
        +llm_monthly_token_cap: int | None
        +uploads_per_day: int | None
        +upload_max_pages: int | None
    }
    class LlmUsageRow {
        <<table llm_usage>>
        +month: date  (PK, the 1st, UTC)
        +tokens: bigint
        +calls: int
        +updated_at: timestamptz
    }
    class record_usage {
        <<function, app/limits/usage.py>>
        +record_usage(sessions, result: ChatResult) None
    }
    class NebiusChatModel {
        +on_usage: Callable[[ChatResult], Awaitable[None]] | None
    }
    NebiusChatModel --> record_usage : on_usage after each answer
    record_usage --> LlmUsageRow : upsert tokens += prompt + completion
```

`tokens` counts `prompt_tokens + completion_tokens` (Token Factory bills both; reasoning tokens are
part of completion). One row per month; nothing per user: the budget protects the credit, and the
upload cap is what spreads it across judges.

## 4. Flow

```mermaid
sequenceDiagram
    participant B as Browser (web)
    participant A as API route
    participant L as limits.py
    participant D as Postgres
    participant M as NebiusChatModel
    B->>A: POST /projects (or …/attempts, …/comic)
    A->>A: who (401/503), ownership (404), state (409), as today
    A->>L: budget_spent(request, session)
    L->>D: SELECT tokens FROM llm_usage WHERE month = this month
    alt at or over LLM_MONTHLY_TOKEN_CAP
        A-->>B: 429 {"error": "llm_budget_spent"} (nothing written)
    end
    A->>L: images_spent(request, session) (T030)
    L->>D: SELECT count(*) FROM frame_audits WHERE created_at >= the 1st of this month (UTC)
    alt at or over IMAGE_MONTHLY_GENERATION_CAP
        A-->>B: 429 {"error": "image_budget_spent"} (nothing written)
    end
    A->>L: uploads_today(session, owner) (upload only)
    alt at UPLOADS_PER_DAY
        A-->>B: 429 {"error": "upload_limit", "per_day": 3}
    end
    A->>A: read the PDF; count its pages (upload only, before storing)
    alt over UPLOAD_MAX_PAGES
        A-->>B: 413 {"error": "too_many_pages", "max_pages": 15}
    end
    A-->>B: 202 as today; the job runs
    M->>L: on_usage(result) after every answer
    L->>D: INSERT … ON CONFLICT (month) DO UPDATE SET tokens = tokens + n
```

- **Where each check sits.** `POST /projects`: after who and storage (the 503s), the budget, then the
  day's count, then the existing length, form, size and header checks, then the **page count**
  (`pdfplumber` opens the bytes in a thread; a PDF it can't open falls through to the job's own
  `not_a_pdf`), and only then storage. `…/attempts` and `…/comic`: the budget after their 404 and
  409 checks and before their 503s, so nothing is written for a refused request.
- **A job already running finishes** over the budget: stopping mid-storyboard would waste what it
  already spent and leave a half board. The budget is a ceiling on starting work, so the month can
  end slightly over it; the cap is set below the credit with room for one job.
- **Uploads today** = the owner's `projects` rows with `created_at` in the last 24 hours (rolling, so
  no time zone decides when "tomorrow" starts). Copies made by the seed keep their source's
  `created_at`, so the sample never counts.
- **Metering never fails a call**: `on_usage` errors are logged at `WARNING` and swallowed (a lost
  count under-counts a little; a failed model call would lose the work). It runs after the answer
  is parsed, so a failed call (an HTTP error, a timeout) counts nothing; an answer that came back
  **empty** is counted before it raises, since Token Factory bills it (a reasoning call can spend
  its whole `max_tokens` thinking; review of T069).

**The image budget (T030; Tumo, 2026-10-15).** The renderer is fal.ai's FLUX.2 [klein] (storyboard.md
§3.5), billed per image, about $0.003–0.004 each. The budget counts **drawings**: the rows of
`frame_audits` created this UTC month, storyboard and comic alike, because every drawing the API
pays for is audited and every audit is logged (verify.md §4), an `ERROR` audit included. No new table
and no counter to keep in step: the log is the count. It is checked where the token budget is, with
the same rule (refuse new work at the start; a job already running finishes): `POST /projects`,
`…/attempts` and `…/comic`, each right after the token budget, answering 429
`{"error": "image_budget_spent"}`. **What it misses, knowingly:** a draw fal blacked out for safety
and drew again (`REDRAWS`, up to 3 requests for one drawing, storyboard.md §3.5) is one row; a
process that dies between the drawing and its log (a restart mid-job) leaves no row; and a
request fal failed costs nothing; so the count is a floor, and the cap is set with room for that and
for one job finishing over it. **Measured** (2026-10-15, the stored runs of 11 scripts on the local
stack): a storyboard under the ladder of the time (`drawn_sex,no_character`; hosted now adds
`split_panels`) is **17–26 drawings** (the
held-out runs of 13–14 Oct), about $0.07–0.10; under the old strict audit up to 134 (lost-property, 49
shots). Its audit is 130,000–175,000 tokens (up to 390,000 under the old audit; T104's layout
question adds about 15,000–24,000 to it and as much to its comic, verify.md §3; T102 lets every sex
question, T095's too, use up to 4,096 tokens, so measure tokens a job again once the agent set
settles); this month's
`llm_usage` on the local stack, all our testing, is 4.4 million tokens in 1,455 calls.

**The judge seed** (`python -m app.demo.seed --from <project id>`, run once against the hosted
database; `JUDGE_EMAIL` and `JUDGE_PASSWORD` from the environment, never the command line):
1. Supabase Auth: create the user (`email_confirm: true`); if the email exists, find its id and set
   the password. Idempotent.
2. If `--from` is given and the judge owns no project with the source's `pdf_path`: copy the source
   project into the judge's account in one transaction: the `projects` row (new id, the judge as
   owner, the source's title, `pdf_path`, `created_at` and stage columns), a `done` storyboard job,
   every `frames` row and its storyboard `frame_audits` rows (the assets are content addresses,
   shared, never copied), and the comic (its job and `comics` row) if the source has one. The
   source must be the owner's settled storyboard (`done`, no frame `rendering` or `auditing`), else
   the script refuses before writing.
3. Print the judge's id, the copied project's id and its title. Never the password.

## 5. State

No new lifecycle: a refused request writes nothing, and the job and frame state machines are
unchanged.

## 6. Contracts

```python
# app/core/config.py (Settings)
llm_monthly_token_cap: int | None = None   # LLM_MONTHLY_TOKEN_CAP; None or 0: no budget
uploads_per_day: int | None = None         # UPLOADS_PER_DAY; None or 0: no cap
upload_max_pages: int | None = None        # UPLOAD_MAX_PAGES; None or 0: no cap
image_monthly_generation_cap: int | None = None   # IMAGE_MONTHLY_GENERATION_CAP (T030); None or 0: no cap; blank is None

# app/limits/usage.py (T069)
class LlmUsageRow(Base): ...               # table llm_usage: month date PK, tokens bigint, calls int, updated_at
def this_month(now: datetime) -> date: ...                 # the 1st of now's month, UTC
async def record_usage(sessions: async_sessionmaker[AsyncSession], result: ChatResult) -> None: ...
#   upsert this month's row: tokens += prompt + completion, calls += 1; logs and swallows any error
async def tokens_this_month(session: AsyncSession) -> int: ...
async def uploads_today(session: AsyncSession, owner: uuid.UUID) -> int: ...   # created_at > now() - 24 h
async def drawings_this_month(session: AsyncSession) -> int: ...   # T030: frame_audits rows, any target, created_at >= this_month(now)

# app/limits/checks.py (T069): each raises ApiError, writes nothing
async def budget_spent(request: Request, session: AsyncSession) -> bool: ...    # tokens this month >= the cap
async def check_budget(request: Request, session: AsyncSession) -> None: ...    # 429 llm_budget_spent
async def check_uploads(request: Request, session: AsyncSession, owner: uuid.UUID) -> None: ...   # 429 upload_limit
def check_pages(request: Request, pdf: bytes) -> None: ...                      # 413 too_many_pages (a thread call)
async def images_spent(request: Request, session: AsyncSession) -> bool: ...   # T030: drawings this month >= the cap
async def check_images(request: Request, session: AsyncSession) -> None: ...   # T030: 429 image_budget_spent; called right after check_budget

# app/comic/job.py: the comic's refusals stay in start_comic, in comic.md §4a's order
start_comic(..., budget_spent: bool = False)   # → ComicRefused("llm_budget_spent") after comic_running, before the 503s
start_comic(..., images_spent: bool = False)   # T030: → ComicRefused("image_budget_spent") right after llm_budget_spent
RefusalCode: ... | Literal["image_budget_spent"]   # app/comic/job.py, T030
_COMIC_STATUS["image_budget_spent"] = 429        # app/api/v1/projects.py, T030: without it the route answers 500
# app/demo/seed.py, T030: each copied frame_audits row keeps its source's created_at, as the project
#   row already does: a copy made this month must not count as this month's drawings

# app/llm/client.py
NebiusChatModel(..., on_usage: Callable[[ChatResult], Awaitable[None]] | None = None)
#   awaited after each successful answer; create_app passes record_usage bound to its sessions

# app/api/errors.py
ApiError(status, code, *, headers=None, extra: Mapping[str, object] | None = None)   # extra fields join {"error": code}

# app/demo/seed.py (T069): python -m app.demo.seed [--from PROJECT_ID]
async def main(argv: list[str]) -> int: ...
```

**Migration** `0006_llm_usage`: the `llm_usage` table; downgrade drops it.

**Responses** (web.md §6 gains these rows):

| Route | New answers |
|---|---|
| `POST /projects` | 429 `{"error": "llm_budget_spent"}` · 429 `{"error": "image_budget_spent"}` (T030) · 429 `{"error": "upload_limit", "per_day": n}` · 413 `{"error": "too_many_pages", "max_pages": n}` |
| `POST …/attempts`, `POST …/comic` | 429 `{"error": "llm_budget_spent"}` · 429 `{"error": "image_budget_spent"}` (T030), in that order |

**Copy** (web.md §6 Copy):

| Where | Text |
|---|---|
| Upload, `llm_budget_spent` | "The demo has used this month's model budget. Your existing storyboards still open; new uploads start again next month." |
| Upload, `upload_limit` | "This demo makes {per_day} storyboards a day per account. Try again tomorrow." |
| Upload, `too_many_pages` | "This demo takes scripts of up to {max_pages} pages." |
| Try another render / Make the comic, `llm_budget_spent` | "The demo has used this month's model budget." |
| Upload, `image_budget_spent` (T030) | "The demo has drawn this month's budget of frames. Your existing storyboards still open; new uploads start again next month." |
| Try another render / Make the comic, `image_budget_spent` (T030) | "The demo has drawn this month's budget of frames." |

**Environment** (`.env.example`, deploy.md §6): `LLM_MONTHLY_TOKEN_CAP` (already listed, read by
no code until now), `UPLOADS_PER_DAY`, `UPLOAD_MAX_PAGES`, each off when unset **or blank** (the
example file lists them empty); `JUDGE_EMAIL`, `JUDGE_PASSWORD` for the
seed only (local `.env`, never the hosted API's environment). **T030:** `IMAGE_MONTHLY_GENERATION_CAP`,
now read (`.env.example`'s "read by no code yet" goes), off when unset or blank like the others.

## 7. Structure

| Path | New? | Responsibility | Task |
|---|---|---|---|
| `services/api/app/limits/{__init__,usage,checks}.py` | new | §6 | T069 |
| `services/api/migrations/versions/0006_llm_usage.py` | new | the table | T069 |
| `services/api/app/llm/client.py`, `app/main.py` | changed | `on_usage`; the meter wired in the lifespan | T069 |
| `services/api/app/api/errors.py` | changed | `extra` | T069 |
| `services/api/app/api/v1/projects.py` | changed | the checks in the three routes | T069 |
| `services/api/app/demo/{__init__,seed}.py` | new | the judge seed | T069 |
| `apps/web/components/projects/upload.ts`, the retry and comic copy | changed | §6 Copy | T069 |
| `services/api/app/core/config.py`, `.env.example`, `docs/design/deploy.md` §6 | changed | the settings | T069 |
| `services/api/app/limits/{usage,checks}.py`, `app/api/v1/projects.py`, `app/comic/job.py`, `app/core/config.py` | changed | the image budget: `drawings_this_month`, `images_spent`, `check_images`, `start_comic(images_spent=)`, the setting | T030 |
| `apps/web/components/projects/upload.ts`, the retry and comic copy | changed | `image_budget_spent`'s copy | T030 |
| `render.yaml`, `.env.example`, `docs/design/deploy.md` §6 | changed | the hosted values and the two money caps (deploy.md) | T030 |

## 8. Decisions & alternatives

| Decision | Chosen | Rejected, and why |
|---|---|---|
| What the budget counts | tokens the API's calls report, per month, in Postgres | Token Factory's own billing: no API to read it; a per-process counter: lost on restart, and the host restarts the API on every deploy |
| Where it bites | refusing new work at the start | stopping running jobs: wastes what they spent and leaves half a board |
| Per user or global | global budget + per-account upload cap | a per-user token budget: a judge can't see tokens, and the shared account makes "per user" one user anyway |
| "Per day" | rolling 24 h | a calendar day: whose time zone? judges are worldwide |
| Page count | at upload, before storing | in the job's parse: the judge waits for a failure the upload could have told them |
| Judge sample | a copy of a finished project | rendering it on the judge's first visit: spends on every fresh account and makes the judge wait |
| The image budget (T030) | count drawings from `frame_audits`, per month, refuse new work at the start | a dollar figure (fal bills per image; a count reads the same and needs no price table); a counter in the renderer (a second count to keep in step with the log, and a migration while #170 or T104 takes 0009); stopping a running job at the cap (half a board, as for tokens); counting fal requests (a safety redraw costs, but the gap is at most 3 to 1 and rare) |

## 9. How this is verified

- `record_usage` adds prompt + completion and one call to this month's row (two calls → one row);
  an error inside it is logged and swallowed; `NebiusChatModel` awaits `on_usage` once per answer
  and not for a failed call.
- `POST /projects` at the budget → 429 `llm_budget_spent`, nothing stored, no job; the fourth upload
  in 24 h → 429 `upload_limit` with `per_day`; a 16-page PDF with `UPLOAD_MAX_PAGES=15` → 413
  `too_many_pages` with `max_pages`, nothing stored; each off when its setting is unset.
- `…/attempts` and `…/comic` at the budget → 429, the frame and jobs untouched.
- The seed against a fake Auth transport: creates then, on a second run, updates the password;
  copies a settled project once (a second run copies nothing); refuses an unsettled source; never
  prints the password.
- Web: each new error code maps to its copy (`upload.ts`, the retry button, Make the comic).
- **T030:** `drawings_this_month` counts this UTC month's `frame_audits` rows of both targets and not
  last month's; `POST /projects`, `…/attempts` and `…/comic` at the image cap → 429
  `image_budget_spent`, nothing stored, no job, the frame untouched; the token budget's 429 wins when
  both are spent; off when `IMAGE_MONTHLY_GENERATION_CAP` is unset, blank or 0; `image_budget_spent`
  maps to its copy in the web; the comic route answers 429, not 500 (`_COMIC_STATUS`); after the judge
  seed copies a project, `drawings_this_month` is unchanged (the copied audits keep their
  `created_at`).
- **Live** (Tumo's go-ahead, no spend): the seed against the dev Supabase with a throwaway judge
  email, signing in as it in the browser and opening the copied storyboard and comic.

## 10. Open questions

- [x] **The two money caps' figures** (Katlego and Tumo, 2026-10-15: Katlego brings the remaining
  Token Factory credit and the fal spend allowed a month). **Tokens decided 2026-10-16 by Katlego:
  `LLM_MONTHLY_TOKEN_CAP` = 2,800,000** (30% of the $18 left; the arithmetic in deploy.md §6).
  **Drawings decided 2026-10-16 by Katlego, from Tumo's fal balance and top-up plan:
  `IMAGE_MONTHLY_GENERATION_CAP` = 800** (the arithmetic in deploy.md §6). A storyboard is about 130,000–175,000
  audit tokens and 17–26 drawings (§4, measured 2026-10-15); `LLM_MONTHLY_TOKEN_CAP` leaves one job's
  room under the credit, `IMAGE_MONTHLY_GENERATION_CAP` one job's (about 150 drawings) under the fal
  allowance. They are entered in Render's dashboard (deploy.md §6, `sync: false`), so the code
  doesn't wait on them; the deploy does.
- [x] Devpost's rules on a login for judges: the rules page couldn't be read by the assistant
  (403); **confirmed 2026-10-16: Devpost allows a judge login** (Katlego), so the shared judge account stands, its credentials in
  Devpost's testing instructions (T030).
