from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from xml.etree import ElementTree as ET

from ebms_adapter_client.models import DataSource, MessageRequest, MessageRequestProperties

NS_BERICHTEN = "http://schemas.rdw.nl/GEB/BerichtVerwerkService/Types/2009/01"
NS_BERICHT = "http://schemas.rdw.nl/GEB/BerichtenProsessor/Bericht/Types/2009/01"

_DEFAULT_SUBJECT = "Berichtenboxbericht"
_DEFAULT_MESSAGE_TYPE = "bericht"
_DEFAULT_SOORT_GEBRUIKER = "Burger"
_DEFAULT_BIJLAGE_TYPE = "Pdf"


@dataclass(frozen=True)
class BerichtenboxAttachment:
    """``content`` is the attachment's raw (binary) bytes -- it is Base64-encoded
    when embedded into the ``Inhoud`` XML element, since XML text content
    cannot safely hold arbitrary binary data."""

    filename: str
    content: bytes
    content_type: str = _DEFAULT_BIJLAGE_TYPE
    description: str | None = None


@dataclass(frozen=True)
class BerichtenboxContractConfig:
    """Per-contract constants for the MijnOverheid Berichtenbox 2.0 GLOBE-R-BV
    integration. These vary by environment/contract, so they're supplied by
    the caller's own configuration rather than hardcoded here."""

    cpa_id: str
    from_role: str = "SR"
    service: str = "urn:osb:services:MIJNOVERHEID.ebMS.BB.2.0"
    action: str = "GLOBE-R-BV-Request"
    to_role: str = "SP"


def _sub(parent: ET.Element, tag: str, text: str) -> ET.Element:
    element = ET.SubElement(parent, tag)
    element.text = text
    return element


def build_berichten_xml(
    *,
    batch_id: str,
    notification_id: str,
    bsn: str,
    message: str,
    subject: str = _DEFAULT_SUBJECT,
    deliverer_id: str,
    message_type: str = _DEFAULT_MESSAGE_TYPE,
    attachments: list[BerichtenboxAttachment] | None = None,
) -> bytes:
    """Builds the ``Berichten``/``BerichtInformatie``/``Bijlagen`` business XML
    sent as the EBMS envelope's data source content.

    Uses ``xml.etree.ElementTree`` so all text content is correctly escaped
    (the reference Next.js implementation used unescaped string templating,
    which is not safe for arbitrary message/subject/bsn content). Returns raw
    UTF-8 XML bytes -- NOT Base64 -- since ``DataSource.to_dict()`` performs
    its own Base64 encoding of ``content``.
    """
    ET.register_namespace("", NS_BERICHTEN)
    # ElementTree reserves "ns\d+" prefixes for its own auto-generation, so a
    # literal "ns1" prefix (as used by the reference implementation) can't be
    # registered here. Namespace-aware XML consumers key off the URI, not the
    # prefix text, so this has no effect on interoperability.
    ET.register_namespace("bericht", NS_BERICHT)

    root = ET.Element(f"{{{NS_BERICHTEN}}}Berichten")

    batch_informatie = ET.SubElement(root, f"{{{NS_BERICHTEN}}}BatchInformatie")
    _sub(batch_informatie, f"{{{NS_BERICHTEN}}}BatchID", batch_id)
    _sub(batch_informatie, f"{{{NS_BERICHTEN}}}AanmaakDatum", datetime.now(UTC).isoformat())
    _sub(batch_informatie, f"{{{NS_BERICHTEN}}}BerichtLeverancierID", deliverer_id)

    bericht = ET.SubElement(root, f"{{{NS_BERICHT}}}Bericht")
    bericht_informatie = ET.SubElement(bericht, f"{{{NS_BERICHT}}}BerichtInformatie")
    _sub(bericht_informatie, f"{{{NS_BERICHT}}}BatchID", notification_id)
    _sub(bericht_informatie, f"{{{NS_BERICHT}}}BerichtID", notification_id)
    _sub(bericht_informatie, f"{{{NS_BERICHT}}}BerichtType", message_type)
    _sub(bericht_informatie, f"{{{NS_BERICHT}}}Onderwerp", subject)
    _sub(bericht_informatie, f"{{{NS_BERICHT}}}BerichtTekst", message)
    _sub(bericht_informatie, f"{{{NS_BERICHT}}}GebruikerID", bsn)
    _sub(bericht_informatie, f"{{{NS_BERICHT}}}SoortGebruiker", _DEFAULT_SOORT_GEBRUIKER)

    if attachments:
        bijlagen = ET.SubElement(bericht, f"{{{NS_BERICHT}}}Bijlagen")
        for index, attachment in enumerate(attachments, start=1):
            bijlage = ET.SubElement(bijlagen, f"{{{NS_BERICHT}}}Bijlage")
            _sub(bijlage, f"{{{NS_BERICHT}}}Inhoud", base64.b64encode(attachment.content).decode("ascii"))
            _sub(bijlage, f"{{{NS_BERICHT}}}BijlageType", attachment.content_type)
            _sub(bijlage, f"{{{NS_BERICHT}}}Omschrijving", attachment.description or attachment.filename)
            _sub(bijlage, f"{{{NS_BERICHT}}}Volgorde", str(index))

    return cast(bytes, ET.tostring(root, encoding="UTF-8", xml_declaration=True))


def build_message_request(
    *,
    contract: BerichtenboxContractConfig,
    from_party_id: str,
    to_party_id: str,
    notification_id: str,
    xml_content: bytes,
) -> MessageRequest:
    """Wraps ``build_berichten_xml``'s output into a ``MessageRequest`` ready
    to pass to ``EbmsAdapterClient.send_message``. ``xml_content`` must be raw
    bytes (not pre-Base64-encoded)."""
    properties = MessageRequestProperties(
        cpa_id=contract.cpa_id,
        from_party_id=from_party_id,
        service=contract.service,
        action=contract.action,
        from_role=contract.from_role,
        to_party_id=to_party_id,
        to_role=contract.to_role,
    )
    data_source = DataSource(
        content_type="text/xml",
        content=xml_content,
        name=f"bericht-{notification_id}.xml",
        content_id=notification_id,
    )
    return MessageRequest(properties=properties, data_sources=[data_source])
