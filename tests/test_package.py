"""The package's surface: what it exports and what it refuses to re-export.

The package provides four things — a django-ninja auth class, middleware, a
decorator and the `KLEORA` settings — plus `request.kleora` and
`get_management_client()`. This module is the assertion that each name is
importable from the top level, because "importable from the top level" is the
entire contract the quickstart snippet relies on.
"""

from __future__ import annotations

import tomllib
from importlib.metadata import metadata
from pathlib import Path

import django_kleora


def test_every_documented_name_is_exported() -> None:
    """The five documented names, plus four more.

    `account_portal_url` is the hosted portal's URL on `KLEORA["ISSUER"]`.

    `install_problem_handlers` is the one call that brings
    django-ninja's own two refusals into the RFC 9457 shape everything else this
    package writes already has.
    """

    assert sorted(django_kleora.__all__) == [
        "ConfigurationError",
        "IssuerUnavailable",
        "KleoraAuthMiddleware",
        "KleoraAuthentication",
        "__version__",
        "account_portal_url",
        "get_management_client",
        "install_problem_handlers",
        "requires_permission",
    ]
    for name in django_kleora.__all__:
        assert hasattr(django_kleora, name), name


def test_the_quickstart_imports_resolve() -> None:
    """The quickstart's imports, as a customer writes them."""

    from django_kleora import KleoraAuthentication, requires_permission

    assert callable(requires_permission)
    assert callable(KleoraAuthentication)


def test_the_taxonomy_is_kleoras_and_not_a_second_copy() -> None:
    """Two copies of one class make `except` lie.

    This package is built *on* `kleora` rather than beside it, so it must
    not redeclare `TokenError` or `EnvironmentMismatch`. A customer catching
    `kleora.TokenError` around a Django view has to catch what the view
    actually raised.
    """

    import kleora

    ours = set(django_kleora.__all__)
    assert ours & {"TokenError", "EnvironmentMismatch", "ApiError", "Claims"} == set()
    assert issubclass(django_kleora.ConfigurationError, kleora.KleoraError)


def test_configuration_error_is_also_djangos() -> None:
    """So `manage.py` prints it as a setup problem rather than a crash."""

    from django.core.exceptions import ImproperlyConfigured

    assert issubclass(django_kleora.ConfigurationError, ImproperlyConfigured)


def test_version_is_a_string() -> None:
    assert isinstance(django_kleora.__version__, str)
    assert django_kleora.__version__


def test_the_manifest_names_the_same_author_and_homepage_as_kleoras() -> None:
    """Both packages are published to PyPI, which shows these fields.

    Without them a project page renders an empty Author and no link. The shared
    two are asserted against the installed `kleora` distribution's own metadata
    rather than only against literals, so the two packages cannot drift apart;
    the repository and issue tracker are each package's own.
    """

    here = Path(__file__).resolve().parents[1]
    ours = tomllib.loads((here / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    sibling = metadata("kleora")
    sibling_urls = dict(entry.split(", ", 1) for entry in sibling.get_all("Project-URL") or [])

    assert ours["authors"] == [{"name": "Kleora", "email": "contact@kleora.io"}]
    assert sibling["Author-email"] == "Kleora <contact@kleora.io>"
    assert ours["urls"]["Homepage"] == sibling_urls["Homepage"] == "https://kleora.io"
    assert ours["urls"]["Documentation"] == sibling_urls["Documentation"]
    assert ours["urls"]["Repository"] == "https://github.com/kleora-io/kleora-django"
    assert ours["urls"]["Issues"] == "https://github.com/kleora-io/kleora-django/issues"
