"""Reading the bearer token off a request and turning it into `Claims`.

One implementation, used by both surfaces: `KleoraAuthentication` (django-ninja)
and `KleoraAuthMiddleware` (everything else). Neither verifies anything itself
— `kleora.verify_access_token` does, over the JWKS cache it shares per
issuer per process — because a second verifier would drift from the first within
a release, and the one that drifted would be the one on a customer's request
path.

The three outcomes are deliberately three, exactly as `@kleora-io/node`'s
middlewares make them:

| Cause | The verdict | The answer |
| --- | --- | --- |
| A token that verifies | the `Claims` | the view runs |
| No credential, or one that fails | the `KleoraError`, or nothing | 401 `unauthenticated` |
| The JWKS could not be read | `TokenError('issuer_unavailable')` | 503 `issuer-unavailable` |

Collapsing the last two — which is what answering 401 to both does — makes an
outage look to an operator like a fleet of bad credentials, and tells every
client to discard its token and re-authenticate against an issuer that is
already down. That is why the two are separate codes.

A configuration this package cannot use is **not** one of the three. It is not
about the request, it is not retryable, and this package does not get to choose
a status for it: `ConfigurationError` propagates, and the application's own
handler answers — a 500 in Django's default, which is the correct answer to a
service that cannot verify anything for anybody.
"""

from __future__ import annotations

import logging

from django.http import HttpRequest
from kleora import (
    Claims,
    EnvironmentMismatch,
    KleoraError,
    TokenError,
    verify_access_token,
)

from .conf import get_settings

logger = logging.getLogger("django_kleora")
"""Where a refusal's reason goes, since it does not go to the caller.

`logging.getLogger(__name__)` would be `django_kleora._verify`, which is
a private module name in a customer's `LOGGING` dict. The package's own name is
the handle a customer configures.
"""

HEADER = "Authorization"
SCHEME = "bearer"

KLEORA_ATTR = "kleora"
KLEORA_ERROR_ATTR = "kleora_error"


def bearer_token(request: HttpRequest) -> str | None:
    """The credential in `Authorization: Bearer <token>`, or `None`.

    `None` for a missing header, an empty one, and any other scheme — a request
    carrying `Basic` credentials is an unauthenticated request as far as this
    package is concerned, not a malformed token, and saying otherwise would turn
    somebody else's authentication into our 401.
    """

    value = request.headers.get(HEADER, "")
    scheme, _, token = value.partition(" ")
    if scheme.lower() != SCHEME:
        return None
    token = token.strip()
    return token or None


def claims_for(token: str) -> Claims:
    """Verify `token` against the configured issuer and audience.

    Raises `TokenError` for anything about the token, `EnvironmentMismatch` for
    a token minted by the other environment, and `ConfigurationError` when the
    settings cannot be used.
    """

    configuration = get_settings()
    return verify_access_token(
        token,
        issuer=configuration.issuer,
        audience=configuration.audience,
    )


def authenticate(
    request: HttpRequest, token: str | None
) -> tuple[Claims | None, KleoraError | None]:
    """`(claims, None)` for a token that verifies, `(None, error)` otherwise.

    `token` is `None` when there was no credential at all, which is
    `(None, None)`: nothing failed, nobody was presented. The caller decides
    whether an anonymous request is allowed — the middleware always allows it,
    the django-ninja auth class never does.
    """

    if token is None:
        _record(request, None, None)
        return None, None

    try:
        claims = claims_for(token)
    except (TokenError, EnvironmentMismatch) as error:
        # The reason reaches a log and not the caller: the difference between
        # "expired" and "signed by a key we have never seen" is of no use to
        # somebody who does not already hold a valid token, and of every use to
        # somebody probing.
        logger.warning("kleora: refusing a request: %s", error)
        _record(request, None, error)
        return None, error

    _record(request, claims, None)
    return claims, None


def is_issuer_unavailable(error: KleoraError | None) -> bool:
    """Whether `error` is the one failure that is ours rather than the caller's."""

    return isinstance(error, TokenError) and error.code == "issuer_unavailable"


def _record(request: HttpRequest, claims: Claims | None, error: KleoraError | None) -> None:
    """Put the verdict on the request, where a view and the decorator read it.

    `setattr` rather than `request.kleora = …` because `HttpRequest` declares
    neither attribute; the two readers below are what keeps the types honest
    from there on.
    """

    setattr(request, KLEORA_ATTR, claims)
    setattr(request, KLEORA_ERROR_ATTR, error)


def kleora_of(request: HttpRequest) -> Claims | None:
    """`request.kleora`, or `None` on a request no surface of ours has seen."""

    value = getattr(request, KLEORA_ATTR, None)
    return value if isinstance(value, Claims) else None


def kleora_error_of(request: HttpRequest) -> KleoraError | None:
    """`request.kleora_error` — why `request.kleora` is `None`, when it is."""

    value = getattr(request, KLEORA_ERROR_ATTR, None)
    return value if isinstance(value, KleoraError) else None
