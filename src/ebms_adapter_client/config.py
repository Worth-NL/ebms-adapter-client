from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EbmsAdapterClientConfig:
    """Connection settings for :class:`~ebms_adapter_client.client.EbmsAdapterClient`.

    ``base_url`` is the scheme+host+port ebms-admin is listening on (e.g.
    ``http://localhost:8080``). ``service_path``/``api_path`` reproduce how
    ebms-admin's ``Start.java`` (``SOAP_URL = "/service"``) and
    ``EmbeddedWebConfig.java`` (``sf.setAddress("/rest/v19" + path)``) mount
    the REST API, and can be overridden if a reverse proxy changes that
    layout.
    """

    base_url: str
    username: str | None = None
    password: str | None = None
    service_path: str = "/service"
    api_path: str = "/rest/v19"
    timeout: float = 30.0
    verify_ssl: bool | str = True

    @property
    def api_base_url(self) -> str:
        return f"{self.base_url.rstrip('/')}{self.service_path}{self.api_path}"
