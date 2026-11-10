"""Read-only summary of an ebXML Collaboration-Protocol Agreement (CPPA 2.0).

``parse_cpa_summary`` pulls out what a consumer needs to decide whether a CPA is the one it means to use: who the
parties are, which actions each may send or receive, where each party's messages are delivered and which certificates
it presents. It does not validate the CPA; ``EbmsAdapterClient.validate_cpa`` asks ebms-core to do that.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

from cryptography import x509
from defusedxml import DefusedXmlException
from defusedxml import ElementTree as DefusedET


class CpaParseError(ValueError):
    """The document is not a CPA this parser can summarise (malformed XML, or a required element is missing)."""


@dataclass(frozen=True)
class CpaPartyId:
    value: str
    type: str | None = None

    @property
    def qualified(self) -> str:
        """The id as ebms-core expects it in a message request: ``<type>:<value>``, or the bare value if untyped."""
        return f"{self.type}:{self.value}" if self.type else self.value


@dataclass(frozen=True)
class CpaCertificate:
    cert_id: str
    subject: str | None
    issuer: str | None
    serial_number: str | None
    not_after: datetime | None


@dataclass(frozen=True)
class CpaCollaborationRole:
    process: str | None
    role: str | None
    service: str | None
    service_type: str | None
    can_send: tuple[str, ...]
    can_receive: tuple[str, ...]


@dataclass(frozen=True)
class CpaParty:
    name: str | None
    party_ids: tuple[CpaPartyId, ...]
    collaboration_roles: tuple[CpaCollaborationRole, ...]
    endpoints: tuple[str, ...]
    certificates: tuple[CpaCertificate, ...]

    @property
    def endpoint_hosts(self) -> tuple[str, ...]:
        return tuple(host for host in (urlsplit(endpoint).hostname for endpoint in self.endpoints) if host)

    def can_send(self, action: str, *, process: str | None = None) -> bool:
        return any(
            action in role.can_send for role in self.collaboration_roles if process is None or role.process == process
        )

    def has_party_id(self, party_id: str) -> bool:
        """Matches either the bare value or the ``<type>:<value>`` form."""
        return any(party_id in (candidate.value, candidate.qualified) for candidate in self.party_ids)


@dataclass(frozen=True)
class CpaSummary:
    cpa_id: str
    status: str | None
    start: datetime
    end: datetime
    parties: tuple[CpaParty, ...]

    def is_active(self, at: datetime) -> bool:
        return self.start <= at <= self.end

    def find_party(self, party_id: str) -> CpaParty | None:
        return next((party for party in self.parties if party.has_party_id(party_id)), None)

    def other_parties(self, party: CpaParty) -> tuple[CpaParty, ...]:
        return tuple(other for other in self.parties if other is not party)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _attr(element: ET.Element, local_name: str) -> str | None:
    """Attribute by local name: CPPA attributes are namespace-qualified (``tp:cpaid``)."""
    for key, value in element.attrib.items():
        if _local_name(key) == local_name:
            return value
    return None


def _children(parent: ET.Element, local_name: str) -> list[ET.Element]:
    return [child for child in parent if _local_name(child.tag) == local_name]


def _child(parent: ET.Element, local_name: str) -> ET.Element | None:
    return next(iter(_children(parent, local_name)), None)


def _descendants(parent: ET.Element, local_name: str) -> list[ET.Element]:
    return [element for element in parent.iter() if _local_name(element.tag) == local_name]


def _text(element: ET.Element | None) -> str | None:
    if element is None or element.text is None:
        return None
    return element.text.strip() or None


def _parse_datetime(value: str | None, field: str) -> datetime:
    if not value:
        raise CpaParseError(f"CPA has no {field}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CpaParseError(f"CPA {field} is not a valid date-time: {value!r}") from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _parse_certificate(element: ET.Element) -> CpaCertificate:
    x509_data = next(iter(_descendants(element, "X509Data")), None)
    subject = issuer = serial_number = None
    not_after = None
    if x509_data is not None:
        subject = _text(_child(x509_data, "X509SubjectName"))
        issuer_serial = _child(x509_data, "X509IssuerSerial")
        if issuer_serial is not None:
            issuer = _text(_child(issuer_serial, "X509IssuerName"))
            serial_number = _text(_child(issuer_serial, "X509SerialNumber"))
        encoded = _text(_child(x509_data, "X509Certificate"))
        if encoded:
            try:
                certificate = x509.load_der_x509_certificate(base64.b64decode("".join(encoded.split()), validate=True))
            except (binascii.Error, ValueError) as exc:
                raise CpaParseError(
                    f"Certificate {_attr(element, 'certId')!r} is not a valid X.509 certificate"
                ) from exc
            # The embedded certificate is authoritative; the X509Data names are only descriptive copies of it.
            subject = certificate.subject.rfc4514_string()
            issuer = certificate.issuer.rfc4514_string()
            serial_number = str(certificate.serial_number)
            not_after = certificate.not_valid_after_utc
    return CpaCertificate(
        cert_id=_attr(element, "certId") or "",
        subject=subject,
        issuer=issuer,
        serial_number=serial_number,
        not_after=not_after,
    )


def _actions(parent: ET.Element | None) -> tuple[str, ...]:
    if parent is None:
        return ()
    return tuple(
        action for binding in _children(parent, "ThisPartyActionBinding") if (action := _attr(binding, "action"))
    )


def _parse_collaboration_role(element: ET.Element) -> CpaCollaborationRole:
    process = _child(element, "ProcessSpecification")
    role = _child(element, "Role")
    binding = _child(element, "ServiceBinding")
    service = _child(binding, "Service") if binding is not None else None
    return CpaCollaborationRole(
        process=_attr(process, "name") if process is not None else None,
        role=_attr(role, "name") if role is not None else None,
        service=_text(service),
        service_type=_attr(service, "type") if service is not None else None,
        can_send=(
            tuple(a for can_send in _children(binding, "CanSend") for a in _actions(can_send))
            if binding is not None
            else ()
        ),
        can_receive=(
            tuple(a for can_receive in _children(binding, "CanReceive") for a in _actions(can_receive))
            if binding is not None
            else ()
        ),
    )


def _parse_party(element: ET.Element) -> CpaParty:
    party_ids = tuple(
        CpaPartyId(value=value, type=_attr(party_id, "type"))
        for party_id in _children(element, "PartyId")
        if (value := _text(party_id))
    )
    endpoints = tuple(uri for endpoint in _descendants(element, "Endpoint") if (uri := _attr(endpoint, "uri")))
    return CpaParty(
        name=_attr(element, "partyName"),
        party_ids=party_ids,
        collaboration_roles=tuple(_parse_collaboration_role(role) for role in _children(element, "CollaborationRole")),
        endpoints=tuple(dict.fromkeys(endpoints)),
        certificates=tuple(_parse_certificate(certificate) for certificate in _children(element, "Certificate")),
    )


def parse_cpa_summary(cpa_xml: str | bytes) -> CpaSummary:
    """Summarises a CPPA 2.0 ``CollaborationProtocolAgreement``.

    Raises ``CpaParseError`` when the XML is malformed, uses forbidden constructs (entity expansion, external
    references) or lacks the CPA id, Start/End or parties.
    """
    try:
        root = DefusedET.fromstring(cpa_xml)
    except (ET.ParseError, DefusedXmlException) as exc:
        raise CpaParseError(f"CPA is not well-formed or safe XML: {exc}") from exc

    if _local_name(root.tag) != "CollaborationProtocolAgreement":
        raise CpaParseError(f"Expected a CollaborationProtocolAgreement, got {_local_name(root.tag)!r}")

    cpa_id = _attr(root, "cpaid")
    if not cpa_id:
        raise CpaParseError("CPA has no cpaid")

    status = _child(root, "Status")
    parties = tuple(_parse_party(party) for party in _children(root, "PartyInfo"))
    if not parties:
        raise CpaParseError("CPA has no PartyInfo")

    return CpaSummary(
        cpa_id=cpa_id,
        status=_attr(status, "value") if status is not None else None,
        start=_parse_datetime(_text(_child(root, "Start")), "Start"),
        end=_parse_datetime(_text(_child(root, "End")), "End"),
        parties=parties,
    )
