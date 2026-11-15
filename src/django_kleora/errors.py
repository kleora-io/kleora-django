"""This package's one error, and why it is two base classes at once.

Everything else in the taxonomy — `TokenError`, `EnvironmentMismatch`,
`ApiError`, `KleoraError` — is `kleora`'s and is re-exported from it
rather than redeclared here, for a reason: two copies of one exception class
in a dependency graph make `except` and `isinstance` lie, so a package
declares its own only when it is the only package that can raise it. This one is.

`ConfigurationError` is what a `KLEORA` setting this package cannot use
raises. It inherits from **both** `kleora.KleoraError` and Django's
`ImproperlyConfigured`, because both statements are true and a caller may
reasonably hold either belief:

* an application that wraps every Kleora failure catches `KleoraError`,
  and a configuration it cannot use is one of them;
* a Django application — and Django itself, in `manage.py` and in the ASGI/WSGI
  handlers — catches `ImproperlyConfigured` and prints it as a setup problem
  rather than a crash.

The alternative was to pick one and be wrong for half the callers.
"""

from __future__ import annotations

from django.core.exceptions import ImproperlyConfigured
from kleora import KleoraError


class ConfigurationError(KleoraError, ImproperlyConfigured):
    """A `KLEORA` setting that cannot be used.

    Raised at the point the setting is *read*, not at import: a check that
    fired at import would make the package impossible to install into a project
    before its settings exist, and `manage.py check` is where a Django
    application expects to be told (see `django_kleora.checks`).
    """
