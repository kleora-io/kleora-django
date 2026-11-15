"""`KleoraAuthMiddleware` — `request.kleora` for views django-ninja never sees.

```python
MIDDLEWARE = [
    # …
    "django_kleora.KleoraAuthMiddleware",
]
```

It sets `request.kleora` to the verified `Claims` or to `None`, and
`request.kleora_error` to why, and it **never rejects a request by itself**.
That is deliberate and it is the whole
difference between this and the django-ninja auth class: middleware runs in
front of everything, including the health check, the admin, the login page and
every unauthenticated page a Django project serves. Middleware that answered
401 would take all of them with it.

Refusing is the job of what comes after — `requires_permission`, or a view's own
`if request.kleora is None`. The reason for a refusal is logged here, where it
happened, and is never in the response.

There is one asymmetry with the auth class worth knowing: an unreachable issuer
is recorded rather than answered, because answering is what this middleware does
not do. `requires_permission` reads it back and answers 503; a view that reads
`request.kleora` itself and finds `None` should consult
`request.kleora_error` before deciding that its caller is anonymous.
"""

from __future__ import annotations

from collections.abc import Callable

from django.http import HttpRequest, HttpResponseBase

from ._verify import authenticate, bearer_token


class KleoraAuthMiddleware:
    """Put the verified `Claims` on every request, and never refuse one.

    A new-style Django middleware: constructed once per worker with the next
    callable, called once per request. It holds no per-request state, so one
    instance serves every thread.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponseBase]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponseBase:
        authenticate(request, bearer_token(request))
        return self.get_response(request)
