import base64
from xml.etree import ElementTree as ET

from ebms_adapter_client.berichtenbox import (
    BerichtenboxAttachment,
    BerichtenboxContractConfig,
    build_berichten_xml,
    build_message_request,
)
from ebms_adapter_client.berichtenbox.builder import NS_BERICHT, NS_BERICHTEN


def _parse(xml_bytes: bytes) -> ET.Element:
    return ET.fromstring(xml_bytes)


def _find(root: ET.Element, ns: str, local_name: str) -> ET.Element:
    element = root.find(f".//{{{ns}}}{local_name}")
    assert element is not None, f"{local_name} not found"
    return element


def test_build_berichten_xml_escapes_special_characters():
    xml_bytes = build_berichten_xml(
        batch_id="batch-1",
        notification_id="notif-1",
        bsn="123456789",
        message='Tom & Jerry <said> "hello"',
        subject="Test & <subject>",
        deliverer_id="00000003803078680000",
    )
    root = _parse(xml_bytes)
    bericht_tekst = _find(root, NS_BERICHT, "BerichtTekst")
    onderwerp = _find(root, NS_BERICHT, "Onderwerp")
    assert bericht_tekst.text == 'Tom & Jerry <said> "hello"'
    assert onderwerp.text == "Test & <subject>"
    # confirm it round-trips through actual escaped XML on the wire
    assert b"&amp;" in xml_bytes
    assert b"&lt;said&gt;" in xml_bytes


def test_build_berichten_xml_omits_bijlagen_when_no_attachments():
    xml_bytes = build_berichten_xml(
        batch_id="batch-1",
        notification_id="notif-1",
        bsn="123456789",
        message="hello",
        deliverer_id="00000003803078680000",
    )
    root = _parse(xml_bytes)
    assert root.find(f".//{{{NS_BERICHT}}}Bijlagen") is None


def test_build_berichten_xml_includes_multiple_attachments_in_order():
    attachments = [
        BerichtenboxAttachment(filename="a.pdf", content=b"content-a"),
        BerichtenboxAttachment(filename="b.pdf", content=b"content-b", description="Bijlage B"),
    ]
    xml_bytes = build_berichten_xml(
        batch_id="batch-1",
        notification_id="notif-1",
        bsn="123456789",
        message="hello",
        deliverer_id="00000003803078680000",
        attachments=attachments,
    )
    root = _parse(xml_bytes)
    bijlagen = _find(root, NS_BERICHT, "Bijlagen").findall(f"{{{NS_BERICHT}}}Bijlage")
    assert len(bijlagen) == 2

    assert bijlagen[0].find(f"{{{NS_BERICHT}}}Volgorde").text == "1"
    assert bijlagen[0].find(f"{{{NS_BERICHT}}}Omschrijving").text == "a.pdf"
    assert bijlagen[0].find(f"{{{NS_BERICHT}}}BijlageType").text == "Pdf"
    assert base64.b64decode(bijlagen[0].find(f"{{{NS_BERICHT}}}Inhoud").text) == b"content-a"

    assert bijlagen[1].find(f"{{{NS_BERICHT}}}Volgorde").text == "2"
    assert bijlagen[1].find(f"{{{NS_BERICHT}}}Omschrijving").text == "Bijlage B"
    assert base64.b64decode(bijlagen[1].find(f"{{{NS_BERICHT}}}Inhoud").text) == b"content-b"


def test_build_berichten_xml_default_message_type_and_subject():
    xml_bytes = build_berichten_xml(
        batch_id="batch-1",
        notification_id="notif-1",
        bsn="123456789",
        message="hello",
        deliverer_id="00000003803078680000",
    )
    root = _parse(xml_bytes)
    assert _find(root, NS_BERICHT, "BerichtType").text == "bericht"
    assert _find(root, NS_BERICHT, "Onderwerp").text == "Berichtenboxbericht"
    assert _find(root, NS_BERICHT, "SoortGebruiker").text == "Burger"


def test_build_berichten_xml_inner_batch_id_is_notification_id_outer_is_batch_id():
    xml_bytes = build_berichten_xml(
        batch_id="outer-batch-id",
        notification_id="the-notification-id",
        bsn="123456789",
        message="hello",
        deliverer_id="00000003803078680000",
    )
    root = _parse(xml_bytes)
    outer_batch_id = _find(root, NS_BERICHTEN, "BatchID")
    inner_batch_id = _find(root, NS_BERICHT, "BatchID")
    bericht_id = _find(root, NS_BERICHT, "BerichtID")
    assert outer_batch_id.text == "outer-batch-id"
    assert inner_batch_id.text == "the-notification-id"
    assert bericht_id.text == "the-notification-id"


def test_build_message_request_wraps_properties_and_datasource():
    contract = BerichtenboxContractConfig(cpa_id="MIJNOVERHEID-EBMS-BB-2-0_example")
    xml_content = b"<Berichten/>"
    message_request = build_message_request(
        contract=contract,
        from_party_id="urn:osb:oin:00000003803078680000",
        to_party_id="urn:osb:oin:00000004003214345001",
        notification_id="notif-1",
        xml_content=xml_content,
    )
    payload = message_request.to_dict()

    assert payload["properties"] == {
        "cpaId": "MIJNOVERHEID-EBMS-BB-2-0_example",
        "fromPartyId": "urn:osb:oin:00000003803078680000",
        "fromRole": "SR",
        "toPartyId": "urn:osb:oin:00000004003214345001",
        "toRole": "SP",
        "service": "urn:osb:services:MIJNOVERHEID.ebMS.BB.2.0",
        "action": "GLOBE-R-BV-Request",
    }
    assert len(payload["dataSources"]) == 1
    data_source = payload["dataSources"][0]
    assert data_source["name"] == "bericht-notif-1.xml"
    assert data_source["contentId"] == "notif-1"
    assert data_source["contentType"] == "text/xml"
    assert base64.b64decode(data_source["content"]) == xml_content
