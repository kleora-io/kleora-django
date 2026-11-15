"""`KleoraAuthentication` — the django-ninja auth class.

```python
from ninja import NinjaAPI
from django_kleora import KleoraAuthentication

api = NinjaAPI(auth=KleoraAuthentication())
```

Every operation on that `NinjaAPI` then requires a Kleora access token, and
every handler can read `request.kleora`. django-ninja also puts the same
`Claims` on `request.auth`, which is its own convention; both are the same
object.

**What the refusals look like, and the one place this package speaks somebody
else's dialect.** A token that does not verify is django-ninja's own 401 —
`{"detail": "Unauthorized"}` — because `HttpBearer` decides that, not us: an
auth class says yes or no, and the framework writes the answer. An issuer that
cannot be reached is `IssuerUnavailable`, a `ninja.errors.HttpError` subclass, so
django-ninja answers **503** rather than telling a caller with a perfectly good
token to go and get another one from a provider that is down.

`requires_permission`, by contrast, writes RFC 9457 problem documents, because
there the response is ours to write. One call brings the two refusals above into
the same shape:

```python
from django_kleora import KleoraAuthentication, install_problem_handlers

api = install_problem_handlers(NinjaAPI(auth=KleoraAuthentication()))
```

**It is a call rather than something this package arranges by itself**, and not
for want of looking: an auth class never sees the `NinjaAPI` it was handed to,
and django-ninja keeps its exception handlers in a private per-instance dict with
no class-level registry, no setting and no constructor argument.
`django_kleora.handlers` is where that search is written down, including
the two mechanisms that would work and what they would cost.
"""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest
from kleora import Claims
from ninja.errors import HttpError
from ninja.security import HttpBearer

from ._verify import authenticate, bearer_token, is_issuer_unavailable
from .problems import ISSUER_UNAVAILABLE, PROBLEM_BASE, TITLES


class IssuerUnavailable(HttpError):
    """503: the issuer's key set could not be read, so nothing could be judged.

    A `ninja.errors.HttpError` so that django-ninja's own handler answers it
    without the application registering anything. `problem()` is here for the
    applications that would rather answer an RFC 9457 document, which is what
    the rest of this package writes.
    """

    slug = "issuer-unavailable"
    status = 503

    def __init__(self, detail: str = ISSUER_UNAVAILABLE) -> None:
        super().__init__(self.status, detail)
        self.detail = detail

    def problem(self) -> dict[str, Any]:
        """This refusal as the problem document `requires_permission` would write."""

        return {
            "type": f"{PROBLEM_BASE}{self.slug}",
            "title": TITLES[self.slug],
            "status": self.status,
            "detail": self.detail,
        }


class KleoraAuthentication(HttpBearer):
    """Verify the bearer token, return `Claims`, and set `request.kleora`.

    Attach it to a whole API (`NinjaAPI(auth=KleoraAuthentication())`), to a
    router, or to one operation — django-ninja treats all three the same.

    The instance is shared by every request on the worker and holds no state:
    the configuration is read from `settings.KLEORA` and the keys come from
    the process-wide JWKS cache, so two threads verifying at once make one
    request to the issuer between them, not two.
    """

    def __call__(self, request: HttpRequest) -> Claims | None:
        """Set `request.kleora` even when there is no credential to verify.

        `HttpBearer.__call__` returns before `authenticate` for a request with
        no `Authorization` header, so without this a handler reached some other
        way — a second auth class, a route this one is not attached to — would
        find the attribute missing rather than `None`. Missing and `None` mean
        different things to `getattr`, and only one of them is true.
        """

        claims, error = authenticate(request, bearer_token(request))
        if is_issuer_unavailable(error):
            raise IssuerUnavailable
        return claims

    def authenticate(self, request: HttpRequest, token: str) -> Claims | None:
        """`HttpBearer`'s hook. Reached only when `__call__` is not overridden.

        It is overridden above — the whole decision is made there, because the
        503 has to be reachable for a request whose header `HttpBearer` parses
        and for one it does not. This stays because `HttpBearer` declares it
        abstract, and it is written to agree with `__call__` rather than to
        raise `NotImplementedError`: a subclass that calls `super().__call__()`
        deserves the documented behaviour, not a crash.
        """

        claims, error = authenticate(request, token)
        if is_issuer_unavailable(error):
            raise IssuerUnavailable
        return claims
