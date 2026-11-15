"""Django system checks over `settings.KLEORA`, run by `manage.py check`.

Registered when `"django_kleora"` is in `INSTALLED_APPS`, which is the
only reason the package needs to be there at all — nothing else in it is a
Django app: no models, no migrations, no templates, no URLs.

The check that earns its place is `kleora.E003`: a `kl_test_` key configured
against a production issuer, or the reverse. Both halves of that are in the settings, so
it can be decided with no network call and reported before the process serves
anything. The alternative is finding out on the first administrative request, in
production, from an `EnvironmentMismatch` in a traceback.

`manage.py check` runs on `runserver`, on every `manage.py` command that is not
marked otherwise, and is what a deployment pipeline is expected to call. It does
not run on a WSGI or ASGI worker's startup path, so these are a report and not
an enforcement; `get_settings()` and `get_management_client()` raise the same
conditions where they are read.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings as django_settings
from django.core.checks import CheckMessage, Error, Warning, register
from kleora import KleoraError, classify_api_key

from .conf import API_KEY, KEYS, SETTING, get_settings
from .errors import ConfigurationError

README_SETTINGS = "https://github.com/kleora-io/kleora-django#settings"
"""Where the `KLEORA` setting is documented, for a check's hint."""

PREFIXES = {"production": "kl_live_", "sandbox": "kl_test_"}
"""What a message may show of a key: the literal prefix and nothing random.

The console may display a key's stored prefix — the literal plus eight random
characters — but a check message reaches a deployment log
that nobody chose to hold a credential, so this is derived from the *kind* and
never sliced out of the key itself.
"""


@register()
def check_kleora_settings(app_configs: Any = None, **kwargs: Any) -> list[CheckMessage]:
    """Everything about `settings.KLEORA` that can be decided without a request."""

    try:
        configuration = get_settings()
    except ConfigurationError as error:
        return [
            Error(
                str(error),
                hint=f"See {README_SETTINGS} for the shape of {SETTING}.",
                id="kleora.E001",
            )
        ]

    messages: list[CheckMessage] = []
    messages.extend(_unknown_keys())

    if configuration.api_key is None:
        return messages

    try:
        key_kind = classify_api_key(configuration.api_key)
    except KleoraError as error:
        return [
            *messages,
            Error(
                f"settings.{SETTING}['{API_KEY}'] {error}",
                hint="Kleora API keys start with 'kl_live_' or 'kl_test_'.",
                id="kleora.E002",
            ),
        ]

    issuer_kind = configuration.kind
    if key_kind != issuer_kind:
        messages.append(
            Error(
                f"settings.{SETTING}['{API_KEY}'] is a {key_kind} key "
                f"({PREFIXES[key_kind]}…) but {configuration.issuer} is a "
                f"{issuer_kind} issuer.",
                hint=(
                    "A sandbox credential must not reach a production environment or the "
                    "reverse. Configure the key that belongs to this issuer."
                ),
                id="kleora.E003",
            )
        )

    return messages


def _unknown_keys() -> list[CheckMessage]:
    """A warning, not an error, for a key this package does not read.

    A typo (`AUDIANCE`) and a deliberate extra of the project's own look
    identical from here, and refusing to start over the second would be this
    package deciding what may be in somebody else's settings dict. Naming it is
    enough: the typo is obvious once it is printed next to the keys that are
    read.
    """

    raw = getattr(django_settings, SETTING, None)
    if not isinstance(raw, dict):
        return []
    unknown = sorted(str(key) for key in raw if key not in KEYS)
    if not unknown:
        return []
    return [
        Warning(
            f"settings.{SETTING} carries {', '.join(unknown)}, which django-kleora does not read.",
            hint=f"The keys it reads are {', '.join(KEYS)}.",
            id="kleora.W001",
        )
    ]
