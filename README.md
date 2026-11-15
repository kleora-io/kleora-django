# `django-kleora`

The Django integration: a django-ninja auth class, middleware, a decorator and
a settings dict, over [`kleora`](https://pypi.org/project/kleora/), which it
installs for you.

## Install

```bash
pip install django-kleora
# or
uv add django-kleora
```

Requires Python 3.12 or newer, Django 5.0 or newer and django-ninja 1.6.3 or
newer.

## Quickstart

```python
# settings.py
KLEORA = {"ISSUER": "<issuer>", "AUDIENCE": "<audience>"}

# api.py
from django_kleora import (
    KleoraAuthentication,
    install_problem_handlers,
    requires_permission,
)
api = install_problem_handlers(NinjaAPI(auth=KleoraAuthentication()))

@api.get("/invoices")
@requires_permission("invoices:read")
def invoices(request):
    return {"tenant": request.kleora.tenant}
```

That block is the Django quickstart Kleora's console shows on an App's
overview. The package's own suite reads it out of this README, executes it and
drives the API it builds (`tests/test_quickstart.py`), because the thing a
customer copies is the thing that has to work.

The full settings, with the middleware for views django-ninja never sees:

```python
# settings.py
INSTALLED_APPS = [..., "django_kleora"]
MIDDLEWARE = [..., "django_kleora.KleoraAuthMiddleware"]

KLEORA = {
    "ISSUER": "https://acme-sandbox.kleora.eu",
    "AUDIENCE": "https://api.acme.example",
    "API_KEY": env("KLEORA_API_KEY"),        # optional
    "API_BASE": "https://api.kleora.io/api/v1",
}
```

**Nothing here verifies a token or classifies an issuer itself.** The JWKS cache,
the eight `TokenError` codes, the sandbox rule and the environment guard are all
`kleora`'s. This package is glue, and that is the point: a second
implementation would drift from the first within a release, and the copy that
drifted would be the one on a customer's request path.

## What it exports

| Name | What it does |
| --- | --- |
| `KleoraAuthentication` | `ninja.security.HttpBearer` subclass. Verifies the bearer token, returns `Claims`, sets `request.kleora` (and django-ninja's own `request.auth` — the same object). |
| `KleoraAuthMiddleware` | For views django-ninja never sees. Sets `request.kleora` to `Claims` or `None` and `request.kleora_error` to why, and **never refuses a request itself**. |
| `requires_permission("invoices:read")` | View decorator. 403 when the token lacks the permission, 401 when there is no verified token, 503 when the issuer could not be reached. Works on a plain Django view and on a django-ninja operation. |
| `get_management_client()` | The process's `kleora.ManagementClient`, built from `KLEORA` and guarded at construction. |
| `install_problem_handlers(api)` | Makes a `NinjaAPI` answer django-ninja's own two auth refusals with RFC 9457 problem documents instead of `{"detail": …}`. Returns the `api`, so it can wrap the construction. |
| `IssuerUnavailable` | The 503 the django-ninja auth class raises. A `ninja.errors.HttpError`, so django-ninja answers it without you registering anything. |
| `ConfigurationError` | A `KLEORA` dict that cannot be used. Both a `kleora.KleoraError` and Django's `ImproperlyConfigured`. |
| `account_portal_url(client_id=…, section=None, return_to=None)` | The hosted account portal's URL on `KLEORA["ISSUER"]` — a pure function, no request. The portal is offered only when that Client lists `self_service` in `allowed_scopes`; otherwise it says managing the account there is not offered. `return_to` must be an absolute URL with no fragment or userinfo, and becomes the portal's back link only when it is one of the Client's `post_logout_redirect_uris`. Open it in a new tab, never a frame. |

## Settings

`ISSUER` and `AUDIENCE` are required. `AUDIENCE` is the `client_id` the token was
issued to or the environment's `api_audience`; `aud` must contain it. `API_KEY`
is needed only by `get_management_client()`, and `API_BASE` defaults to
`https://api.kleora.io` — the documented `…/api/v1` spelling is accepted
and normalised, so you cannot end up requesting `/api/v1/api/v1/me`.

The `INSTALLED_APPS` entry buys one thing and it is worth having: `manage.py
check` then reports a `KLEORA` it cannot use — including **a `kl_test_` key
configured against a production issuer** (`kleora.E003`), which is
decided from the settings alone, with no network call, before the process serves
anything.

## What it answers, and where the shapes differ

`requires_permission` writes RFC 9457 problem documents under the same
`https://kleora.io/problems/` namespace the management API and
`@kleora-io/node`'s middlewares use, so an application that puts Kleora in
front of a Django API and an Express API gets one error shape across both:

| Cause | Answer |
| --- | --- |
| The token carries the permission | the view runs |
| A verified token without it | 403 `insufficient-permission`, naming it |
| No verified token | 401 `unauthenticated` |
| The issuer's JWKS could not be read at all | 503 `issuer-unavailable` |

Those are `requires_permission`'s answers. On a `NinjaAPI` the auth class refuses
before any view runs, and its 401 and 503 are the framework's `{"detail": …}`
until `install_problem_handlers(api)` has been called — see below.

The last row is a deliberate distinction and it matters: an unknown `kid` is
a bad token and the caller's problem, an unreachable issuer is the provider's and
is retryable. Answering 401 to both tells every client to discard a perfectly
good token and go back to a provider that is already down.

**Two refusals are django-ninja's to write, and one call takes them back.** When
`KleoraAuthentication` is attached to a `NinjaAPI`, a token that does not verify
is the framework's own 401 — `{"detail": "Unauthorized"}`, at
`application/json` — because an auth class says yes or no and the framework
writes the answer. The 503 above is the same story with a different status. Add
one call and both become problem documents like everything else here:

```python
from django_kleora import KleoraAuthentication, install_problem_handlers

api = install_problem_handlers(NinjaAPI(auth=KleoraAuthentication()))
```

It is safe to call unconditionally and safe to call twice, and a handler you
register afterwards wins — `add_exception_handler` is a dict assignment, so your
API's own opinion outranks this package's.

**Why it is a call and not something this package does for you.** An auth class
never learns which `NinjaAPI` it was attached to: django-ninja invokes it as
`callback(request)`, keeps its handlers in a private per-instance dict with no
class-level registry, no `NINJA_*` setting and no constructor argument, and no
longer keeps a list of the APIs a process has built. The two mechanisms that
would work — patching `NinjaAPI` from an `AppConfig`, or rewriting the response
in middleware — would each change the behaviour of APIs that have nothing to do
with Kleora, and were rejected for that rather than for being impossible. The
whole search is written down in `django_kleora.handlers`, so the next
person reading this does not have to repeat it.

The 401 body never carries a reason in either shape, by design: the difference
between "expired" and "signed by a key we have never seen" is of no use to a
caller that does not already hold a valid token, and of every use to one probing.
The reason goes to the `django_kleora` logger instead.

## Development

```bash
uv sync
uv run pytest           # no stack, no database, no network
uv run ruff check . && uv run ruff format --check .
uv run mypy             # strict, with django-stubs
uv build                # the sdist and the wheel, into dist/
```

The suite signs its own ES256 tokens and answers the issuer's JWKS request
through `httpx.MockTransport`, so it exercises the real verifier in `kleora`
with only the socket replaced.

This package has no generated client of its own: `get_management_client()`
returns `kleora`'s `ManagementClient`, whose client is generated in
[kleora-python](https://github.com/kleora-io/kleora-python).

### Contract tests

There are none here, and so none in CI. Everything this package does on the
wire is done by `kleora`, whose live contract tests (marked `live`) prove the
JWKS document and the management API against a real environment; this suite
covers the Django glue around them, which needs no network.

### Releasing

Bump `version` in `pyproject.toml` on `main`, then run the **Release** workflow
(`.github/workflows/release.yml`) by hand. A maintainer approves the `pypi`
environment, and the workflow runs the unit suite, builds the sdist and the
wheel from the committed lockfile and publishes them to PyPI by trusted
publishing. No token is stored anywhere. PyPI refuses a version that already
exists.

## Licence

[Apache License, Version 2.0](https://www.apache.org/licenses/LICENSE-2.0) —
the full, unmodified text ships inside this package, so it travels with
whatever you install. Apache-2.0 rather than a shorter permissive licence
because of the explicit patent grant in §3, which is the term a legal review of
a vendor SDK asks about.

**There is no `NOTICE` file**, here or in any other Kleora package, and that
is deliberate. Apache-2.0 §4(d) turns a `NOTICE` into an obligation that
propagates: every downstream redistributor of a work that has one must
reproduce its contents. Kleora is the sole copyright holder of the code in
these packages, so there is nothing to attribute, and a `NOTICE` would place a
requirement on you in exchange for nothing. Third-party dependencies keep their
own licences and their own notices; this package redistributes none of them —
its manifest names them and your installer fetches them.

Apache-2.0 covers what you install and compile into your own product: the
browser, Node, Nuxt and Python SDKs. It does **not** cover the rest of
Kleora — the hosted service, the API servers, the management console and the
hosted authentication pages are proprietary.
