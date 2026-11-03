# Design — `llm` (Nebius Token Factory provider)

**Status:** agreed · **Owner:** Katlego (Claude) · **Tasks:** T004, T075 · **Spec:** [SPEC.md](../../SPEC.md)
(every story calls a model through this)

---

## 1. What this covers

The one seam every model call in Panelwise goes through: an async client for Nebius Token Factory
with three tiers (fast, reasoning, vision), and `structured_chat`, which turns a call into a
validated Pydantic object. **Not covered:** prompts and schemas (each caller owns its own — T006
extraction, T007 shots, T020 audit), spend caps (T030), tracing spans (arrives with `core`
tracing; until then, usage is returned on every result and logged).

## 2. Reference material

| Kind | Where |
| --- | --- |
| Measured API behaviour this is built to | [docs/nebius-findings.md](../nebius-findings.md) (T001, 2026-09-28) |
| Code ported from | FrameFlow `services/api/app/services/openai_compat.py` (retries, reasoning-but-no-content error) and `llm_provider.py` (`structured_chat` repair retry) |
| External API | OpenAI-compatible `POST /v1/chat/completions` at `https://api.tokenfactory.nebius.com/v1` |

## 3. Domain model

```mermaid
classDiagram
    class Tier {
        <<enum>>
        FAST
        REASONING
        VISION
    }
    class Usage {
        +int prompt_tokens
        +int completion_tokens
        +int reasoning_tokens
    }
    class ChatResult {
        +str content
        +str model
        +Tier tier
        +Usage usage
        +str|None finish_reason
    }
    class StructuredResult~T~ {
        +T value
        +ChatResult chat
        +bool repaired
    }
    class NebiusChatModel {
        +from_settings(Settings) NebiusChatModel
        +model_for(Tier) str
        +chat(messages, tier, *, thinking, temperature, max_tokens, response_format) ChatResult
        +aclose()
    }
    class LLMError
    class LLMConfigError
    class LLMRequestError {
        +int|None status
    }
    class LLMEmptyResponse
    LLMError <|-- LLMConfigError
    LLMError <|-- LLMRequestError
    LLMError <|-- LLMEmptyResponse
    NebiusChatModel ..> ChatResult
    ChatResult --> Usage
    StructuredResult --> ChatResult
```

- `ChatResult.model` is the model the server says answered (`response.model`), falling back to the
  requested ID — anything that names a model to a user reports this, never a configured default.
- `content` has a leading `<think>…</think>` removed and is `.strip()`ped (findings U2: Super
  returns `"\n391"` with thinking on). Content that arrives as a list of parts is the
  concatenation of its `text` parts.
