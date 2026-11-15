"""The `AppConfig`, which exists for the system checks and nothing else.

```python
INSTALLED_APPS = [
    # …
    "django_kleora",
]
```

This package has no models, no migrations, no templates, no URLs and no admin.
The `INSTALLED_APPS` entry buys one thing: `django_kleora.checks` is
imported, so `manage.py check` reports a `KLEORA` dict it cannot use —
including a `kl_test_` key configured against a production issuer — before the
process serves anything.

Everything else works without it. `KleoraAuthentication`,
`KleoraAuthMiddleware` and `requires_permission` read `settings.KLEORA`
directly and do not consult the app registry, so a project that installs the
middleware and forgets this line is correct but unchecked. That is the wrong
trade and the README says so, but it is not a failure.
"""

from __future__ import annotations

from django.apps import AppConfig


class KleoraConfig(AppConfig):
    """Kleora's Django integration.

    `label` is `kleora` rather than the default `django_kleora`
    because a label is what `INSTALLED_APPS` collisions are detected on and what
    a `manage.py` command takes as an argument; the shorter one is the name this
    package is known by.
    """

    name = "django_kleora"
    label = "kleora"
    verbose_name = "Kleora"

    def ready(self) -> None:
        """Import the modules whose side effect is a registration.

        `checks` registers the system check; `conf` and `management` connect the
        `setting_changed` receivers that drop their caches. All three are
        imported here rather than at package import so that installing the
        package into a project is inert until Django says the app registry is
        being populated.
        """

        from . import checks, conf, management  # noqa: F401
