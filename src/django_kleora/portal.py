"""The hosted account portal's URL, for this project's issuer.

The same pure function as `kleora.account_portal_url`,
with the issuer taken from settings, so a template can link to the portal
without repeating it:

```python
from django_kleora import account_portal_url

url = account_portal_url(client_id="cl_…", return_to="https://app.example.com/")
```

**The portal is offered only for a Client whose `allowed_scopes` include
`self_service`** (that list is the consent). For any other Client the
link still opens, and every portal page says that managing the account there is
not offered. `client_id` is required because `KLEORA` carries no client id: a
Django project verifies tokens for an audience and never needed one before, and
the Client named is the one whose consent and `post_logout_redirect_uris`
decide what the portal shows.

Link it as a new tab or a top-level navigation, never a frame: the portal
refuses to be framed (`frame-ancestors 'none'`).
"""

from __future__ import annotations

from kleora import AccountPortalSection
from kleora import account_portal_url as _account_portal_url

from .conf import get_settings


def account_portal_url(
    *,
    client_id: str,
    section: AccountPortalSection | None = None,
    return_to: str | None = None,
) -> str:
    """The portal URL on `KLEORA["ISSUER"]` for `client_id`'s users. No request.

    `return_to` must be an absolute `http`/`https` URL with no fragment and no
    userinfo (`kleora.KleoraError` otherwise); the issuer shows it as the
    portal's "back" link only when it equals one of the Client's
    `post_logout_redirect_uris`.
    """

    return _account_portal_url(
        issuer=get_settings().issuer,
        client_id=client_id,
        section=section,
        return_to=return_to,
    )
