"""`get_management_client()`: one client, from settings, guarded at construction.

The guard is the part with teeth. `ISSUER` is always configured in a Django
project, so a `kl_test_` key in a production project is decided locally and
`EnvironmentMismatch` is raised **before a socket is opened** — the key is never
sent to the wrong environment, which is why it is a construction-time refusal.
"""

from __future__ import annotations

import pytest
from django.test import override_settings
from kleora import EnvironmentMismatch, ManagementClient

from django_kleora import ConfigurationError, get_management_client
from tests.conftest import LIVE_KEY, TEST_KEY
from tests.settings import AUDIENCE, ISSUER

SANDBOX_ISSUER = "https://acme-sandbox.kleora.eu"


def test_it_is_built_from_the_settings() -> None:
    with override_settings(KLEORA={"ISSUER": ISSUER, "AUDIENCE": AUDIENCE, "API_KEY": LIVE_KEY}):
        client = get_management_client()

        assert isinstance(client, ManagementClient)
        assert client.base_url == "https://api.kleora.io"


def test_the_documented_api_base_spelling_does_not_double_the_prefix() -> None:
    """The README's example carries `/api/v1`; the generated paths carry it too."""

    with override_settings(
        KLEORA={
            "ISSUER": ISSUER,
            "AUDIENCE": AUDIENCE,
            "API_KEY": LIVE_KEY,
            "API_BASE": "https://api.kleora.io/api/v1",
        }
    ):
        assert get_management_client().base_url == "https://api.kleora.io"


def test_the_same_client_is_returned_within_a_process() -> None:
    """One connection pool, and one `GET /me` for the guard rather than one each."""

    with override_settings(KLEORA={"ISSUER": ISSUER, "AUDIENCE": AUDIENCE, "API_KEY": LIVE_KEY}):
        assert get_management_client() is get_management_client()


def test_a_sandbox_key_with_a_production_issuer_is_refused_before_any_request() -> None:
    with (
        override_settings(KLEORA={"ISSUER": ISSUER, "AUDIENCE": AUDIENCE, "API_KEY": TEST_KEY}),
        pytest.raises(EnvironmentMismatch) as raised,
    ):
        get_management_client()

    assert "sandbox key" in str(raised.value)
    assert ISSUER in str(raised.value)


def test_a_production_key_with_a_sandbox_issuer_is_refused_too() -> None:
    with (
        override_settings(
            KLEORA={"ISSUER": SANDBOX_ISSUER, "AUDIENCE": AUDIENCE, "API_KEY": LIVE_KEY}
        ),
        pytest.raises(EnvironmentMismatch),
    ):
        get_management_client()


def test_the_matching_pair_is_accepted() -> None:
    with override_settings(
        KLEORA={"ISSUER": SANDBOX_ISSUER, "AUDIENCE": AUDIENCE, "API_KEY": TEST_KEY}
    ):
        assert get_management_client().base_url == "https://api.kleora.io"


def test_no_api_key_is_a_configuration_error_naming_the_key() -> None:
    with (
        override_settings(KLEORA={"ISSUER": ISSUER, "AUDIENCE": AUDIENCE}),
        pytest.raises(ConfigurationError) as raised,
    ):
        get_management_client()

    assert "API_KEY" in str(raised.value)


def test_the_credential_is_not_in_the_repr() -> None:
    """A credential is never shown — `kleora` redacts it; assert it here.

    The value reaches a traceback nobody chose, through this package's own
    accessor, so this is the call site where it matters.
    """

    with override_settings(KLEORA={"ISSUER": ISSUER, "AUDIENCE": AUDIENCE, "API_KEY": LIVE_KEY}):
        text = repr(get_management_client())

    assert LIVE_KEY not in text
    assert "kl_live_" in text
