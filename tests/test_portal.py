"""`account_portal_url` on `KLEORA["ISSUER"]`.

The URL rules themselves are `kleora`'s and tested there (`tests/test_portal.py`
of that package); this holds the one thing this package adds — the issuer comes
from settings, and follows them.
"""

from __future__ import annotations

import pytest
from django.test import override_settings
from kleora import KleoraError

from django_kleora import ConfigurationError, account_portal_url

from .settings import AUDIENCE, ISSUER


def test_builds_the_portal_url_on_the_configured_issuer() -> None:
    assert account_portal_url(client_id="cl_1") == f"{ISSUER}/account?client_id=cl_1"


def test_carries_the_section_and_return_to() -> None:
    url = account_portal_url(
        client_id="cl_1", section="sessions", return_to="https://app.example.com/"
    )
    assert url == (
        f"{ISSUER}/account/sessions?client_id=cl_1&return_to=https%3A%2F%2Fapp.example.com%2F"
    )


def test_follows_the_setting() -> None:
    with override_settings(KLEORA={"ISSUER": "https://other.kleora.eu/", "AUDIENCE": AUDIENCE}):
        assert account_portal_url(client_id="c").startswith("https://other.kleora.eu/account?")


def test_refuses_a_return_to_of_the_wrong_shape() -> None:
    with pytest.raises(KleoraError, match="fragment"):
        account_portal_url(client_id="c", return_to="https://app.example.com/#x")


def test_says_what_is_missing_when_kleora_is_not_configured() -> None:
    with override_settings(KLEORA=None), pytest.raises(ConfigurationError):
        account_portal_url(client_id="c")


def test_is_keyword_only() -> None:
    with pytest.raises(TypeError):
        account_portal_url("c")  # type: ignore[call-arg]
