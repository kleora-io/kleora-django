"""`KleoraAuthentication` on a real `NinjaAPI`.

Every case goes through django-ninja's own machinery — `TestClient` resolves the
route, runs the auth callbacks and renders the response — because what is being
asserted is not that a function returns `Claims` but that *attaching this class
to an API* admits and refuses the right requests. The class is only worth
anything through the framework.
"""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest
from ninja import NinjaAPI
from ninja.testing import TestClient

from django_kleora import IssuerUnavailable, KleoraAuthentication
from tests.conftest import AUDIENCE, CLIENT_ID, TENANT, JWKSEndpoint, SigningKey, bearer


def client(namespace: str) -> TestClient:
    """One API per test: `NinjaAPI` registers its namespace process-wide."""

    api = NinjaAPI(auth=KleoraAuthentication(), urls_namespace=namespace)

    @api.get("/whoami")
    def whoami(request: HttpRequest) -> dict[str, Any]:
        claims = request.kleora  # type: ignore[attr-defined]
        return {
            "sub": claims.sub,
            "tenant": claims.tenant,
            "client_id": claims.client_id,
            "permissions": list(claims.permissions),
            "auth_is_kleora": request.auth is claims,  # type: ignore[attr-defined]
        }

    return TestClient(api)


def test_a_verifying_token_is_admitted_and_sets_request_kleora(
    key: SigningKey, jwks: JWKSEndpoint
) -> None:
    response = client("auth-ok").get("/whoami", headers=bearer(key.access_token()))

    assert response.status_code == 200
    body = response.json()
    assert body["tenant"] == TENANT
    assert body["client_id"] == CLIENT_ID
    assert body["permissions"] == ["invoices:read", "invoices:write"]
    # django-ninja's own convention and ours are the same object, not two.
    assert body["auth_is_kleora"] is True
    assert jwks.fetches == 1


def test_no_credential_is_401(key: SigningKey, jwks: JWKSEndpoint) -> None:
    response = client("auth-none").get("/whoami")

    assert response.status_code == 401
    assert jwks.fetches == 0, "a request with no token must not reach the issuer"


def test_another_scheme_is_401_and_not_a_malformed_token(
    key: SigningKey, jwks: JWKSEndpoint
) -> None:
    """`Basic` credentials are somebody else's authentication, not our bad token."""

    response = client("auth-basic").get("/whoami", headers={"Authorization": "Basic YWRhOng="})

    assert response.status_code == 401
    assert jwks.fetches == 0


def test_a_token_for_the_wrong_audience_is_401(key: SigningKey, jwks: JWKSEndpoint) -> None:
    token = key.access_token(audience=["https://api.someone-else.example"])

    assert client("auth-aud").get("/whoami", headers=bearer(token)).status_code == 401


def test_an_expired_token_is_401(key: SigningKey, jwks: JWKSEndpoint) -> None:
    token = key.access_token(lifetime=-3600)

    assert client("auth-exp").get("/whoami", headers=bearer(token)).status_code == 401


def test_an_id_token_is_401(key: SigningKey, jwks: JWKSEndpoint) -> None:
    """The same key, the same `alg`, the same claims — `typ` is the only difference.

    An ID token is typed `JWT`, an access token `at+jwt`. Without the type check this is the
    substitution that turns an identity assertion into an authorisation.
    """

    token = key.access_token(typ="JWT")

    assert client("auth-typ").get("/whoami", headers=bearer(token)).status_code == 401


def test_a_signature_from_an_unknown_key_is_401(jwks: JWKSEndpoint) -> None:
    stranger = SigningKey.make("kid-stranger")

    response = client("auth-kid").get("/whoami", headers=bearer(stranger.access_token()))

    assert response.status_code == 401


def test_an_unreachable_issuer_is_503_and_not_401(
    key: SigningKey, unreachable_jwks: JWKSEndpoint
) -> None:
    """The 401/503 split, at the surface a customer sees.

    An unknown `kid` is a bad token and the caller's problem; an issuer that
    cannot be read is our infrastructure and is retryable. Answering 401 to both
    tells every caller to discard a perfectly good token and go back to a
    provider that is already down.
    """

    response = client("auth-503").get("/whoami", headers=bearer(key.access_token()))

    assert response.status_code == 503
    assert unreachable_jwks.fetches >= 1


def test_issuer_unavailable_carries_a_problem_document_for_the_asking() -> None:
    """The escape hatch `auth.py` documents, for an API that wants one shape."""

    document = IssuerUnavailable().problem()

    assert document == {
        "type": "https://kleora.io/problems/issuer-unavailable",
        "title": "Identity provider unavailable",
        "status": 503,
        "detail": "the identity provider could not be reached to verify this token",
    }


def test_the_audience_may_be_the_client_id(key: SigningKey, jwks: JWKSEndpoint) -> None:
    """`AUDIENCE` is whichever of the two a service configures; both are in `aud`."""

    from django.test import override_settings

    from tests.settings import ISSUER

    with override_settings(KLEORA={"ISSUER": ISSUER, "AUDIENCE": CLIENT_ID}):
        response = client("auth-clientid").get("/whoami", headers=bearer(key.access_token()))

    assert response.status_code == 200
    assert AUDIENCE != CLIENT_ID
