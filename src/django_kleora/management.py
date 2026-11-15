"""`get_management_client()` — one `ManagementClient` per process, from settings.

```python
from django_kleora import get_management_client
from kleora._generated.api.apps import list_apps

apps = list_apps.sync(client=get_management_client().api())
```

Cached because the client owns an `httpx` connection pool: one per call would
open a new TLS connection for every administrative request, and the guard —
which costs one `GET /me` when it cannot be decided locally — would be paid
again each time.

`ISSUER` is always configured here, unlike in bare `kleora` where it is
optional, so the environment guard is always the local one: a `kl_test_` key in
a project whose `ISSUER` is a production issuer raises `EnvironmentMismatch`
from this function, before a socket is opened and before the key has been sent
anywhere. `django_kleora.checks` reports the same condition
at `manage.py check` time, so it is normally caught at startup rather than here.
"""

from __future__ import annotations

import threading

from django.core.signals import setting_changed
from django.dispatch import receiver
from kleora import ManagementClient

from .conf import API_KEY, SETTING, get_settings
from .errors import ConfigurationError

_client: ManagementClient | None = None
_lock = threading.Lock()


def get_management_client() -> ManagementClient:
    """The process's management client, built from `settings.KLEORA`.

    Raises `ConfigurationError` when `API_KEY` is absent — administering the
    platform and verifying its tokens are separate jobs, and a service that only
    does the second needs no key, so the key is optional right up to the moment
    something asks for this.
    """

    global _client
    with _lock:
        if _client is None:
            configuration = get_settings()
            if configuration.api_key is None:
                raise ConfigurationError(
                    f"settings.{SETTING}['{API_KEY}'] is not set, so there is no credential "
                    "to call the management API with"
                )
            _client = ManagementClient(
                api_key=configuration.api_key,
                base_url=configuration.api_base,
                issuer=configuration.issuer,
            )
        return _client


@receiver(setting_changed)
def _reset(*, setting: str, **_: object) -> None:
    """Drop and close the client when the settings it was built from move.

    The same signal `conf` listens to, and for the same reason: a client holding
    the previous `API_KEY` is as stale as the dict it came from. It is closed
    rather than dropped, so a test that overrides `KLEORA` a hundred times
    does not leave a hundred connection pools open.
    """

    if setting != SETTING:
        return
    global _client
    with _lock:
        stale, _client = _client, None
    if stale is not None:
        stale.close()
