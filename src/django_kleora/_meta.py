"""Package identity: the version, read from the installed distribution.

The same shape as `kleora._meta`, minus the `User-Agent`: this package
makes no HTTP request of its own. The two requests it can cause — the JWKS fetch
and a management API call — are made by `kleora`, and they carry
`kleora-python/{version}` because that is the package that made them.
Adding a second `User-Agent` here would be this package claiming a request it
did not send.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("django-kleora")
except PackageNotFoundError:  # pragma: no cover - only when running from a source tree
    __version__ = "0.0.0"
