"""`install_problem_handlers(api)` — the two refusals django-ninja writes for us.

```python
from ninja import NinjaAPI
from django_kleora import KleoraAuthentication, install_problem_handlers

api = install_problem_handlers(NinjaAPI(auth=KleoraAuthentication()))
```

Everything this platform refuses is an RFC 9457 problem document (see
https://kleora.io/problems/unauthenticated and its siblings), and everything
*this package* writes is — `requires_permission`'s 401, 403 and 503 all come out of
`django_kleora.problems`. Two refusals were the exception, because
django-ninja writes them rather than us:

* **A token that does not verify.** ninja raises `AuthenticationError`, and its
  own handler answers `{"detail": "Unauthorized"}` at `application/json`. With
  this call: 401 `unauthenticated`, at `application/problem+json`, with
  `WWW-Authenticate: Bearer`.
* **An issuer whose key set cannot be read.** `KleoraAuthentication` raises
  `IssuerUnavailable`, an `HttpError`, so ninja answers `{"detail": …}` at 503.
  With this call: 503 `issuer-unavailable`, at `application/problem+json`.

The second of those could be written as three lines of a customer's own code,
but that version produces the right *body* and the wrong media type —
`api.create_response()` renders through the API's renderer, whose `media_type`
is `application/json` — so a client selecting on `application/problem+json`
sees a document it has been told not to look at. One call does both, and
they go through the same `problems.problem()` the decorator uses, so the four
documents this package can write are one shape.

**The two statuses stay two.** A bad token is the caller's problem and an
issuer that cannot be read is the provider's. Answering 401 to both tells
every client to throw away a perfectly good token because our provider is down.

## Why this is a call you make and not something the package does for you

We looked for a hook that would let the package install these itself, reading
django-ninja 1.6.3 for one. There is none, and the
reason is structural rather than an omission:

* **The registry is per instance and private.** `NinjaAPI.__init__` creates
  `self._exception_handlers` and immediately fills it from
  `ninja.errors.set_default_exc_handlers(self)`. There is no class-level
  registry, no `NINJA_*` setting for it (`ninja/conf.py` carries pagination,
  throttling and file-method keys and nothing else), and no argument to
  `NinjaAPI(...)` that takes handlers.
* **An auth class never learns which API it was attached to.** ninja calls the
  callback as `callback(request)` from `Operation._run_authentication`, which
  holds `self.api` and passes none of it. Nothing on the request carries a
  handle either: the only attributes ninja sets are `request.auth` and
  `request._ninja_csrf_exempt`. The API is reachable from
  `request.resolver_match.func.__closure__` — the view is a closure over the
  `PathView` — and reading a third-party function's closure cells by position
  is a thing that breaks silently on somebody else's refactor, which is worse
  than a documented call.
* **`AppConfig.ready()` has nothing to enumerate.** ninja used to keep
  `NinjaAPI._registry`; in 1.6.3 it is gone and `_validate()` is `pass`
  ("Registry check no longer needed"). Even with a registry, `ready()` runs
  while the app registry is being populated and a project's `api.py` is
  normally imported later still, with the URLconf — so an `AppConfig` would be
  looking at an empty list in the common case.

Two mechanisms *would* work and were rejected as judgements, not as
impossibilities:

* **Monkeypatching `NinjaAPI.set_default_exception_handlers`** from
  `AppConfig.ready()`. It would work — and it would change the refusal shape
  of every `NinjaAPI` in the process, including ones with a different auth
  class that have nothing to do with Kleora. A vendor SDK that quietly
  rewrites another library's responses process-wide is worse than a call you
  can read. It is also order-dependent: an API constructed before `ready()`
  (an `api.py` imported from `settings.py`, or from an earlier app's `ready()`)
  gets nothing, and "automatic, usually" is the worst of the three states.
* **Rewriting the response in `KleoraAuthMiddleware`.** Also possible, and it
  would have to decide whether a 401 it is looking at is ninja's default or one
  the application chose — by matching ninja's default body, which changes
  between versions without telling anybody. It would also override a handler
  the application registered itself, and answer outside the `NinjaAPI`, so the
  one shape it produced would not be the shape that API produces for anything
  else.

So the call stays a call, and `requires_permission` needs none of this: a
handler this package registers can be replaced by one the application
registers afterwards, because `add_exception_handler` is a dict assignment and
the last writer wins. That is deliberate — the application's own decision about
its own API outranks ours.

## What it does not touch

`AuthorizationError` (403) and `Throttled` (429) are ninja's other refusals.
Nothing in ninja raises the first, so a handler for it would only catch one an
application raised itself, and translating that into
`insufficient-permission` would be this package naming somebody else's refusal.
The second is raised by ninja's throttling from the application's own rate
configuration; `rate-limited` is Kleora's slug for Kleora's limits, and it
carries `Retry-After` and the `RateLimit-*` headers that a `Throttled` cannot
supply.
"""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from ninja import NinjaAPI
from ninja.errors import AuthenticationError

from .auth import IssuerUnavailable
from .problems import ISSUER_UNAVAILABLE, UNAUTHENTICATED, problem


def install_problem_handlers(api: NinjaAPI) -> NinjaAPI:
    """Make `api` answer django-ninja's two auth refusals with problem documents.

    Returns `api`, so it can wrap the construction in one expression. Calling it
    twice is harmless: each call assigns the same two entries.
    """

    def unauthenticated(
        request: HttpRequest, exc: AuthenticationError | type[AuthenticationError]
    ) -> HttpResponse:
        """401 `unauthenticated` — the slug Kleora's APIs give that status.

        The body says only that the request was not authenticated. An expired
        token and one signed by a key we have never seen get the same sentence:
        the difference is of no use to a caller that does not already hold a
        valid credential, and of every use to one probing. The reason is logged
        by `django_kleora._verify`.
        """

        if isinstance(exc, AuthenticationError) and exc.status_code != 401:
            # ninja raises this with 401 and nothing else does. An application
            # that raised it with another status has not said "unauthenticated",
            # and a 401 document carrying a 403 would be a worse answer than the
            # framework's own — so that one goes back to ninja's shape.
            return api.create_response(request, {"detail": str(exc)}, status=exc.status_code)
        return problem("unauthenticated", 401, UNAUTHENTICATED)

    def issuer_unavailable(
        request: HttpRequest, exc: IssuerUnavailable | type[IssuerUnavailable]
    ) -> HttpResponse:
        """503 `issuer-unavailable` — retryable, and not the caller's fault."""

        detail = exc.detail if isinstance(exc, IssuerUnavailable) else ISSUER_UNAVAILABLE
        return problem(IssuerUnavailable.slug, IssuerUnavailable.status, detail)

    api.add_exception_handler(AuthenticationError, unauthenticated)
    api.add_exception_handler(IssuerUnavailable, issuer_unavailable)
    return api
