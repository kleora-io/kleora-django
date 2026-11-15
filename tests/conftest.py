"""Django, configured; keys, minted; and a JWKS endpoint that answers locally.

The whole suite runs with no stack, no network and no database: tokens are
signed here with an ES256 key made here, and the issuer's JWKS document is
served by an `httpx.MockTransport` installed into `kleora`'s per-issuer
cache. What is exercised is therefore the *real* verifier — the real signature
check, the real `kid` lookup, the real error codes — with only the socket
replaced. `kleora`'s own test suite does the same thing for the same reason,
and this is deliberately its smaller sibling rather than a second way of doing
it.

The one reach into a private name is `kleora.verify._CACHES`, which is
where `verify_access_token` keeps the cache it shares per issuer per process.
There is no public way to hand this package's verification a prepared cache —
`django_kleora` calls `verify_access_token(token, issuer=…, audience=…)`
with no `jwks`, because that is what a customer's settings can express — so a
test that wants to control the key set has to put it where that call will look.
Reaching for the public `jwks=` parameter instead would mean testing a call this
package never makes.
"""

from __future__ import annotations

import os
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import django
import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from jwt.algorithms import ECAlgorithm

# Assigned rather than `setdefault`: a shell that already exports another
# project's `DJANGO_SETTINGS_MODULE` would otherwise leave this suite pointed at
# a settings module that is not in this project. There is exactly one settings
# module a run of this suite can mean, so it says which.
os.environ["DJANGO_SETTINGS_MODULE"] = "tests.settings"
django.setup()

from django.test import RequestFactory  # noqa: E402
from kleora._environments import classify_issuer  # noqa: E402
from kleora.jwks import JWKSCache  # noqa: E402
from kleora.verify import _CACHES  # noqa: E402

ISSUER = "https://acme.kleora.eu"
SANDBOX_ISSUER = "https://acme-sandbox.kleora.eu"
AUDIENCE = "https://api.acme.example"
CLIENT_ID = "8f1c9d5e-0b3a-4d1e-9a2b-6c7d8e9f0a1b"
TENANT = "0f6b2c81-6d2a-4e8e-bd2f-6a8c5f3a1d44"

TEST_KEY = "kl_test_" + "K" * 40
LIVE_KEY = "kl_live_" + "L" * 40


@dataclass
class SigningKey:
    """One ES256 key pair, standing in for an environment's signing key."""

    kid: str
    private: ec.EllipticCurvePrivateKey

    @classmethod
    def make(cls, kid: str = "kid-active") -> SigningKey:
        return cls(kid=kid, private=ec.generate_private_key(ec.SECP256R1()))

    def public_jwk(self) -> dict[str, Any]:
        jwk: dict[str, Any] = dict(ECAlgorithm.to_jwk(self.private.public_key(), as_dict=True))
        jwk.update({"kid": self.kid, "use": "sig", "alg": "ES256"})
        return jwk

    def access_token(
        self,
        *,
        issuer: str = ISSUER,
        audience: str | list[str] | None = None,
        permissions: list[str] | None = None,
        lifetime: int = 300,
        typ: str = "at+jwt",
        **overrides: Any,
    ) -> str:
        """A token shaped like a Kleora access token."""

        issued = int(time.time())
        payload: dict[str, Any] = {
            "iss": issuer,
            "sub": str(uuid.uuid4()),
            "aud": [CLIENT_ID, AUDIENCE] if audience is None else audience,
            "iat": issued,
            "exp": issued + lifetime,
            "jti": str(uuid.uuid4()),
            "client_id": CLIENT_ID,
            "scope": "openid profile email",
            "env": classify_issuer(issuer),
            "tenant": TENANT,
            "tenant_slug": "acme",
            "roles": ["owner"],
            "permissions": ["invoices:read", "invoices:write"]
            if permissions is None
            else permissions,
            "email": "ada@acme.example",
            "email_verified": True,
            "amr": ["pwd"],
        }
        payload.update(overrides)
        return jwt.encode(
            payload,
            self.private,
            algorithm="ES256",
            headers={"kid": self.kid, "typ": typ},
        )


@dataclass
class JWKSEndpoint:
    """`/.well-known/jwks.json` for one issuer, counting what it answered."""

    keys: list[SigningKey] = field(default_factory=list)
    status: int = 200
    fetches: int = 0

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.fetches += 1
        if self.status != 200:
            return httpx.Response(self.status, json={"title": "no"})
        return httpx.Response(
            200,
            json={"keys": [key.public_jwk() for key in self.keys]},
            headers={"Cache-Control": "max-age=300"},
        )

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handle))


@pytest.fixture
def key() -> SigningKey:
    return SigningKey.make()


@pytest.fixture
def jwks(key: SigningKey) -> Iterator[JWKSEndpoint]:
    """The issuer's key set, installed where `verify_access_token` will look.

    Torn down by emptying the shared dictionary rather than by restoring it: the
    cache is per process and per issuer, so a cache left behind would be the one
    the *next* test verified against, and a test that passed for that reason is
    worse than one that failed.
    """

    endpoint = JWKSEndpoint(keys=[key])
    for issuer in (ISSUER, SANDBOX_ISSUER):
        _CACHES[issuer] = JWKSCache(issuer, client=endpoint.client())
    yield endpoint
    _CACHES.clear()


@pytest.fixture
def unreachable_jwks() -> Iterator[JWKSEndpoint]:
    """An issuer whose key set cannot be read at all — the 503 case."""

    endpoint = JWKSEndpoint(keys=[], status=503)
    _CACHES[ISSUER] = JWKSCache(ISSUER, client=endpoint.client())
    yield endpoint
    _CACHES.clear()


@pytest.fixture
def rf() -> RequestFactory:
    return RequestFactory()


def bearer(token: str) -> dict[str, str]:
    """The `Authorization` header, for `RequestFactory` and ninja's `TestClient` alike."""

    return {"Authorization": f"Bearer {token}"}
