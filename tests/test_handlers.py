"""`install_problem_handlers`, judged against the published contract and not against itself.

A test that checks the handler emits what the handler emits proves nothing, so
the expected slugs, statuses and `type` namespace are written out here, from
what Kleora publishes, rather than imported from `django_kleora.problems`:

* every Kleora problem type lives under `https://kleora.io/problems/`, and each
  slug is a page there (https://kleora.io/problems/unauthenticated);
* a credential that cannot be verified is the caller's problem: 401
  `unauthenticated`, the slug Kleora's own APIs answer that status with;
* an issuer whose key set cannot be read is the provider's problem, and
  retryable: 503 `issuer-unavailable`, an SDK-side slug the management API never
  answers with.

A change to either side of that contract has to change this module too.
"""

from __future__ import annotations

from typing import Any

import pytest
from django.http import HttpRequest, HttpResponse
from ninja import NinjaAPI
from ninja.errors import AuthenticationError, HttpError
from ninja.testing import TestClient

from django_kleora import (
    KleoraAuthentication,
    install_problem_handlers,
)
from django_kleora.problems import PROBLEM_BASE
from tests.conftest import (
    JWKSEndpoint,
    SigningKey,
    bearer,
)

PROBLEM_JSON = "application/problem+json"

#: The namespace every Kleora problem type lives under.
NAMESPACE = "https://kleora.io/problems/"

#: The middleware failure mapping every Kleora SDK answers with: a credential
#: that cannot be verified, and an issuer whose key set cannot be read.
MAPPING = {401: "unauthenticated", 503: "issuer-unavailable"}

#: Slugs the management API itself declares at 401. `unauthenticated` is the
#: one for a missing or unverifiable credential; the others are answers to
#: specific self-service operations and never to a bearer token.
MANAGEMENT_401 = {
    "unauthenticated": {401},
    "invalid-code": {401},
    "invalid-credentials": {401},
    "reauth-required": {401},
}


def problem_namespace() -> str:
    """The `type` prefix every Kleora problem document carries."""

    return NAMESPACE


def sdk_mapping() -> dict[int, str]:
    """`{401: …, 503: …}`: the middleware failure mapping."""

    return dict(MAPPING)


def the_slug_for_unverifiable_credentials() -> str:
    """The slug for a credential this package could not verify."""

    return sdk_mapping()[401]


def client(name: str, *, problems: bool = True) -> TestClient:
    """The quickstart's arrangement: our auth class on the whole API."""

    api = NinjaAPI(auth=KleoraAuthentication(), urls_namespace=name)

    @api.get("/invoices")
    def invoices(request: HttpRequest) -> dict[str, Any]:
        return {"ok": True}

    if problems:
        install_problem_handlers(api)
    return TestClient(api)


def test_a_refused_request_carries_the_slug_both_specs_name(
    key: SigningKey, jwks: JWKSEndpoint
) -> None:
    """A refused request carries the published slug, status and namespace."""

    slug = the_slug_for_unverifiable_credentials()
    response = client("problems-none").get("/invoices")

    assert response.status_code == 401
    assert response["Content-Type"] == PROBLEM_JSON
    document = response.json()
    assert document["type"] == f"{problem_namespace()}{slug}"
    assert document["status"] == 401
    assert document["title"]
    # RFC 6750 §3 requires it on a 401: a client that cannot
    # tell "no credential" from "wrong credential" retries the wrong thing.
    assert response["WWW-Authenticate"] == "Bearer"
    assert jwks.fetches == 0, "a request with no token must not reach the issuer"


def test_the_slug_is_the_one_the_management_api_declares_for_a_401() -> None:
    """The SDK's 401 slug is one the platform declares at 401, under the same namespace.

    Several slugs answer 401 on the management API, so what this package has a
    contract about is *this* slug rather than a count; and the namespace this
    package writes is the platform's, not a second one.
    """

    slug = sdk_mapping()[401]

    assert slug in MANAGEMENT_401
    assert 401 in MANAGEMENT_401[slug]
    assert problem_namespace() == PROBLEM_BASE


def test_without_the_call_django_ninja_writes_its_own_body(
    key: SigningKey, jwks: JWKSEndpoint
) -> None:
    """The behaviour the call exists to change, pinned so the fix cannot be mistaken for it.

    `ninja.errors._default_http_error` renders `{"detail": str(exc)}` through the
    API's renderer, so the media type is `application/json` as well — which is
    what a client selecting on `application/problem+json` never sees.
    """

    response = client("problems-absent", problems=False).get("/invoices")

    assert response.status_code == 401
    assert response.json() == {"detail": "Unauthorized"}
    assert response["Content-Type"] == "application/json; charset=utf-8"


@pytest.mark.parametrize(
    "kind",
    ["expired", "wrong-audience", "unknown-key", "id-token", "other-scheme"],
)
def test_every_unverifiable_credential_gets_the_same_document(
    kind: str, key: SigningKey, jwks: JWKSEndpoint
) -> None:
    """One sentence for all of them, and the reason in none of them.

    The difference between "expired" and "signed by a key we have never seen" is
    of no use to a caller without a valid token and of every use to one probing,
    so it goes to the logger. A document that named it would be a disclosure this
    package's whole 401 story is written against.
    """

    stranger = SigningKey.make("kid-stranger")
    headers = {
        "expired": bearer(key.access_token(lifetime=-3600)),
        "wrong-audience": bearer(key.access_token(audience=["https://api.elsewhere.example"])),
        "unknown-key": bearer(stranger.access_token()),
        "id-token": bearer(key.access_token(typ="JWT")),
        "other-scheme": {"Authorization": "Basic YWRhOng="},
    }[kind]

    response = client(f"problems-{kind}").get("/invoices", headers=headers)

    assert response.status_code == 401
    document = response.json()
    assert document["type"] == f"{problem_namespace()}{the_slug_for_unverifiable_credentials()}"
    assert document == {
        "type": document["type"],
        "title": "Authentication required",
        "status": 401,
        "detail": "the request could not be authenticated",
    }
    for leak in ("expired", "signature", "kid", "audience", "typ", str(stranger.kid)):
        assert leak not in document["detail"], leak


