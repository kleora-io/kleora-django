"""The Django settings the suite and `mypy` both run against.

One module, used twice. `tests/conftest.py` points `DJANGO_SETTINGS_MODULE` at it
before `django.setup()`, and `[tool.django-stubs]` points the mypy plugin at it
— the plugin imports a settings module to resolve Django's own generics, and a
package with no project of its own has to supply one. A second module for mypy
alone would be one more thing that can disagree with what the tests run under.

There is no database here, and deliberately: this package has no models, so a
suite that configured one would be waiting on Postgres to test a decorator.
"""

from __future__ import annotations

from typing import Any

SECRET_KEY = "not-a-secret-nothing-here-signs-anything"
DEBUG = False
ALLOWED_HOSTS = ["*"]
USE_TZ = True

INSTALLED_APPS = ["django_kleora"]
MIDDLEWARE: list[str] = []
DATABASES: dict[str, Any] = {}

ISSUER = "https://acme.kleora.eu"
AUDIENCE = "https://api.acme.example"

KLEORA = {
    "ISSUER": ISSUER,
    "AUDIENCE": AUDIENCE,
}
