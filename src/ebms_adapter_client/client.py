from __future__ import annotations

from types import TracebackType
from typing import Any, cast
from urllib.parse import quote

import httpx

from ebms_adapter_client.config import EbmsAdapterClientConfig
from ebms_adapter_client.exceptions import (
    EbmsBadRequestError,
    EbmsConnectionError,
    EbmsNotFoundError,
    EbmsServerError,
)
from ebms_adapter_client.models import (
    CertificateMapping,
    Message,
    MessageEvent,
    MessageEventType,
    MessageFilter,
    MessageRequest,
    MessageStatus,
    URLMapping,
)

_TEXT_PLAIN = {"Content-Type": "text/plain"}


def _quote(value: str) -> str:
    """Percent-encodes a caller-supplied identifier before splicing it into a URL path,
    so values containing ``/``, ``?``, ``#`` etc. can't alter the request target."""
    return quote(value, safe="")


class EbmsAdapterClient:
    """Client for the ebms-core REST API (``{base_url}/service/rest/v19/...``).

    Covers the JSON ``cpas``, ``urlMappings``, ``certificateMappings`` and
    ``ebms`` resources exposed by ``CPARestController``,
    ``URLMappingRestController``, ``CertificateMappingRestController`` and
    ``EbMSRestController`` in eluinstra/ebms-core (branch
    ``ebms-core-2.20.x``). The MTOM/multipart variants
    (``messages/mtom``) are intentionally out of scope.
    """

    def __init__(self, config: EbmsAdapterClientConfig, *, http_client: httpx.Client | None = None):
        self._config = config
        auth = (config.username, config.password or "") if config.username is not None else None
        self._client = http_client or httpx.Client(
            base_url=config.api_base_url,
            auth=auth,
            timeout=config.timeout,
            verify=config.verify_ssl,
        )

    def __enter__(self) -> EbmsAdapterClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    # -- internal request helper ---------------------------------------------

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise EbmsConnectionError(f"Could not reach ebms-core at {self._config.api_base_url}: {exc}") from exc

        if response.status_code == 404:
            raise EbmsNotFoundError(f"{method} {path} -> 404 Not Found", status_code=404, response_body=response.text)
        if response.status_code == 400:
            raise EbmsBadRequestError(
                response.text or f"{method} {path} -> 400 Bad Request", status_code=400, response_body=response.text
            )
        if response.status_code >= 500:
            raise EbmsServerError(
                response.text or f"{method} {path} -> {response.status_code}",
                status_code=response.status_code,
                response_body=response.text,
            )
        response.raise_for_status()
        return response

    # -- CPA management (/cpas) ----------------------------------------------

    def validate_cpa(self, cpa_xml: str) -> None:
        self._request("POST", "/cpas/validate", content=cpa_xml, headers=_TEXT_PLAIN)

    def insert_cpa(self, cpa_xml: str, *, overwrite: bool = False) -> str:
        response = self._request(
            "POST",
            "/cpas",
            content=cpa_xml,
            headers=_TEXT_PLAIN,
            params={"overwrite": str(overwrite).lower()},
        )
        return response.text

    def delete_cpa(self, cpa_id: str) -> None:
        self._request("DELETE", f"/cpas/{_quote(cpa_id)}")

    def list_cpa_ids(self) -> list[str]:
        return cast("list[str]", self._request("GET", "/cpas").json())

    def get_cpa(self, cpa_id: str) -> str:
        return self._request("GET", f"/cpas/{_quote(cpa_id)}").text

    def clear_cpa_cache(self) -> None:
        self._request("DELETE", "/cpas/cache")

    # -- URL mappings (/urlMappings) ------------------------------------------

    def create_url_mapping(self, mapping: URLMapping) -> None:
        self._request("POST", "/urlMappings", json=mapping.to_dict())

    def delete_url_mapping(self, source: str) -> None:
        # `source` is itself a full URL used verbatim as the path segment (matching
        # ebms-core's URLMappingRestController, which expects the unescaped URL here)
        # -- it is intentionally not percent-encoded.
        self._request("DELETE", f"/urlMappings/{source}")

    def list_url_mappings(self) -> list[URLMapping]:
        return [URLMapping.from_dict(item) for item in self._request("GET", "/urlMappings").json()]

    def clear_url_mapping_cache(self) -> None:
        self._request("DELETE", "/urlMappings/cache")

    # -- Certificate mappings (/certificateMappings) --------------------------

    def create_certificate_mapping(self, mapping: CertificateMapping) -> None:
        self._request("POST", "/certificateMappings", json=mapping.to_dict())

    def delete_certificate_mapping(self, cpa_id: str, source_certificate_b64: str) -> None:
        self._request(
            "DELETE",
            "/certificateMappings",
            params={"cpaId": cpa_id},
            content=source_certificate_b64,
            headers=_TEXT_PLAIN,
        )

    def list_certificate_mappings(self) -> list[CertificateMapping]:
        return [CertificateMapping.from_dict(item) for item in self._request("GET", "/certificateMappings").json()]

    def clear_certificate_mapping_cache(self) -> None:
        self._request("DELETE", "/certificateMappings/cache")

    # -- EBMS messaging (/ebms) ------------------------------------------------

    def ping(self, cpa_id: str, from_party_id: str, to_party_id: str) -> None:
        self._request("POST", f"/ebms/ping/{_quote(cpa_id)}/from/{_quote(from_party_id)}/to/{_quote(to_party_id)}")

    def send_message(self, message_request: MessageRequest) -> str:
        return self._request("POST", "/ebms/messages", json=message_request.to_dict()).text

    def resend_message(self, message_id: str) -> str:
        return self._request("PUT", f"/ebms/messages/{_quote(message_id)}").text

    def list_unprocessed_message_ids(
        self, message_filter: MessageFilter | None = None, *, max_nr: int = 0
    ) -> list[str]:
        params: dict[str, Any] = (message_filter or MessageFilter()).to_query_params()
        params["maxNr"] = max_nr
        return cast("list[str]", self._request("GET", "/ebms/messages/unprocessed", params=params).json())

    def get_message(self, message_id: str, *, process: bool = False) -> Message:
        response = self._request(
            "GET", f"/ebms/messages/{_quote(message_id)}", params={"process": str(process).lower()}
        )
        return Message.from_dict(response.json())

    def process_message(self, message_id: str) -> None:
        self._request("PATCH", f"/ebms/messages/{_quote(message_id)}")

    def get_message_status(self, message_id: str) -> MessageStatus:
        response = self._request("GET", f"/ebms/messages/{_quote(message_id)}/status")
        return MessageStatus.from_dict(response.json())

    def list_unprocessed_message_events(
        self,
        message_filter: MessageFilter | None = None,
        *,
        event_types: list[MessageEventType] | None = None,
        max_nr: int = 0,
    ) -> list[MessageEvent]:
        params: dict[str, Any] = (message_filter or MessageFilter()).to_query_params()
        params["maxNr"] = max_nr
        if event_types:
            params["eventTypes"] = [event_type.value for event_type in event_types]
        response = self._request("GET", "/ebms/events/unprocessed", params=params)
        return [MessageEvent.from_dict(item) for item in response.json()]

    def process_message_event(self, message_id: str) -> None:
        self._request("PATCH", f"/ebms/events/{_quote(message_id)}")
