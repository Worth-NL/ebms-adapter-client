import base64
from datetime import UTC, datetime

import pytest
import respx
from httpx import Response

from ebms_adapter_client import (
    CertificateMapping,
    DataSource,
    EbmsAdapterClientConfig,
    EbmsBadRequestError,
    EbmsConnectionError,
    EbMSMessageStatus,
    EbmsNotFoundError,
    EbmsServerError,
    MessageEventType,
    MessageFilter,
    MessageRequest,
    MessageRequestProperties,
    URLMapping,
)
from ebms_adapter_client.client import EbmsAdapterClient

BASE_URL = "http://ebms-core.local:8080"
API_BASE = f"{BASE_URL}/service/rest/v19"


@pytest.fixture
def client():
    config = EbmsAdapterClientConfig(base_url=BASE_URL, username="user", password="pass")
    with EbmsAdapterClient(config) as client:
        yield client


def test_api_base_url_composition():
    config = EbmsAdapterClientConfig(base_url="http://localhost:8080/")
    assert config.api_base_url == "http://localhost:8080/service/rest/v19"


@respx.mock
def test_validate_cpa_sends_raw_text_body(client):
    route = respx.post(f"{API_BASE}/cpas/validate").mock(return_value=Response(200))
    client.validate_cpa("<CollaborationProtocolAgreement/>")
    assert route.calls.last.request.content == b"<CollaborationProtocolAgreement/>"
    assert route.calls.last.request.headers["Content-Type"] == "text/plain"


@respx.mock
def test_insert_cpa_returns_cpa_id(client):
    respx.post(f"{API_BASE}/cpas", params={"overwrite": "true"}).mock(return_value=Response(200, text="cpa-123"))
    cpa_id = client.insert_cpa("<CollaborationProtocolAgreement/>", overwrite=True)
    assert cpa_id == "cpa-123"


@respx.mock
def test_delete_cpa_not_found_raises(client):
    respx.delete(f"{API_BASE}/cpas/unknown-cpa").mock(return_value=Response(404))
    with pytest.raises(EbmsNotFoundError) as exc_info:
        client.delete_cpa("unknown-cpa")
    assert exc_info.value.status_code == 404


@respx.mock
def test_get_cpa_percent_encodes_path_segment(client):
    """A cpa_id containing '/' must not be able to alter the request path."""
    route = respx.get(f"{API_BASE}/cpas/cpa%2Fwith%2Fslashes").mock(return_value=Response(200, text="<cpa/>"))
    client.get_cpa("cpa/with/slashes")
    assert route.called


@respx.mock
def test_list_and_get_cpa(client):
    respx.get(f"{API_BASE}/cpas").mock(return_value=Response(200, json=["cpa-1", "cpa-2"]))
    assert client.list_cpa_ids() == ["cpa-1", "cpa-2"]

    respx.get(f"{API_BASE}/cpas/cpa-1").mock(return_value=Response(200, text="<cpa/>"))
    assert client.get_cpa("cpa-1") == "<cpa/>"


@respx.mock
def test_url_mapping_round_trip(client):
    respx.post(f"{API_BASE}/urlMappings").mock(return_value=Response(200))
    client.create_url_mapping(URLMapping(source="http://a", destination="http://b"))

    respx.get(f"{API_BASE}/urlMappings").mock(
        return_value=Response(200, json=[{"source": "http://a", "destination": "http://b"}])
    )
    mappings = client.list_url_mappings()
    assert mappings == [URLMapping(source="http://a", destination="http://b")]

    respx.delete(f"{API_BASE}/urlMappings/http://a").mock(return_value=Response(200))
    client.delete_url_mapping("http://a")


@respx.mock
def test_certificate_mapping_round_trip(client):
    source_b64 = base64.b64encode(b"cert-source-der").decode("ascii")
    dest_b64 = base64.b64encode(b"cert-dest-der").decode("ascii")

    respx.post(f"{API_BASE}/certificateMappings").mock(return_value=Response(200))
    client.create_certificate_mapping(CertificateMapping(source=source_b64, destination=dest_b64, cpa_id="cpa-1"))

    respx.get(f"{API_BASE}/certificateMappings").mock(
        return_value=Response(200, json=[{"source": source_b64, "destination": dest_b64, "cpaId": "cpa-1"}])
    )
    mappings = client.list_certificate_mappings()
    assert mappings[0].cpa_id == "cpa-1"

    respx.delete(f"{API_BASE}/certificateMappings", params={"cpaId": "cpa-1"}).mock(return_value=Response(200))
    client.delete_certificate_mapping("cpa-1", source_b64)


@respx.mock
def test_ping(client):
    route = respx.post(f"{API_BASE}/ebms/ping/cpa-1/from/party-a/to/party-b").mock(return_value=Response(200))
    client.ping("cpa-1", "party-a", "party-b")
    assert route.called