def test_an_unreachable_issuer_is_not_collapsed_into_the_401(
    key: SigningKey, unreachable_jwks: JWKSEndpoint
) -> None:
    """The 401/503 distinction, kept by the thing that unifies everything else.

    A bad token is the caller's problem; an issuer whose key set cannot be read is
    ours and is retryable. Answering 401 to both tells every client to discard a
    perfectly good token and go back to a provider that is already down — so the
    two statuses and the two slugs both have to stay two.
    """

    mapping = sdk_mapping()
    response = client("problems-503").get("/invoices", headers=bearer(key.access_token()))

    assert response.status_code == 503
    assert response["Content-Type"] == PROBLEM_JSON
    document = response.json()
    assert document["type"] == f"{problem_namespace()}{mapping[503]}"
    assert document["status"] == 503
    assert mapping[503] != mapping[401]
    # `issuer-unavailable` is an SDK-side slug, not one the management surface
    # can ever answer, so it is deliberately absent from that taxonomy.
    assert mapping[503] not in MANAGEMENT_401
    # No `WWW-Authenticate` on a 503: there is nothing for the caller to
    # re-present, and a challenge would invite exactly the retry that cannot help.
    with pytest.raises(KeyError):
        response["WWW-Authenticate"]


def test_a_handler_the_application_registers_afterwards_wins(
    key: SigningKey, jwks: JWKSEndpoint
) -> None:
    """The application's decision about its own API outranks this package's.

    `add_exception_handler` is a dict assignment, so the last writer wins. That is
    the property that makes the call safe to recommend unconditionally: nothing it
    does is irreversible, and an application with its own opinion keeps it.
    """

    api = NinjaAPI(auth=KleoraAuthentication(), urls_namespace="problems-override")

    @api.get("/invoices")
    def invoices(request: HttpRequest) -> dict[str, Any]:
        return {"ok": True}

    install_problem_handlers(api)

    @api.exception_handler(AuthenticationError)
    def mine(request: HttpRequest, exc: Exception) -> HttpResponse:
        return api.create_response(request, {"mine": True}, status=401)

    response = TestClient(api).get("/invoices")

    assert response.status_code == 401
    assert response.json() == {"mine": True}


def test_it_leaves_the_frameworks_other_answers_alone(key: SigningKey, jwks: JWKSEndpoint) -> None:
    """Registered on `AuthenticationError`, not on `HttpError`.

    Registering the parent would have swallowed every `HttpError` the application
    raises itself and answered it in Kleora's shape, which is this package
    deciding what somebody else's refusals look like.
    """

    api = NinjaAPI(auth=KleoraAuthentication(), urls_namespace="problems-untouched")

    @api.get("/conflict")
    def conflict(request: HttpRequest) -> dict[str, Any]:
        raise HttpError(409, "somebody else's refusal")

    @api.get("/needs")
    def needs(request: HttpRequest, n: int) -> dict[str, Any]:
        return {"n": n}

    install_problem_handlers(api)
    client_ = TestClient(api)
    headers = bearer(key.access_token())

    theirs = client_.get("/conflict", headers=headers)
    assert theirs.status_code == 409
    assert theirs.json() == {"detail": "somebody else's refusal"}
    assert theirs["Content-Type"] == "application/json; charset=utf-8"

    invalid = client_.get("/needs", headers=headers)
    assert invalid.status_code == 422
    assert "detail" in invalid.json()
    assert invalid["Content-Type"] == "application/json; charset=utf-8"


def test_an_authentication_error_at_another_status_is_not_translated(
    key: SigningKey, jwks: JWKSEndpoint
) -> None:
    """ninja raises it with 401 and nothing else does.

    An application that raised `AuthenticationError(403, …)` has not said
    "unauthenticated", and a 401 document answering a 403 would be a worse answer
    than the framework's own.
    """

    api = NinjaAPI(urls_namespace="problems-odd-status")

    @api.get("/odd")
    def odd(request: HttpRequest) -> dict[str, Any]:
        raise AuthenticationError(403, "not for you")

    install_problem_handlers(api)

    response = TestClient(api).get("/odd")

    assert response.status_code == 403
    assert response.json() == {"detail": "not for you"}


def test_it_returns_the_api_and_is_idempotent(key: SigningKey, jwks: JWKSEndpoint) -> None:
    """So the construction can be one expression, and a second call changes nothing."""

    api = NinjaAPI(auth=KleoraAuthentication(), urls_namespace="problems-idempotent")

    @api.get("/invoices")
    def invoices(request: HttpRequest) -> dict[str, Any]:
        return {"ok": True}

    assert install_problem_handlers(api) is api
    assert install_problem_handlers(api) is api

    response = TestClient(api).get("/invoices")

    assert response.status_code == 401
    assert response["Content-Type"] == PROBLEM_JSON
