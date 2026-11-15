"""`@requires_permission`: the four answers, on both kinds of view.

Both kinds matter. On a plain Django view behind `KleoraAuthMiddleware` the
decorator is the only thing that refuses anything; on a django-ninja operation
it sits under `@api.get` and has to survive django-ninja's parameter resolution,
which reads the *wrapped* function's signature. The quickstart puts it there, so
that is the arrangement that has to work.
"""

from __future__ import annotations

import json
from typing import Any

from django.http import HttpRequest, HttpResponse, HttpResponseBase, JsonResponse
from django.test import RequestFactory
from ninja import NinjaAPI
from ninja.testing import TestClient

from django_kleora import (
    KleoraAuthentication,
    KleoraAuthMiddleware,
    requires_permission,
)
from tests.conftest import TENANT, JWKSEndpoint, SigningKey, bearer


def guarded(permission: str = "invoices:read") -> KleoraAuthMiddleware:
    """A plain Django view behind the middleware and the decorator."""

    @requires_permission(permission)
    def view(request: HttpRequest) -> HttpResponse:
        return JsonResponse({"ok": True})

    return KleoraAuthMiddleware(view)


def body_of(response: HttpResponseBase) -> dict[str, Any]:
    """The JSON a response carried. `HttpResponseBase` has no `content`; this does."""

    assert isinstance(response, HttpResponse)
    body: dict[str, Any] = json.loads(response.content)
    return body


def problem_of(response: HttpResponseBase) -> dict[str, Any]:
    assert response["Content-Type"] == "application/problem+json"
    return body_of(response)


def test_a_token_carrying_the_permission_runs_the_view(
    rf: RequestFactory, key: SigningKey, jwks: JWKSEndpoint
) -> None:
    response = guarded()(
        rf.get("/invoices", headers={"Authorization": f"Bearer {key.access_token()}"})
    )

    assert response.status_code == 200
    assert body_of(response) == {"ok": True}


def test_a_token_without_it_is_403_naming_the_permission(
    rf: RequestFactory, key: SigningKey, jwks: JWKSEndpoint
) -> None:
    token = key.access_token(permissions=["invoices:write"])

    response = guarded()(rf.get("/invoices", headers={"Authorization": f"Bearer {token}"}))

    assert response.status_code == 403
    body = problem_of(response)
    assert body["type"] == "https://kleora.io/problems/insufficient-permission"
    assert body["title"] == "Permission denied"
    assert body["status"] == 403
    assert "invoices:read" in body["detail"]


def test_a_truncated_permissions_claim_says_so_in_the_403(
    rf: RequestFactory, key: SigningKey, jwks: JWKSEndpoint
) -> None:
    """An access token's `permissions` claim is capped at 200 entries.

    Beyond that the token cannot prove a permission the user may well hold, and
    a 403 that said only "you do not have it" would send a developer looking at
    the role assignment rather than at the cap.
    """

    token = key.access_token(permissions=["a:b"], permissions_truncated=True)

    response = guarded()(rf.get("/invoices", headers={"Authorization": f"Bearer {token}"}))

    assert response.status_code == 403
    assert "truncated at 200 entries" in problem_of(response)["detail"]


def test_no_credential_is_401_and_not_403(rf: RequestFactory, jwks: JWKSEndpoint) -> None:
    """An unauthenticated caller is not a caller lacking a permission."""

    response = guarded()(rf.get("/invoices"))

    assert response.status_code == 401
    body = problem_of(response)
    assert body["type"] == "https://kleora.io/problems/unauthenticated"
    assert body["detail"] == "the request could not be authenticated"
    assert response["WWW-Authenticate"] == "Bearer"


def test_a_bad_token_is_401_and_says_nothing_about_why(
    rf: RequestFactory, key: SigningKey, jwks: JWKSEndpoint
) -> None:
    token = key.access_token(lifetime=-3600)

    response = guarded()(rf.get("/invoices", headers={"Authorization": f"Bearer {token}"}))

    assert response.status_code == 401
    assert problem_of(response)["detail"] == "the request could not be authenticated"


def test_an_unreachable_issuer_is_503(
    rf: RequestFactory, key: SigningKey, unreachable_jwks: JWKSEndpoint
) -> None:
    response = guarded()(
        rf.get("/invoices", headers={"Authorization": f"Bearer {key.access_token()}"})
    )

    assert response.status_code == 503
    body = problem_of(response)
    assert body["type"] == "https://kleora.io/problems/issuer-unavailable"
    assert "WWW-Authenticate" not in response


def test_a_route_that_forgot_the_middleware_is_401_and_not_a_crash(
    rf: RequestFactory, key: SigningKey, jwks: JWKSEndpoint
) -> None:
    """`request.kleora` missing entirely reads the same as `None`, by design."""

    @requires_permission("invoices:read")
    def view(request: HttpRequest) -> HttpResponse:  # pragma: no cover - must not run
        raise AssertionError("the view must not be reached")

    assert view(rf.get("/invoices")).status_code == 401


def test_the_decorator_keeps_the_views_own_parameters(
    rf: RequestFactory, key: SigningKey, jwks: JWKSEndpoint
) -> None:
    """`functools.wraps` is not cosmetic here — django-ninja reads the signature."""

    api = NinjaAPI(urls_namespace="deco-params", auth=KleoraAuthentication())

    @api.get("/invoices/{invoice_id}")
    @requires_permission("invoices:read")
    def one(request: HttpRequest, invoice_id: int, tail: str = "z") -> dict[str, Any]:
        return {"invoice_id": invoice_id, "tail": tail}

    response = TestClient(api).get("/invoices/7?tail=q", headers=bearer(key.access_token()))

    assert response.status_code == 200
    assert response.json() == {"invoice_id": 7, "tail": "q"}


def test_on_a_ninja_operation_the_403_is_still_a_problem_document(
    key: SigningKey, jwks: JWKSEndpoint
) -> None:
    """django-ninja returns an `HttpResponse` a handler produced, unchanged.

    That is what lets one decorator serve a plain view and a ninja operation
    with one implementation and one error shape.
    """

    api = NinjaAPI(urls_namespace="deco-ninja", auth=KleoraAuthentication())

    @api.get("/invoices")
    @requires_permission("invoices:read")
    def invoices(request: HttpRequest) -> dict[str, Any]:
        return {"tenant": request.kleora.tenant}  # type: ignore[attr-defined]

    client = TestClient(api)
    ok = client.get("/invoices", headers=bearer(key.access_token()))
    assert ok.status_code == 200
    assert ok.json() == {"tenant": TENANT}

    refused = client.get(
        "/invoices", headers=bearer(key.access_token(permissions=["something:else"]))
    )
    assert refused.status_code == 403
    assert (
        json.loads(refused.content)["type"] == "https://kleora.io/problems/insufficient-permission"
    )