- `Usage.reasoning_tokens` comes from `usage.completion_tokens_details.reasoning_tokens`; 0 when
  absent. It is already included in `completion_tokens` (that is how it's billed).

## 4. Flow

```mermaid
sequenceDiagram
    participant C as Caller (T006 extraction…)
    participant S as structured_chat
    participant M as NebiusChatModel
    participant N as Token Factory
    C->>S: messages, Tier, ResponseModel
    S->>S: inline JSON schema into the system message
    S->>M: chat(..., response_format=json_schema strict)
    loop up to max_attempts (default 5, T075)
        M->>N: POST /chat/completions
        alt 429 or 5xx or network error
            N-->>M: status (+ Retry-After)
            M->>M: sleep Retry-After or backoff 2 s, 4 s, 8 s, 16 s (each capped 30 s)
        else 200
            N-->>M: choices[0].message, usage, model
        end
    end
    M-->>S: ChatResult
    S->>S: ResponseModel.model_validate_json(content)
    alt invalid
        S->>M: messages + assistant(bad) + user(error, "only corrected JSON")
        M-->>S: ChatResult
        S->>S: validate again (raises ValidationError if still invalid)
    end
    S-->>C: StructuredResult(value, chat, repaired)
```

**Failure paths:**
- 4xx other than 429 → `LLMRequestError(status)` immediately, no retry (retrying a bad request
  wastes credit). The error names the status and model; it never includes the API key or the
  request body (the body quotes the screenplay).
- Retries exhausted on 429 / 5xx / network → `LLMRequestError` with the last status (`None` for
  network).
- A connection that doesn't open within `connect_timeout_s` (10 s) is a network error like any
  other, and retried. A response that doesn't arrive within `timeout_s` (120 s) is a read timeout:
  retried once, and the second read timeout of a call ends it with `LLMRequestError(None)`
  (`_MAX_READ_TIMEOUTS = 2`, T075). A model that hangs is not an outage that passes, and five
  waits of 120 s would hold the call for ten minutes.
- 200 whose body isn't JSON (something in front of Token Factory answered) → `LLMRequestError(200)`,
  no retry. Every failure this module raises is an `LLMError`.
- 200 with empty content → `LLMEmptyResponse`. If the message carries `reasoning_content`, the
  error says thinking consumed the budget and to call with `thinking=False` or raise `max_tokens`.
- Tier with no model configured (e.g. `NEBIUS_MODEL_VISION` empty) → `LLMConfigError` at call time;
  a missing `NEBIUS_API_KEY` → `LLMConfigError` in `from_settings`.
- Repair also invalid → the `ValidationError` propagates. The caller decides; the grounding filter
  is never loosened to absorb it.

## 5. State

Stateless per call. The client holds one `httpx2.AsyncClient` (connection pool) for its lifetime.

## 6. Contracts

```python
# app/llm/client.py
class Tier(StrEnum):
    FAST = "fast"            # NEBIUS_MODEL_FAST       — extraction, shots (bulk, schema-bound)
    REASONING = "reasoning"  # NEBIUS_MODEL_REASONING  — judgement calls
    VISION = "vision"        # NEBIUS_MODEL_VISION     — describes images only (nebius-findings § The vision decision)

type Message = dict[str, Any]   # OpenAI chat message; content may be a str or a list of parts

class NebiusChatModel:
    def __init__(self, *, api_key: str, base_url: str, models: Mapping[Tier, str],
                 timeout_s: float = 120.0, connect_timeout_s: float = 10.0,  # T075
                 max_attempts: int = 5,                                    # T075: was 3
                 transport: httpx2.AsyncBaseTransport | None = None,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
                 on_usage: Callable[[ChatResult], Awaitable[None]] | None = None,  # T069: counts the month's tokens
                 vision_thinking: bool | None = None) -> None: ...         # T105: VISION's thinking default
    @classmethod
    def from_settings(cls, settings: Settings) -> "NebiusChatModel": ...
    def model_for(self, tier: Tier) -> str: ...
    async def chat(self, messages: Sequence[Message], tier: Tier = Tier.FAST, *,
                   thinking: bool | None = None,          # None = the tier's default (below)
                   temperature: float = 0.0,
                   max_tokens: int | None = None,
                   response_format: Mapping[str, Any] | None = None) -> ChatResult: ...
    async def aclose(self) -> None: ...

# app/llm/structured.py
async def structured_chat[T: BaseModel](model: NebiusChatModel, messages: Sequence[Message],
        response_model: type[T], tier: Tier = Tier.FAST, *, max_repair_attempts: int = 1,
        thinking: bool | None = None, temperature: float = 0.0,
        max_tokens: int | None = None,
        grammar: Mapping[str, Any] | None = None) -> StructuredResult[T]: ...
#   grammar (T109): the schema sent as response_format's "schema" in place of model_json_schema(),
#   for limits the decoder enforces but the prompt doesn't show (verify.md § T109 contracts). The
#   prompt's schema text and the validation stay response_model's. None (the default): as before
```

**Thinking defaults** (findings U2): `FAST` → `False`; `REASONING` → `True`; `VISION` →
`NEBIUS_VISION_THINKING` (default `false` since T105, findings § U8; blank sends nothing, as
before T105, when the toggle was only measured on Nemotron). `False` sends
`chat_template_kwargs: {"enable_thinking": false}`; `True` sends `{"enable_thinking": true}`.

**Request body** (exactly these keys; absent ones are omitted):
`model, messages, temperature, max_tokens?, response_format?, chat_template_kwargs?`

**Structured request:** `response_format = {"type": "json_schema", "json_schema": {"name":
<ResponseModel.__name__>, "schema": <model_json_schema()>, "strict": true}}` (findings U1), plus
`"Reply with JSON only, matching this JSON Schema: <schema>"` appended to the first system message,
(as an extra `text` part when its content is a list of parts), or a new leading system message
if there is none. Never a second system message: some chat templates accept only one. With
`grammar` (T109), `response_format`'s `"schema"` is `grammar`; the prompt's `<schema>` is still
`model_json_schema()`, and the repair turn and validation are unchanged.

**Settings** (`app/core/config.py`, env names in `.env.example`): `nebius_api_key`,
`nebius_base_url`, `nebius_model_fast`, `nebius_model_reasoning`, `nebius_model_vision`,
`nebius_vision_thinking` (false, T105), `llm_request_timeout_s` (120), `llm_connect_timeout_s` (10, T075), `llm_max_attempts` (5, T075:
was 3).

## 7. Structure

| Path | New? | Responsibility |
| --- | --- | --- |
| `services/api/app/llm/__init__.py` | new | re-exports the contract above |
| `services/api/app/llm/client.py` | new | `Tier`, `Usage`, `ChatResult`, errors, `NebiusChatModel` |
| `services/api/app/llm/structured.py` | new | `StructuredResult`, `structured_chat` |
| `services/api/app/llm/smoke.py` | new | `python -m app.llm.smoke`: one real call per configured tier, prints model + usage (the T004 Verify step) |
| `services/api/app/core/config.py` | changed | the Nebius settings (T075: `llm_connect_timeout_s`, `llm_max_attempts` 5) |
| `.env.example` | changed | T075: `LLM_MAX_ATTEMPTS=5`, `LLM_CONNECT_TIMEOUT_S=10` |
| `services/api/tests/llm/test_client.py`, `test_structured.py` | new | `httpx2.MockTransport` tests, no network |

## 8. Decisions & alternatives

| Decision | Chosen | Rejected, and why |
| --- | --- | --- |
| Providers | Nebius only | FrameFlow's Gemini → Ollama chain: Panelwise's locked stack is Nemotron on Token Factory; a silent fallback to another vendor would also make "which model answered" harder to trust |
| Sync or async | async (`httpx2.AsyncClient`) | FrameFlow's sync client: the API is async, and T006 runs chunk extraction concurrently (findings U4: TPM, not RPM, is the limit) |
| JSON mode | `json_schema` strict + schema in prompt | `json_object`: wrong shapes and one invented detail in the probe (U1). `guided_json`: ignored |
| Thinking | off by default on FAST | on everywhere: ~68× output tokens for a one-number answer (U2) |
| One base URL | yes | per-tier URLs: every Nemotron model answers on the default host (U3) |
| Retry on 4xx | never (except 429) | a malformed request fails the same way every time and costs credit |
| How long a call rides out an outage (T075) | 5 attempts, waits 2, 4, 8, 16 s, a 10 s connect timeout: a dropped connection is retried for about 80 s | 3 attempts, waits 1 s and 2 s, no connect timeout of its own (before T075): on 2026-10-10 Token Factory dropped connections on and off from 21:28 to 21:38, each `ConnectError` took about 20 s, and three of them ended a call in 45 s; 3 of sipho-and-siphokazi's 31 audits were withheld as `audit_error` for it |
| A read timeout (T075) | at most 2 per call | retried like a dropped connection: five waits of 120 s on a hung model |
| Limits only the decoder sees (T109) | `structured_chat(grammar=)`: one optional schema for `response_format` | `Field(max_length=…)` on the response model: the prompt's schema text changes with it, and on Super VL that changed 7 of 10 answers that reached no limit (verify.md §9 T109); a vision-only client method: two paths to the same request |
| Re-audit an `audit_error` later in the job (T075) | not now: a follow-up in the storyboard and comic jobs | here: the client can't know a drawing exists. Those jobs are built (T026, T064): an `ERROR` audit withholds and the loop redraws; a later re-audit was not added |

Deviations from [docs/architecture-defaults.md](../architecture-defaults.md): none.

## 9. How this is verified

- Unit tests with `httpx2.MockTransport` assert the **exact request body** per tier and thinking
  setting, retry and `Retry-After` behaviour (with an injected `sleep`), no retry on 400, the
  empty-content errors, `<think>` stripping, usage parsing, and that no error message contains the
  API key.
- `structured_chat` tests: schema inlined into the existing system message (not a second one),
  valid on the first try → `repaired=False`, invalid then valid → `repaired=True` with the repair
  turn shaped as specified, invalid twice → `ValidationError`.
- **T109:** `structured_chat(grammar=g)` sends `g` as `response_format.json_schema.schema` and still
  puts `model_json_schema()` in the system message; a repair turn resends with `g` too; without
  `grammar` the body is byte for byte today's.
- **T075:** with an injected `sleep` and a `MockTransport`: four `ConnectError`s then a 200 answer,
  after waits of 2, 4, 8 and 16 s; five `ConnectError`s give `LLMRequestError(None)` after 5
  attempts; two `ReadTimeout`s end the call after 2 attempts, while a `ReadTimeout` then a
  `ConnectError` then a 200 answers; `from_settings` passes the connect timeout to the client's
  `httpx2.Timeout`; a `Retry-After` of 60 still waits 30 s.
- `uv run python -m app.llm.smoke` against the real account: FAST and REASONING answer, and FAST
  reports `reasoning_tokens == 0`.

## 10. Open questions

- [ ] Sampling for grounded extraction (U6) is decided in T006; `temperature` defaults to 0.0 here
  and callers may override.