@respx.mock
def test_send_message_returns_message_id(client):
    route = respx.post(f"{API_BASE}/ebms/messages").mock(return_value=Response(200, text="msg-123"))
    request = MessageRequest(
        properties=MessageRequestProperties(cpa_id="cpa-1", from_party_id="party-a", service="svc", action="act"),
        data_sources=[DataSource(content_type="text/plain", content=b"hello", name="doc.txt")],
    )
    message_id = client.send_message(request)
    assert message_id == "msg-123"

    sent_body = route.calls.last.request.content
    assert b'"cpaId":"cpa-1"' in sent_body
    assert b'"content":"' + base64.b64encode(b"hello") in sent_body
    assert b"fromRole" not in sent_body  # optional fields omitted when None


@respx.mock
def test_send_message_bad_request(client):
    respx.post(f"{API_BASE}/ebms/messages").mock(return_value=Response(400, text="Unknown cpaId"))
    request = MessageRequest(
        properties=MessageRequestProperties(cpa_id="bad", from_party_id="a", service="s", action="ac")
    )
    with pytest.raises(EbmsBadRequestError) as exc_info:
        client.send_message(request)
    assert "Unknown cpaId" in str(exc_info.value)


@respx.mock
def test_get_message_parses_response(client):
    payload = {
        "properties": {
            "cpaId": "cpa-1",
            "fromParty": {"partyId": "party-a", "role": "sender"},
            "toParty": {"partyId": "party-b", "role": "receiver"},
            "service": "svc",
            "action": "act",
            "timestamp": "2026-07-10T10:00:00Z",
            "conversationId": "conv-1",
            "messageId": "msg-123",
            "messageStatus": "RECEIVED",
        },
        "dataSources": [
            {"contentType": "text/plain", "content": base64.b64encode(b"hi").decode("ascii"), "name": "a.txt"}
        ],
    }
    respx.get(f"{API_BASE}/ebms/messages/msg-123", params={"process": "true"}).mock(
        return_value=Response(200, json=payload)
    )
    message = client.get_message("msg-123", process=True)
    assert message.properties.message_status == EbMSMessageStatus.RECEIVED
    assert message.properties.timestamp == datetime(2026, 7, 10, 10, 0, 0, tzinfo=UTC)
    assert message.data_sources[0].content == b"hi"


@respx.mock
def test_get_message_status(client):
    respx.get(f"{API_BASE}/ebms/messages/msg-123/status").mock(
        return_value=Response(200, json={"status": "DELIVERED", "timestamp": "2026-07-10T10:05:00Z"})
    )
    status = client.get_message_status("msg-123")
    assert status.status == EbMSMessageStatus.DELIVERED


@respx.mock
def test_list_unprocessed_message_ids_with_filter(client):
    route = respx.get(f"{API_BASE}/ebms/messages/unprocessed").mock(return_value=Response(200, json=["m1", "m2"]))
    result = client.list_unprocessed_message_ids(MessageFilter(cpa_id="cpa-1"), max_nr=10)
    assert result == ["m1", "m2"]
    request_url = route.calls.last.request.url
    assert request_url.params["cpaId"] == "cpa-1"
    assert request_url.params["maxNr"] == "10"


@respx.mock
def test_list_unprocessed_message_events_with_event_types(client):
    route = respx.get(f"{API_BASE}/ebms/events/unprocessed").mock(
        return_value=Response(200, json=[{"messageId": "m1", "type": "DELIVERED"}])
    )
    events = client.list_unprocessed_message_events(event_types=[MessageEventType.DELIVERED, MessageEventType.FAILED])
    assert events[0].type == MessageEventType.DELIVERED
    request_url = route.calls.last.request.url
    assert request_url.params.get_list("eventTypes") == ["DELIVERED", "FAILED"]


@respx.mock
def test_process_message_and_event(client):
    respx.patch(f"{API_BASE}/ebms/messages/msg-123").mock(return_value=Response(200))
    client.process_message("msg-123")

    respx.patch(f"{API_BASE}/ebms/events/msg-123").mock(return_value=Response(200))
    client.process_message_event("msg-123")


@respx.mock
def test_resend_message(client):
    respx.put(f"{API_BASE}/ebms/messages/msg-123").mock(return_value=Response(200, text="msg-456"))
    assert client.resend_message("msg-123") == "msg-456"


@respx.mock
def test_server_error_raises(client):
    respx.get(f"{API_BASE}/ebms/messages/msg-1/status").mock(return_value=Response(500, text="boom"))
    with pytest.raises(EbmsServerError) as exc_info:
        client.get_message_status("msg-1")
    assert exc_info.value.status_code == 500


@respx.mock
def test_connection_error_wrapped(client):
    import httpx

    respx.get(f"{API_BASE}/cpas").mock(side_effect=httpx.ConnectError("connection refused"))
    with pytest.raises(EbmsConnectionError):
        client.list_cpa_ids()


@respx.mock
def test_basic_auth_header_sent(client):
    route = respx.get(f"{API_BASE}/cpas").mock(return_value=Response(200, json=[]))
    client.list_cpa_ids()
    assert "Authorization" in route.calls.last.request.headers


def test_no_auth_client_omits_authorization_header():
    config = EbmsAdapterClientConfig(base_url=BASE_URL)
    with EbmsAdapterClient(config) as client, respx.mock:
        route = respx.get(f"{API_BASE}/cpas").mock(return_value=Response(200, json=[]))
        client.list_cpa_ids()
        assert "Authorization" not in route.calls.last.request.headers
