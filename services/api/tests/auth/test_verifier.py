"""The Supabase token check -- web.md §6 *API internals* (T053). No network: a local ES256 key
and an httpx2.MockTransport JWKS endpoint that counts its fetches."""

import base64
import json
import time
import uuid
from typing import Any

import httpx2
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from jwt.algorithms import ECAlgorithm

from app.core.auth import AuthError, AuthUnavailable, Caller, SupabaseJwtVerifier

URL = "https://example.supabase.co"
ISS = f"{URL}/auth/v1"
KEY = ec.generate_private_key(ec.SECP256R1())
OTHER = ec.generate_private_key(ec.SECP256R1())


def jwk(private: ec.EllipticCurvePrivateKey, kid: str, alg: str | None = "ES256") -> dict[str, Any]:
    key = json.loads(ECAlgorithm.to_jwk(private.public_key()))
    key |= {"kid": kid, "use": "sig"} | ({"alg": alg} if alg else {})
    return key


class Jwks:
    """The JWKS endpoint: serves `keys`, counts fetches, can fail."""

    def __init__(self, *keys: dict[str, Any]) -> None:
        self.keys = list(keys)
        self.fetches = 0
        self.down = False

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        assert str(request.url) == f"{ISS}/.well-known/jwks.json"
        self.fetches += 1
        if self.down:
            return httpx2.Response(503)
        return httpx2.Response(200, json={"keys": self.keys})


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def verifier(jwks: Jwks, clock: Clock | None = None) -> SupabaseJwtVerifier:
    client = httpx2.AsyncClient(transport=httpx2.MockTransport(jwks))
    return SupabaseJwtVerifier(supabase_url=URL, client=client, clock=clock or Clock())


def token(
    *,
    key: ec.EllipticCurvePrivateKey = KEY,
    kid: str | None = "k1",
    alg: str = "ES256",
    drop: tuple[str, ...] = (),
    **claims: Any,
) -> str:
    now = int(time.time())
    body: dict[str, Any] = {
        "sub": str(USER),
        "aud": "authenticated",
        "iss": ISS,
        "role": "authenticated",
        "is_anonymous": False,
        "iat": now,
        "exp": now + 3600,
    } | claims
    for name in drop:
        body.pop(name)
    headers = {"kid": kid} if kid is not None else {}
    return jwt.encode(body, key, algorithm=alg, headers=headers)


USER = uuid.uuid4()


async def test_a_good_token_is_its_user() -> None:
    assert await verifier(Jwks(jwk(KEY, "k1"))).verify(token()) == Caller(user_id=USER)


@pytest.mark.parametrize(
    "bad",
    [
        {"exp": int(time.time()) - 120},  # expired, past the 30 s leeway
        {"aud": "anon"},
        {"iss": "https://elsewhere.supabase.co/auth/v1"},
        {"role": "anon"},
        {"role": "service_role"},
        {"is_anonymous": True},
        {"sub": "not-a-uuid"},
    ],
)
async def test_a_wrong_claim_is_refused(bad: dict[str, Any]) -> None:
    with pytest.raises(AuthError):
        await verifier(Jwks(jwk(KEY, "k1"))).verify(token(**bad))


@pytest.mark.parametrize("missing", ["exp", "iat", "sub", "aud", "iss", "role"])
async def test_a_missing_required_claim_is_refused(missing: str) -> None:
    with pytest.raises(AuthError):
        await verifier(Jwks(jwk(KEY, "k1"))).verify(token(drop=(missing,)))


async def test_a_token_signed_by_another_key_is_refused() -> None:
    with pytest.raises(AuthError):
        await verifier(Jwks(jwk(KEY, "k1"))).verify(token(key=OTHER))


async def test_hs256_and_none_are_refused_even_with_a_known_kid() -> None:
    v = verifier(Jwks(jwk(KEY, "k1")))
    hs = jwt.encode({"sub": str(USER)}, "x" * 32, algorithm="HS256", headers={"kid": "k1"})
    with pytest.raises(AuthError):
        await v.verify(hs)

    # An unsigned token, built by hand: header {"alg": "none"}, a payload, an empty signature.
    def b64(part: dict[str, Any]) -> str:
        return base64.urlsafe_b64encode(json.dumps(part).encode()).rstrip(b"=").decode()

    claims = {
        "sub": str(USER),
        "aud": "authenticated",
        "iss": ISS,
        "role": "authenticated",
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    }
    none = f"{b64({'alg': 'none', 'typ': 'JWT', 'kid': 'k1'})}.{b64(claims)}."
    with pytest.raises(AuthError):
        await v.verify(none)


async def test_a_token_without_a_kid_is_refused() -> None:
    with pytest.raises(AuthError):
        await verifier(Jwks(jwk(KEY, "k1"))).verify(token(kid=None))


async def test_a_jwk_without_alg_on_p256_is_es256() -> None:
    assert await verifier(Jwks(jwk(KEY, "k1", alg=None))).verify(token()) == Caller(user_id=USER)


async def test_garbage_is_refused() -> None:
    with pytest.raises(AuthError):
        await verifier(Jwks(jwk(KEY, "k1"))).verify("not.a.token")


async def test_the_jwks_is_cached() -> None:
    jwks = Jwks(jwk(KEY, "k1"))
    v = verifier(jwks)
    for _ in range(5):
        await v.verify(token())
    assert jwks.fetches == 1


async def test_an_unknown_kid_refetches_at_most_once_a_minute() -> None:
    jwks, clock = Jwks(jwk(KEY, "k1")), Clock()
    v = verifier(jwks, clock)
    await v.verify(token())
    for _ in range(10):  # a flood of random kids
        with pytest.raises(AuthError):
            await v.verify(token(kid=uuid.uuid4().hex))
    assert jwks.fetches == 1  # the keys are a second old: the flood fetches nothing
    clock.now += 61
    for _ in range(10):
        with pytest.raises(AuthError):
            await v.verify(token(kid=uuid.uuid4().hex))
    assert jwks.fetches == 2  # a minute on, one refetch for the whole flood
    clock.now += 61
    jwks.keys.append(jwk(OTHER, "k2"))  # a rotated-in key appears
    assert await v.verify(token(key=OTHER, kid="k2")) == Caller(user_id=USER)
    assert jwks.fetches == 3


async def test_a_failed_fetch_serves_the_cached_keys() -> None:
    jwks, clock = Jwks(jwk(KEY, "k1")), Clock()
    v = verifier(jwks, clock)
    await v.verify(token())
    jwks.down = True
    clock.now += 601  # past the TTL: a refresh is due and fails
    assert await v.verify(token()) == Caller(user_id=USER)


async def test_no_keys_at_all_is_unavailable_not_unauthorized() -> None:
    jwks = Jwks(jwk(KEY, "k1"))
    jwks.down = True
    with pytest.raises(AuthUnavailable):
        await verifier(jwks).verify(token())


async def test_one_unparseable_key_does_not_hide_the_good_ones() -> None:
    jwks = Jwks({"kid": "weird", "kty": "OKP", "crv": "X448", "x": "AAAA"}, jwk(KEY, "k1"))
    assert await verifier(jwks).verify(token()) == Caller(user_id=USER)
