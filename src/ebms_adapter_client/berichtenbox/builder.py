from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from xml.etree import ElementTree as ET

from ebms_adapter_client.exceptions import BerichtenboxValidationError
from ebms_adapter_client.models import DataSource, MessageRequest, MessageRequestProperties

NS_BERICHTEN = "http://schemas.rdw.nl/GEB/BerichtVerwerkService/Types/2009/01"
NS_BERICHT = "http://schemas.rdw.nl/GEB/BerichtenProsessor/Bericht/Types/2009/01"

_DEFAULT_SUBJECT = "Berichtenboxbericht"
_DEFAULT_MESSAGE_TYPE = "bericht"
_DEFAULT_SOORT_GEBRUIKER = "Burger"
_DEFAULT_BIJLAGE_TYPE = "Pdf"

# Constraints from Logius's "Technische Aansluithandleiding MijnOverheid
# Berichtenbox" (v1.6.3, section 5.3) and, for the attachment description,
# the 2022-04-06 update that raised it from 40 to 128 characters (see
# "Langere bestandsnaam mogelijk bij bijlage MijnOverheid Berichtenbox",
# logius.nl) -- confirming the source PDF predates that change.
MAX_ONDERWERP_LENGTH = 50
MAX_BERICHTTEKST_LENGTH = 4_000
MAX_OMSCHRIJVING_LENGTH = 128
GEBRUIKER_ID_LENGTH = 9
BERICHT_LEVERANCIER_ID_LENGTH = 20
MAX_PERSONALISED_ATTACHMENTS = 2
# 500 kB combined, measured before base64 encoding (which inflates size by
# ~33%) -- using the SI (1000-based) kB reading is the conservative choice,
# since it rejects slightly earlier than a 1024-based reading would.
MAX_PERSONALISED_ATTACHMENT_BYTES = 500_000


def _encode_line_breaks(text: str) -> str:
    """Berichtenbox requires line breaks in Berichttekst to be encoded as the
    literal four-character sequence ``\\r\\n`` (section 5.7) -- an embedded
    real CR/LF byte is valid XML but is not rendered as a line break by the
    Berichtenbox UI, so it must be rewritten here rather than left to the
    caller."""
    return text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\r\\n")


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


def _validate_berichten_xml_inputs(
    *,
    bsn: str,
    subject: str,
    encoded_message: str,
    deliverer_id: str,
    attachments: list[BerichtenboxAttachment],
) -> None:
    """Fails fast, before any network call, on any documented Berichtenbox
    constraint an outbound message would otherwise violate -- letting
    ebms-core's response ever tell us instead risks its parser also failing
    to extract our own BerichtID/BatchID, leaving the sending side with no
    way to correlate the rejection back to a specific message at all."""
    if not (len(bsn) == GEBRUIKER_ID_LENGTH and bsn.isdigit()):
        raise BerichtenboxValidationError(f"bsn (GebruikerID) must be exactly {GEBRUIKER_ID_LENGTH} digits: {bsn!r}")

    if not (len(deliverer_id) == BERICHT_LEVERANCIER_ID_LENGTH and deliverer_id.isdigit()):
        raise BerichtenboxValidationError(
            f"deliverer_id (BerichtLeverancierID) must be exactly {BERICHT_LEVERANCIER_ID_LENGTH} digits: "
            f"{deliverer_id!r}"
        )

    if len(subject) > MAX_ONDERWERP_LENGTH:
        raise BerichtenboxValidationError(
            f"subject (Onderwerp) must be at most {MAX_ONDERWERP_LENGTH} characters, got {len(subject)}"
        )

    if len(encoded_message) > MAX_BERICHTTEKST_LENGTH:
        raise BerichtenboxValidationError(
            f"message (Berichttekst) must be at most {MAX_BERICHTTEKST_LENGTH} characters after line-break "
            f"encoding, got {len(encoded_message)}"
        )

    if len(attachments) > MAX_PERSONALISED_ATTACHMENTS:
        raise BerichtenboxValidationError(
            f"a Berichtenbox message may have at most {MAX_PERSONALISED_ATTACHMENTS} personalised attachments, "
            f"got {len(attachments)}"
        )

    total_attachment_bytes = sum(len(attachment.content) for attachment in attachments)
    if total_attachment_bytes > MAX_PERSONALISED_ATTACHMENT_BYTES:
        raise BerichtenboxValidationError(
            f"combined attachment size must be at most {MAX_PERSONALISED_ATTACHMENT_BYTES} bytes before base64 "
            f"encoding, got {total_attachment_bytes}"
        )

    for attachment in attachments:
        description = attachment.description or attachment.filename
        if len(description) > MAX_OMSCHRIJVING_LENGTH:
            raise BerichtenboxValidationError(
                f"attachment description/filename (Omschrijving) must be at most {MAX_OMSCHRIJVING_LENGTH} "
                f"characters, got {len(description)!r} for {attachment.filename!r}"
            )


def build_berichten_xml(
    *,
    batch_id: str,
    bericht_id: str,
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

    Raises ``BerichtenboxValidationError`` if the inputs would violate a
    documented Berichtenbox constraint (field length/format, attachment
    count/size) -- callers should treat this as non-retryable, since nothing
    about the failure resolves by resending the same input.
    """
    attachments = attachments or []
    encoded_message = _encode_line_breaks(message)
    _validate_berichten_xml_inputs(
        bsn=bsn,
        subject=subject,
        encoded_message=encoded_message,
        deliverer_id=deliverer_id,
        attachments=attachments,
    )

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
    # Per Logius's "Technische Aansluithandleiding MijnOverheid Berichtenbox" (v1.6.3,
    # section 5.3): "Het betreffende BatchID moet worden herhaald in ieder individueel
    # bericht" -- the per-message BatchID must repeat the batch-level one, not the
    # per-message BerichtID.
    _sub(bericht_informatie, f"{{{NS_BERICHT}}}BatchID", batch_id)
    _sub(bericht_informatie, f"{{{NS_BERICHT}}}BerichtID", bericht_id)
    _sub(bericht_informatie, f"{{{NS_BERICHT}}}BerichtType", message_type)
    _sub(bericht_informatie, f"{{{NS_BERICHT}}}Onderwerp", subject)
    _sub(bericht_informatie, f"{{{NS_BERICHT}}}BerichtTekst", encoded_message)
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
    bericht_id: str,
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
        name=f"bericht-{bericht_id}.xml",
        content_id=bericht_id,
    )
    return MessageRequest(properties=properties, data_sources=[data_source])
