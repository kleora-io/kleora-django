"""RFC 9457 problem documents, written rather than parsed.

The same three slugs, statuses, titles and details `@kleora-io/node`'s
middlewares write, under the same namespace the platform's own APIs use for
their errors. A customer who
puts Kleora in front of their Django API and their Express API gets one error
shape across both, and `insufficient-permission` means the same thing on either
side of the call.

**This is the shape `requires_permission` answers with, and — once
`install_problem_handlers(api)` has been called — the shape django-ninja's own
401 and the 503 carry too.** Without that call those two are the framework's
`{"detail": …}` at `application/json`; `django_kleora.handlers` says why
the call cannot install itself.
"""

from __future__ import annotations

from django.http import JsonResponse

PROBLEM_BASE = "https://kleora.io/problems/"
"""The namespace every Kleora problem type lives under; each slug is a page there."""

CONTENT_TYPE = "application/problem+json"

TITLES = {
    "unauthenticated": "Authentication required",
    "insufficient-permission": "Permission denied",
    "issuer-unavailable": "Identity provider unavailable",
}

UNAUTHENTICATED = "the request could not be authenticated"
"""The detail every 401 carries, whatever the reason was.

The same answer for an absent header as for an expired token: the difference is
of no use to a caller that does not already hold a valid token, and of every use
to one probing. The reason goes to the logger instead
(`django_kleora.middleware`).
"""

ISSUER_UNAVAILABLE = "the identity provider could not be reached to verify this token"


def problem(slug: str, status: int, detail: str) -> JsonResponse:
    """The problem response for one slug.

    `WWW-Authenticate` on a 401 is RFC 6750 §3, and Kleora's APIs send it too:
    a client that cannot tell "no credential" from "wrong credential" without it
    retries the wrong thing.
    """

    response = JsonResponse(
        {
            "type": f"{PROBLEM_BASE}{slug}",
            "title": TITLES.get(slug, slug),
            "status": status,
            "detail": detail,
        },
        status=status,
        content_type=CONTENT_TYPE,
    )
    if status == 401:
        response["WWW-Authenticate"] = "Bearer"
    return response
