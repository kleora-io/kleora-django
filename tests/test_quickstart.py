"""The README's quickstart, executed — not transcribed, not paraphrased.

The README's "Quickstart" block is what a customer copies, and Kleora's console
shows the same block on an App's overview. Asserting that the names it imports
exist is not enough: the snippet has to *run*.

So this module reads that block out of `README.md`, `exec`s it, and drives the
API it builds with a token this suite signed. A change to the snippet that this
package cannot serve fails here, in the package's own suite, rather than on a
customer's laptop.
"""

from __future__ import annotations

import ast
import itertools
import re
from pathlib import Path
from typing import Any

from ninja import NinjaAPI
from ninja.testing import TestClient

import django_kleora
from tests.conftest import (
    TENANT,
    JWKSEndpoint,
    SigningKey,
    bearer,
)

README = Path(__file__).resolve().parents[1] / "README.md"

# The fenced `python` block under the README's `## Quickstart` heading.
QUICKSTART = re.compile(r"^## Quickstart\n.*?```python\n(?P<code>.*?)```", re.DOTALL | re.MULTILINE)


_namespaces = itertools.count()


def hosted(snippet_text: str) -> NinjaAPI:
    """`exec` the snippet and hand back the `NinjaAPI` it built.

    `NinjaAPI` is the only name put in scope, because that is the import a
    customer's own file already has; the package's names have to come from the
    snippet's own import, which is the line that matters.

    The snippet is a fragment dropped into a file that already exists, not a
    runnable program, which is why it does not import `NinjaAPI` itself. What is
    not allowed is a block that fails on *Kleora's* names.

    The one thing substituted is `urls_namespace`, which django-ninja requires to
    be unique per process and which a customer — who has one API — never passes.
    Without it the second test to run this would fail on django-ninja's registry
    rather than on anything about the snippet.
    """

    def build(**kwargs: Any) -> NinjaAPI:
        return NinjaAPI(urls_namespace=f"quickstart-{next(_namespaces)}", **kwargs)

    namespace: dict[str, Any] = {"NinjaAPI": build}
    exec(compile(snippet_text, str(README), "exec"), namespace)
    api = namespace["api"]
    assert isinstance(api, NinjaAPI)
    return api


def snippet() -> str:
    match = QUICKSTART.search(README.read_text(encoding="utf-8"))
    assert match is not None, f"no Quickstart python block in {README.name}"
    return match.group("code")


def test_the_quickstart_imports_only_what_the_package_exports() -> None:
    """Every name the snippet takes from `django_kleora` is in its `__all__`."""

    imported = [
        alias.name
        for node in ast.walk(ast.parse(snippet()))
        if isinstance(node, ast.ImportFrom) and node.module == "django_kleora"
        for alias in node.names
    ]

    assert imported
    assert set(imported) <= set(django_kleora.__all__)


def test_the_quickstart_runs_unchanged(key: SigningKey, jwks: JWKSEndpoint) -> None:
    """The snippet is `exec`ed with nothing in scope but `NinjaAPI`.

    That is the import a customer's own file already has (`from ninja import
    NinjaAPI`); the package's names have to come from the snippet's own import.
    """

    response = TestClient(hosted(snippet())).get("/invoices", headers=bearer(key.access_token()))

    assert response.status_code == 200
    assert response.json() == {"tenant": TENANT}


def test_the_quickstart_refuses_what_it_should(key: SigningKey, jwks: JWKSEndpoint) -> None:
    """The same API, told no two ways: 401 with no credential, 403 without the permission."""

    client = TestClient(hosted(snippet()))

    assert client.get("/invoices").status_code == 401
    without = key.access_token(permissions=["invoices:write"])
    assert client.get("/invoices", headers=bearer(without)).status_code == 403


def test_the_snippet_alone_gives_one_refusal_shape(key: SigningKey, jwks: JWKSEndpoint) -> None:
    """The block a customer copies answers a refusal with a problem document.

    django-ninja answers a refused token with its own `{"detail": "Unauthorized"}`
    (`tests/test_handlers.py` pins that, and why it is wrong for this platform).
    The snippet's own `install_problem_handlers(NinjaAPI(...))` replaces it with the
    401 `unauthenticated` problem document Kleora's APIs give that status.

    **This asserts the snippet, not a wrapper around it**: the snippet has to
    produce that behaviour without the customer reading further, and wrapping it
    here would prove the helper works while leaving that unasserted.
    """

    api = hosted(snippet())
    response = TestClient(api).get("/invoices")

    assert response.status_code == 401
    assert response["Content-Type"] == "application/problem+json"
    assert response.json()["type"] == "https://kleora.io/problems/unauthenticated"
