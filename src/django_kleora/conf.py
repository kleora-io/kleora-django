"""The `KLEORA` setting: reading it, validating it, and forgetting it again.

```python
KLEORA = {
    "ISSUER": "https://acme-sandbox.kleora.eu",
    "AUDIENCE": "https://api.acme.example",
    "API_KEY": env("KLEORA_API_KEY"),        # optional
    "API_BASE": "https://api.kleora.io/api/v1",
}
```

Four keys. `ISSUER` and
`AUDIENCE` are what the verifier needs and are required; `API_KEY` is what
`get_management_client()` needs and is optional, because verifying tokens and
administering the platform are separate jobs and most services only do the
first; `API_BASE` defaults to the public management API.

The dict is read once and cached, and the cache is dropped whenever Django says
a setting changed — which is what makes `override_settings` work in a test suite
and `manage.py` reload work in development. Nothing here reads an environment
variable: a credential arrives through the settings a project already controls,
never from behind the caller's back.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from django.conf import settings as django_settings
from django.core.signals import setting_changed
from django.dispatch import receiver
from kleora import EnvironmentKind, classify_issuer
from kleora.management import DEFAULT_BASE_URL

from .errors import ConfigurationError

SETTING = "KLEORA"
"""The name of the settings dict, in one place because three modules name it."""

ISSUER = "ISSUER"
AUDIENCE = "AUDIENCE"
API_KEY = "API_KEY"
API_BASE = "API_BASE"

KEYS = (ISSUER, AUDIENCE, API_KEY, API_BASE)
"""Every key this package reads. Anything else in the dict is a typo."""


@dataclass(frozen=True, slots=True)
class KleoraSettings:
    """A validated `KLEORA`.

    Frozen for the same reason `Claims` is: it is read on every request by the
    auth class and the middleware, and a value one request mutated would be a
    value every later request on that worker inherited.
    """

    issuer: str
    audience: str
    api_key: str | None
    api_base: str

    @property
    def kind(self) -> EnvironmentKind:
        """What the issuer says this configuration is — `production` or `sandbox`."""

        return classify_issuer(self.issuer)


_cached: KleoraSettings | None = None


def get_settings() -> KleoraSettings:
    """The validated `KLEORA` dict, read once per process.

    Raises `ConfigurationError` — which is both a `KleoraError` and Django's
    `ImproperlyConfigured` — for anything it cannot use. The same conditions are
    reported by `manage.py check` without raising, so a misconfigured project is
    told at startup rather than on its first request; this is the enforcement
    behind that report, for the projects that never run the checks.
    """

    global _cached
    if _cached is None:
        _cached = _read(getattr(django_settings, SETTING, None))
    return _cached


def _read(raw: object) -> KleoraSettings:
    if raw is None:
        raise ConfigurationError(
            f"settings.{SETTING} is not set. django-kleora needs at least "
            f"{SETTING} = {{'{ISSUER}': ..., '{AUDIENCE}': ...}}"
        )
    if not isinstance(raw, dict):
        raise ConfigurationError(f"settings.{SETTING} must be a dict, not {type(raw).__name__}")

    values: dict[str, Any] = dict(raw)
    issuer = _required_text(values, ISSUER)
    audience = _required_text(values, AUDIENCE)
    _assert_absolute(issuer)

    api_key = _optional_text(values, API_KEY)
    api_base = _optional_text(values, API_BASE) or DEFAULT_BASE_URL
    _assert_absolute(api_base, key=API_BASE)

    return KleoraSettings(
        issuer=issuer.rstrip("/"),
        audience=audience,
        api_key=api_key,
        api_base=api_base,
    )


def _required_text(values: dict[str, Any], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(
            f"settings.{SETTING}['{key}'] must be a non-empty string; it is {value!r}"
        )
    return value.strip()


def _optional_text(values: dict[str, Any], key: str) -> str | None:
    value = values.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if not isinstance(value, str):
        raise ConfigurationError(
            f"settings.{SETTING}['{key}'] must be a string or absent; it is {value!r}"
        )
    return value.strip()


def _assert_absolute(value: str, *, key: str = ISSUER) -> None:
    """An issuer compares by exact string, so it has to be one that can be fetched.

    An access token's `iss` is the environment's issuer, exactly. A relative or
    scheme-less value can never equal one, so it would fail every verification
    with `issuer_mismatch` — a message about the token, for a mistake in the
    settings.
    """

    split = urlsplit(value)
    if split.scheme not in {"http", "https"} or not split.netloc:
        raise ConfigurationError(
            f"settings.{SETTING}['{key}'] must be an absolute http(s) URL; it is {value!r}"
        )


@receiver(setting_changed)
def _reset(*, setting: str, **_: object) -> None:
    """Drop the cache when the setting it was read from moves.

    `override_settings` and `modify_settings` send this, so a test that changes
    `KLEORA` gets the new value; so does nothing else in production, where
    settings do not change after startup. `get_management_client` listens for
    the same signal, because a client built from the old dict is as stale as the
    dict.
    """

    if setting == SETTING:
        global _cached
        _cached = None
