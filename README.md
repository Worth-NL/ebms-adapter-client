# ebms-adapter-client

[![PyPI](https://img.shields.io/pypi/v/ebms-adapter-client.svg?style=for-the-badge)](https://pypi.org/project/ebms-adapter-client/)
[![Python versions](https://img.shields.io/pypi/pyversions/ebms-adapter-client.svg?style=for-the-badge)](https://pypi.org/project/ebms-adapter-client/)
[![CI](https://img.shields.io/github/actions/workflow/status/Worth-NL/ebms-adapter-client/ci.yml?style=for-the-badge)](https://github.com/Worth-NL/ebms-adapter-client/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)
[![Ruff](https://img.shields.io/endpoint?style=for-the-badge&url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

A minimal Python client for the REST API exposed by
[eluinstra/ebms-core](https://github.com/eluinstra/ebms-core) (branch
`ebms-core-2.20.x`), an ebMS (Electronic Business Messaging Service)
adapter/core used to send and receive ebMS messages between trading
partners.

This package only talks to ebms-core's HTTP/JSON REST API — it doesn't
implement ebMS/SOAP itself. It's a building block intended to be consumed
later by a NotifyNL service (e.g. a Celery task) as a new notification
channel; it has no NotifyNL-specific code itself.

## Endpoint coverage

ebms-core mounts its REST API at `{base_url}/service/rest/v19/...` (see
`EmbeddedWebConfig.java`/`Start.java` in the sibling `ebms-admin` repo, which
is what actually deploys `ebms-core`). Four JSON resource groups are covered:

- `/cpas` — Collaboration Protocol Agreement (CPA) management
- `/urlMappings` — URL mapping management
- `/certificateMappings` — certificate mapping management
- `/ebms` — message submission, retrieval, status, and event polling

The MTOM/multipart variants (`POST /ebms/messages/mtom`,
`GET /ebms/messages/mtom/{messageId}`) are intentionally **not** implemented —
the JSON `DataSource` model (Base64-encoded `content`) covers attachments for
the plain JSON endpoints.

## Installation

```bash
pip install -e .
```

## Usage

```python
from ebms_adapter_client import (
    DataSource,
    EbmsAdapterClient,
    EbmsAdapterClientConfig,
    MessageRequest,
    MessageRequestProperties,
)

config = EbmsAdapterClientConfig(
    base_url="http://localhost:8080",
    username="user", # omit if the server runs without --authentication
    password="pass",
)

with EbmsAdapterClient(config) as client:
    message_id = client.send_message(
        MessageRequest(
            properties=MessageRequestProperties(
                cpa_id="cpa-1",
                from_party_id="party-a",
                service="my-service",
                action="my-action",
            ),
            data_sources=[
                DataSource(content_type="application/pdf", content=b"...", name="letter.pdf"),
            ],
        )
    )

    status = client.get_message_status(message_id)
```

### Configuration

`EbmsAdapterClientConfig` builds the full API base URL as
`{base_url}{service_path}{api_path}`, defaulting to `/service` + `/rest/v19`
to match ebms-admin's default wiring. Override `service_path`/`api_path` if a
reverse proxy changes that layout.

### Auth

- No credentials (`username=None`) → no `Authorization` header is sent,
  matching a server started without `--authentication`.
- `username`/`password` set → HTTP Basic Auth, matching a server started with
  `--authentication` (without `--clientAuthentication`).
- Mutual TLS (`--authentication --ssl --clientAuthentication`) is not wired up
  yet; pass a preconfigured `httpx.Client` (with `cert=`) via the
  `http_client` constructor argument if needed.

### Error handling

All non-2xx responses raise a subclass of `EbmsAdapterError`
(`ebms_adapter_client.exceptions`):

- `EbmsNotFoundError` — HTTP 404
- `EbmsBadRequestError` — HTTP 400 (message text carries the server's error)
- `EbmsServerError` — HTTP 5xx
- `EbmsConnectionError` — the server could not be reached at all

## Development

```bash
uv sync --all-groups
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for more.
