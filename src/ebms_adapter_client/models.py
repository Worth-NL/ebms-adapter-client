from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class EbMSMessageStatus(StrEnum):
    """Mirrors ``nl.clockwork.ebms.EbMSMessageStatus``."""

    UNAUTHORIZED = "UNAUTHORIZED"
    NOT_RECOGNIZED = "NOT_RECOGNIZED"
    RECEIVED = "RECEIVED"
    PROCESSED = "PROCESSED"
    FORWARDED = "FORWARDED"
    FAILED = "FAILED"
    CREATED = "CREATED"
    DELIVERY_FAILED = "DELIVERY_FAILED"
    DELIVERED = "DELIVERED"
    EXPIRED = "EXPIRED"


class MessageEventType(StrEnum):
    """Mirrors ``nl.clockwork.ebms.common.event.MessageEventType``."""

    RECEIVED = "RECEIVED"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"


def _omit_none(data: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if value is not None}


def _parse_instant(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@dataclass
class Party:
    party_id: str
    role: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _omit_none({"partyId": self.party_id, "role": self.role})

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Party:
        return cls(party_id=data["partyId"], role=data.get("role"))


@dataclass
class DataSource:
    """A message payload/attachment. ``content`` is Base64-encoded on the wire."""

    content_type: str
    content: bytes
    name: str | None = None
    content_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _omit_none(
            {
                "name": self.name,
                "contentId": self.content_id,
                "contentType": self.content_type,
                "content": base64.b64encode(self.content).decode("ascii"),
            }
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DataSource:
        return cls(
            name=data.get("name"),
            content_id=data.get("contentId"),
            content_type=data["contentType"],
            content=base64.b64decode(data["content"]),
        )


@dataclass
class MessageRequestProperties:
    """Request-side message envelope, see ``MessageRequestProperties.java``."""

    cpa_id: str
    from_party_id: str
    service: str
    action: str
    from_role: str | None = None
    to_party_id: str | None = None
    to_role: str | None = None
    conversation_id: str | None = None
    message_id: str | None = None
    ref_to_message_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _omit_none(
            {
                "cpaId": self.cpa_id,
                "fromPartyId": self.from_party_id,
                "fromRole": self.from_role,
                "toPartyId": self.to_party_id,
                "toRole": self.to_role,
                "service": self.service,
                "action": self.action,
                "conversationId": self.conversation_id,
                "messageId": self.message_id,
                "refToMessageId": self.ref_to_message_id,
            }
        )


@dataclass
class MessageRequest:
    properties: MessageRequestProperties
    data_sources: list[DataSource] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "properties": self.properties.to_dict(),
            "dataSources": [data_source.to_dict() for data_source in self.data_sources],
        }


@dataclass
class MessageProperties:
    """Response-side message envelope, see ``MessageProperties.java``."""

    cpa_id: str
    from_party: Party
    to_party: Party
    service: str
    action: str
    timestamp: datetime | None
    conversation_id: str
    message_id: str
    message_status: EbMSMessageStatus
    ref_to_message_id: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MessageProperties:
        return cls(
            cpa_id=data["cpaId"],
            from_party=Party.from_dict(data["fromParty"]),
            to_party=Party.from_dict(data["toParty"]),
            service=data["service"],
            action=data["action"],
            timestamp=_parse_instant(data.get("timestamp")),
            conversation_id=data["conversationId"],
            message_id=data["messageId"],
            ref_to_message_id=data.get("refToMessageId"),
            message_status=EbMSMessageStatus(data["messageStatus"]),
        )


@dataclass
class Message:
    properties: MessageProperties
    data_sources: list[DataSource] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Message:
        return cls(
            properties=MessageProperties.from_dict(data["properties"]),
            data_sources=[DataSource.from_dict(item) for item in data.get("dataSources") or []],
        )


@dataclass
class MessageStatus:
    status: EbMSMessageStatus
    timestamp: datetime | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MessageStatus:
        return cls(status=EbMSMessageStatus(data["status"]), timestamp=_parse_instant(data.get("timestamp")))


@dataclass
class MessageEvent:
    message_id: str
    type: MessageEventType

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MessageEvent:
        return cls(message_id=data["messageId"], type=MessageEventType(data["type"]))


@dataclass
class MessageFilter:
    """Shared query filter for the ``.../unprocessed`` messages/events endpoints."""

    cpa_id: str | None = None
    from_party_id: str | None = None
    from_role: str | None = None
    to_party_id: str | None = None
    to_role: str | None = None
    service: str | None = None
    action: str | None = None
    conversation_id: str | None = None
    message_id: str | None = None
    ref_to_message_id: str | None = None

    def to_query_params(self) -> dict[str, str]:
        return _omit_none(
            {
                "cpaId": self.cpa_id,
                "fromPartyId": self.from_party_id,
                "fromRole": self.from_role,
                "toPartyId": self.to_party_id,
                "toRole": self.to_role,
                "service": self.service,
                "action": self.action,
                "conversationId": self.conversation_id,
                "messageId": self.message_id,
                "refToMessageId": self.ref_to_message_id,
            }
        )


@dataclass
class URLMapping:
    source: str
    destination: str

    def to_dict(self) -> dict[str, Any]:
        return {"source": self.source, "destination": self.destination}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> URLMapping:
        return cls(source=data["source"], destination=data["destination"])


@dataclass
class CertificateMapping:
    """``source``/``destination`` are Base64-encoded DER X.509 certificates."""

    source: str
    destination: str
    cpa_id: str

    def to_dict(self) -> dict[str, Any]:
        return {"source": self.source, "destination": self.destination, "cpaId": self.cpa_id}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CertificateMapping:
        return cls(source=data["source"], destination=data["destination"], cpa_id=data["cpaId"])
