"""The Kleora Django integration.

Four things, over [`kleora`](https://pypi.org/project/kleora/):

* **`KleoraAuthentication`** — a django-ninja auth class. Verifies the bearer
  token, returns `Claims`, sets `request.kleora`.
* **`KleoraAuthMiddleware`** — the same for views django-ninja never sees. Sets
  `request.kleora` to `Claims` or `None` and never refuses a request itself.
* **`requires_permission("invoices:read")`** — a view decorator: 403 when the
  token lacks the permission, 401 when there is no verified token at all.
* **`settings.KLEORA`** — the four keys `django_kleora.conf` documents,
  checked by `manage.py check`.

Plus `account_portal_url(client_id=…)`, the hosted account portal's URL on
`KLEORA["ISSUER"]`, offered only for a Client that lists
`self_service` in `allowed_scopes`.

And one call, `install_problem_handlers(api)`, because two of the refusals on a
`NinjaAPI` are written by django-ninja rather than by us and are the only
answers this package can produce that are not RFC 9457 problem documents.
`django_kleora.handlers` records what was searched for a way to install
them without being asked, and what in django-ninja 1.6.3 prevents it.

**Nothing here verifies a token or classifies an issuer itself.** All of that is
`kleora`'s — the JWKS cache, the eight `TokenError` codes, the sandbox
rule (a host is sandbox when its first DNS label ends in `-sandbox`) and
the environment guard. A second implementation would drift from the first within
a release, and the copy that drifted would be the one on a customer's request
path. So this package is glue, and the glue is the whole of it.

The error taxonomy is imported rather than redeclared, because two copies of
one exception class make `except` lie. `django-kleora` is not a
peer of `kleora`, it is built on it, so it raises `kleora`'s
classes and adds exactly two of its own — `ConfigurationError`, for a `KLEORA`
dict it cannot use, and `IssuerUnavailable`, which django-ninja needs to be an
`HttpError` before it will answer 503 with it.
"""

from ._meta import __version__
from .auth import IssuerUnavailable, KleoraAuthentication
from .decorators import requires_permission
from .errors import ConfigurationError
from .handlers import install_problem_handlers
from .management import get_management_client
from .middleware import KleoraAuthMiddleware
from .portal import account_portal_url

__all__ = [
    "ConfigurationError",
    "IssuerUnavailable",
    "KleoraAuthMiddleware",
    "KleoraAuthentication",
    "__version__",
    "account_portal_url",
    "get_management_client",
    "install_problem_handlers",
    "requires_permission",
]
