"""`@requires_permission` — one permission, three answers.

```python
@api.get("/invoices")
@requires_permission("invoices:read")
def invoices(request):
    return {"tenant": request.kleora.tenant}
```

Works on a django-ninja operation (as above — django-ninja returns an
`HttpResponse` a handler produces unchanged) and on a plain Django view. On a
ninja operation it goes **under** the route decorator, which is what the
quickstart shows: `@api.get` registers whatever it is given, so the permission
check has to be the thing registered.

The answers, and why three rather than two:

| The request | Answer |
| --- | --- |
| Carries the permission | the view runs |
| Carries a token without it | 403 `insufficient-permission`, naming it |
| Carries no verified token | 401 `unauthenticated` |
| Reached us with the issuer unreachable | 503 `issuer-unavailable` |

A request with no `request.kleora` is 401 and not 403: an unauthenticated
caller is not a caller lacking a permission, and a route that forgot the
middleware must not read as a permissions problem. The same rule, and the same
sentence, as `@kleora-io/node`'s `requirePermission`.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar, cast

from django.http import HttpRequest

from ._verify import is_issuer_unavailable, kleora_error_of, kleora_of
from .problems import ISSUER_UNAVAILABLE, UNAUTHENTICATED, problem

View = TypeVar("View", bound=Callable[..., Any])

TRUNCATED = (
    "the token does not carry the permission {name!r}. Its permissions claim was "
    "truncated at 200 entries, so this may be a permission the user does hold but "
    "the token could not carry; coarser roles are the fix."
)
MISSING = "the token does not carry the permission {name!r}"


def requires_permission(name: str) -> Callable[[View], View]:
    """Refuse a request whose `Claims` do not carry `name`.

    The permission string is the one Kleora mints into the `permissions`
    claim — `"invoices:read"` — and the check is exact-match membership, not a
    prefix or a wildcard. A token whose `permissions` were truncated is still
    refused, but the 403 says so, because the honest statement is that this
    token cannot prove the permission rather than that the user lacks it.
    """

    def decorate(view: View) -> View:
        @wraps(view)
        def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> Any:
            claims = kleora_of(request)
            if claims is None:
                error = kleora_error_of(request)
                if is_issuer_unavailable(error):
                    return problem("issuer-unavailable", 503, ISSUER_UNAVAILABLE)
                return problem("unauthenticated", 401, UNAUTHENTICATED)
            if name not in claims.permissions:
                template = TRUNCATED if claims.permissions_truncated else MISSING
                return problem("insufficient-permission", 403, template.format(name=name))
            return view(request, *args, **kwargs)

        # `wraps` copies `__wrapped__`, which is what makes `inspect.signature`
        # — and therefore django-ninja's parameter resolution — read the view's
        # own signature rather than this `(request, *args, **kwargs)`. Without
        # it a ninja operation would lose every path and query parameter.
        return cast(View, wrapper)

    return decorate
