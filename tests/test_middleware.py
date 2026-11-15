"""`KleoraAuthMiddleware`: `request.kleora` on everything, refusal on nothing.

The contract — "sets `request.kleora` (`Claims` or `None`), never rejects by
itself" — is two assertions, and the
second one is the one worth guarding: middleware runs in front of the health
check, the admin and every public page a project serves, so a middleware that
answered 401 would take all of them with it.
"""

from __future__ import annotations

import logging

import pytest
from django.http import HttpRequest, HttpResponse
from django.test import RequestFactory
from kleora import Claims, TokenError

from django_kleora import KleoraAuthMiddleware
from tests.conftest import JWKSEndpoint, SigningKey


def seen() -> tuple[KleoraAuthMiddleware, list[HttpRequest]]:
    """The middleware, plus the requests that reached the view behind it."""

    arrived: list[HttpRequest] = []

    def view(request: HttpRequest) -> HttpResponse:
        arrived.append(request)
        return HttpResponse("ok")

    return KleoraAuthMiddleware(view), arrived


def test_a_verifying_token_becomes_request_kleora(
    rf: RequestFactory, key: SigningKey, jwks: JWKSEndpoint
) -> None:
    middleware, arrived = seen()

    response = middleware(
        rf.get("/anything", headers={"Authorization": f"Bearer {key.access_token()}"})
    )

    assert response.status_code == 200
    assert len(arrived) == 1
    claims = arrived[0].kleora  # type: ignore[attr-defined]
    assert isinstance(claims, Claims)
    assert claims.tenant_slug == "acme"
    assert arrived[0].kleora_error is None  # type: ignore[attr-defined]


def test_an_anonymous_request_passes_through_with_none(
    rf: RequestFactory, jwks: JWKSEndpoint
) -> None:
    middleware, arrived = seen()

    response = middleware(rf.get("/health"))

    assert response.status_code == 200
    assert arrived[0].kleora is None  # type: ignore[attr-defined]
    assert arrived[0].kleora_error is None  # type: ignore[attr-defined]
    assert jwks.fetches == 0


def test_a_bad_token_passes_through_too_and_records_why(
    rf: RequestFactory, key: SigningKey, jwks: JWKSEndpoint
) -> None:
    """Never rejects: the refusal is `requires_permission`'s job, or the view's."""

    middleware, arrived = seen()

    response = middleware(
        rf.get("/anything", headers={"Authorization": f"Bearer {key.access_token(lifetime=-3600)}"})
    )

    assert response.status_code == 200, "the middleware must not answer for the view"
    assert arrived[0].kleora is None  # type: ignore[attr-defined]
    error = arrived[0].kleora_error  # type: ignore[attr-defined]
    assert isinstance(error, TokenError)
    assert error.code == "expired"


def test_an_unreachable_issuer_is_recorded_rather_than_answered(
    rf: RequestFactory, key: SigningKey, unreachable_jwks: JWKSEndpoint
) -> None:
    middleware, arrived = seen()

    response = middleware(
        rf.get("/anything", headers={"Authorization": f"Bearer {key.access_token()}"})
    )

    assert response.status_code == 200
    error = arrived[0].kleora_error  # type: ignore[attr-defined]
    assert isinstance(error, TokenError)
    assert error.code == "issuer_unavailable"


def test_the_reason_goes_to_the_log_and_not_to_the_caller(
    rf: RequestFactory,
    key: SigningKey,
    jwks: JWKSEndpoint,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Middleware failure mapping: 401 for the caller's problem, 503 for the issuer's.

    The 401 body says only that the request was not authenticated; the reason
    still has to reach somebody, so it reaches the package's own logger under
    its own name — `django_kleora`, which is what a customer puts in
    `LOGGING`, not the private module it happened to be raised in.
    """

    middleware, _ = seen()

    with caplog.at_level(logging.WARNING, logger="django_kleora"):
        middleware(
            rf.get(
                "/anything",
                headers={"Authorization": f"Bearer {key.access_token(lifetime=-3600)}"},
            )
        )

    assert [record.name for record in caplog.records] == ["django_kleora"]
    assert "expired" in caplog.text
