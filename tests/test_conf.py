"""Reading `settings.KLEORA`, and refusing the shapes that cannot work.

Every refusal here names the key and shows the value, because a settings mistake
is read by somebody who is looking at the settings file — and because the
alternative failure is much worse: a `KLEORA` with a relative `ISSUER` does not
fail at startup, it fails on every request with `issuer_mismatch`, which is a
message about the *token*.
"""

from __future__ import annotations

import pytest
from django.test import override_settings

from django_kleora import ConfigurationError
from django_kleora.conf import get_settings
from tests.settings import AUDIENCE, ISSUER


def test_the_documented_dict_reads_back() -> None:
    """The four keys of the README's example."""

    with override_settings(
        KLEORA={
            "ISSUER": "https://acme-sandbox.kleora.eu",
            "AUDIENCE": "https://api.acme.example",
            "API_KEY": "kl_test_" + "K" * 40,
            "API_BASE": "https://api.kleora.io/api/v1",
        }
    ):
        configuration = get_settings()

    assert configuration.issuer == "https://acme-sandbox.kleora.eu"
    assert configuration.audience == "https://api.acme.example"
    assert configuration.api_key == "kl_test_" + "K" * 40
    # `kleora` accepts the documented `/api/v1` spelling and strips it, so
    # the generated operations do not end up requesting `/api/v1/api/v1/me`.
    assert configuration.api_base == "https://api.kleora.io/api/v1"
    assert configuration.kind == "sandbox"


def test_api_key_and_api_base_are_optional() -> None:
    with override_settings(KLEORA={"ISSUER": ISSUER, "AUDIENCE": AUDIENCE}):
        configuration = get_settings()

    assert configuration.api_key is None
    assert configuration.api_base == "https://api.kleora.io"


def test_a_trailing_slash_on_the_issuer_is_forgiven() -> None:
    """`iss` compares by exact string; a value copied from a browser bar has one."""

    with override_settings(KLEORA={"ISSUER": f"{ISSUER}/", "AUDIENCE": AUDIENCE}):
        assert get_settings().issuer == ISSUER


def test_the_setting_is_cached_until_it_changes() -> None:
    first = get_settings()
    assert get_settings() is first

    with override_settings(KLEORA={"ISSUER": ISSUER, "AUDIENCE": "other"}):
        assert get_settings().audience == "other"

    assert get_settings().audience == AUDIENCE


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "settings.KLEORA is not set"),
        ("https://acme.kleora.eu", "must be a dict"),
        ({}, "settings.KLEORA['ISSUER']"),
        ({"ISSUER": ISSUER}, "settings.KLEORA['AUDIENCE']"),
        ({"ISSUER": "", "AUDIENCE": AUDIENCE}, "settings.KLEORA['ISSUER']"),
        ({"ISSUER": ISSUER, "AUDIENCE": "  "}, "settings.KLEORA['AUDIENCE']"),
        ({"ISSUER": "acme.kleora.eu", "AUDIENCE": AUDIENCE}, "absolute http(s) URL"),
        ({"ISSUER": "/oauth", "AUDIENCE": AUDIENCE}, "absolute http(s) URL"),
        ({"ISSUER": ISSUER, "AUDIENCE": AUDIENCE, "API_KEY": 7}, "a string or absent"),
        (
            {"ISSUER": ISSUER, "AUDIENCE": AUDIENCE, "API_BASE": "nope"},
            "settings.KLEORA['API_BASE'] must be an absolute",
        ),
    ],
)
def test_what_cannot_be_used_is_refused_by_name(value: object, expected: str) -> None:
    with override_settings(KLEORA=value), pytest.raises(ConfigurationError) as raised:
        get_settings()

    assert expected in str(raised.value)
