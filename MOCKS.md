# What's mocked

Every file in `mocks/` is listed here, with what it stands in for. This is also the honest answer
to the judges' favourite question: "Which part of what we just saw is real, and which part is mocked?"

**Mock peripheral services only:** payments, email, identity, third-party data you can't rely on
during judging. **Never the core differentiator:** nothing under `event.toml [scope] core`
(`services/api/app/script`, `app/grounding`, `app/llm`, `app/verify`) may
import from `mocks/`.

**Today `mocks/` is empty, and Panelwise plans no mocks.** Every model call in the demo is a live
Token Factory call, and every frame is a real render. The seeded judge project (T030) is real
output rendered in advance, not a mock: it is produced by the same pipeline and stored like any
other project. Test doubles inside `services/api/tests/` (`httpx2.MockTransport`) keep the suite
offline; they are not mocks in this sense and never ship in the app.

**Not enforced mechanically.** The kit's gate fails a push when a `[scope] core` path imports from
`mocks/`; Panelwise's `scripts/gate.sh` does not have that check. Adding it is a change to
`scripts/gate.sh`, which waits for the other contributor's review or the lead's explicit
authorization (AGENTS.md §4). Until then, a reviewer checks it by hand, and
`./hack preflight` still fails if a file in any `mocks/` folder is missing from this table.

| Mock file | Stands in for | Why |
|---|---|---|
