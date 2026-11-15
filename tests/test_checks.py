"""`manage.py check`, and the sandbox table it decides `kleora.E003` with.

The table is the one every Kleora SDK carries, row for row (`kleora`'s own
`tests/test_environments.py` among them). It is repeated here rather than
referenced because what is being asserted is different: not that `classify_host` answers
`sandbox`, but that **the Django startup check refuses exactly the pairs that
rule refuses** — that the guard a customer actually meets is wired to the shared
rule and not to a fourth opinion about what a sandbox host looks like.

A row added to the rule belongs in every SDK's copy. If this one and
`kleora`'s ever disagree, one of them is describing a guard that does not
exist.
"""

from __future__ import annotations

import pytest
from django.core.checks import CheckMessage, run_checks
from django.test import override_settings

from tests.conftest import LIVE_KEY, TEST_KEY
from tests.settings import AUDIENCE, ISSUER

# `(host, kind, why)` — identical to `kleora`'s `CLASSIFICATION`.
CLASSIFICATION = [
    ("acme.kleora.eu", "production", "a production issuer"),
    ("acme-sandbox.kleora.eu", "sandbox", "a sandbox issuer"),
    ("acme.sandbox.kleora.eu", "production", "the retired two-label shape"),
    ("acme.corp-sandbox.internal", "production", "a base domain that carries the suffix"),
    ("acme.corp.sandbox.internal", "production", "a base domain that carries the label"),
    ("my-sandbox-app.kleora.eu", "production", "the word inside a slug, not at its end"),
    ("my-sandbox-app-sandbox.kleora.eu", "sandbox", "that slug's sandbox side"),
    ("sandbox.kleora.eu", "production", "the bare word"),
    ("-sandbox.kleora.eu", "production", "the suffix with nothing before it"),
    ("id-sandbox.localhost:8100", "sandbox", "development, with a port"),
    ("id.localhost:8100", "production", "development, with a port"),
    ("ACME-SANDBOX.kleora.eu", "sandbox", "DNS labels are case-insensitive"),
    ("app.example.com", "production", "a customer host announces nothing"),
    ("app-sandbox.example.com", "sandbox", "a customer host that does announce it"),
    ("localhost", "production", "a single label that is not a sandbox"),
]

KEYS = {"production": LIVE_KEY, "sandbox": TEST_KEY}


def ids_of(messages: list[CheckMessage]) -> list[str]:
    return sorted(str(message.id) for message in messages)


def kleora_checks() -> list[CheckMessage]:
    return [message for message in run_checks() if str(message.id).startswith("kleora.")]


def test_the_suites_own_settings_pass() -> None:
    assert kleora_checks() == []


@pytest.mark.parametrize(("host", "kind", "why"), CLASSIFICATION)
@pytest.mark.parametrize("key_kind", ["production", "sandbox"])
def test_e003_refuses_exactly_the_pairs_the_shared_rule_refuses(
    host: str, kind: str, why: str, key_kind: str
) -> None:
    """One assertion per (host, key kind): 26 pairs, 13 of which must be refused."""

    with override_settings(
        KLEORA={"ISSUER": f"https://{host}", "AUDIENCE": AUDIENCE, "API_KEY": KEYS[key_kind]}
    ):
        found = ids_of(kleora_checks())

    if key_kind == kind:
        assert found == [], f"{why}: a {key_kind} key belongs with this issuer"
    else:
        assert found == ["kleora.E003"], f"{why}: a {key_kind} key must not reach this issuer"


def test_e001_when_the_setting_is_missing_or_unusable() -> None:
    with override_settings(KLEORA=None):
        messages = kleora_checks()

    assert ids_of(messages) == ["kleora.E001"]
    assert "settings.KLEORA is not set" in messages[0].msg


def test_e002_when_the_key_is_not_a_kleora_key() -> None:
    with override_settings(
        KLEORA={"ISSUER": ISSUER, "AUDIENCE": AUDIENCE, "API_KEY": "sk_live_whoever"}
    ):
        messages = kleora_checks()

    assert ids_of(messages) == ["kleora.E002"]
    assert "kl_live_" in str(messages[0].hint)


def test_e003_shows_the_literal_prefix_and_nothing_random() -> None:
    """A credential is never logged; it is redacted to the prefix.

    A check message lands in a deployment log nobody chose to hold a credential,
    so the message is built from the key's *kind* and never sliced out of the
    key itself — there is no code path here that could print a random character.
    """

    with override_settings(KLEORA={"ISSUER": ISSUER, "AUDIENCE": AUDIENCE, "API_KEY": TEST_KEY}):
        messages = kleora_checks()

    assert ids_of(messages) == ["kleora.E003"]
    text = messages[0].msg
    assert "kl_test_…" in text
    assert "K" * 8 not in text


def test_w001_names_a_key_that_is_not_read() -> None:
    with override_settings(KLEORA={"ISSUER": ISSUER, "AUDIENCE": AUDIENCE, "AUDIANCE": "typo"}):
        messages = kleora_checks()

    assert ids_of(messages) == ["kleora.W001"]
    assert "AUDIANCE" in messages[0].msg


def test_no_key_configured_is_not_a_finding() -> None:
    """Verifying tokens and administering the platform are separate jobs."""

    with override_settings(KLEORA={"ISSUER": ISSUER, "AUDIENCE": AUDIENCE}):
        assert kleora_checks() == []
