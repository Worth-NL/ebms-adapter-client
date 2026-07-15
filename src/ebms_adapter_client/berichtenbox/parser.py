from __future__ import annotations

from dataclasses import dataclass
from xml.etree import ElementTree as ET

from defusedxml import ElementTree as DefusedET

_BATCH_INFORMATIE = "BatchInformatie"
_BERICHTEN = "Berichten"
_BERICHT = "Bericht"
_BATCH_ID = "BatchID"
_TOTAAL_AANTAL_ONTVANGEN_BERICHTEN = "TotaalAantalOntvangenBerichten"
_AANTAL_BERICHTEN_SUCCESVOL_VERWERKT = "AantalBerichtenSuccesvolVerwerkt"
_BERICHT_ID = "BerichtID"
_VERWERKINGS_CODE = "VerwerkingsCode"


@dataclass(frozen=True)
class ParsedBericht:
    message_id: str
    process_code: str


@dataclass(frozen=True)
class ParsedBerichtenBatch:
    batch_id: str
    total_received: int
    successful_count: int
    messages: list[ParsedBericht]

    @property
    def batch_success(self) -> bool:
        return self.total_received > 0 and self.total_received == self.successful_count


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _find_by_local_name(parent: ET.Element, local_name: str) -> ET.Element | None:
    for child in parent:
        if _local_name(child.tag) == local_name:
            return child
    return None


def _findall_by_local_name(parent: ET.Element, local_name: str) -> list[ET.Element]:
    return [child for child in parent if _local_name(child.tag) == local_name]


def _text_by_local_name(parent: ET.Element, local_name: str) -> str:
    element = _find_by_local_name(parent, local_name)
    if element is None or element.text is None:
        raise ValueError(f"'{local_name}' not found in '{_local_name(parent.tag)}'")
    return element.text


def parse_berichten_verwerk_response(xml_content: bytes | str) -> ParsedBerichtenBatch:
    """Parses a ``BerichtVerwerkResponse`` document (as returned in a
    ``Message``'s ``data_sources[0].content``) into a :class:`ParsedBerichtenBatch`.

    Matches tag names by local name only (ignoring namespace prefixes), since
    only the *request* schema's namespaces were confirmed from the reference
    implementation -- the *response* schema's exact namespace was not
    available at implementation time.

    TODO(verify): confirm the exact BerichtVerwerkResponse XSD/namespace
    against a live or sample ebms-core response before go-live. Until then,
    this is validated only against the hand-authored fixture in
    tests/fixtures/berichten_verwerk_response_sample.xml.
    """
    root = DefusedET.fromstring(xml_content)
    if "BerichtVerwerkResponse" not in _local_name(root.tag):
        raise ValueError(f"Unexpected root element '{root.tag}', expected a BerichtVerwerkResponse")

    batch_informatie = _find_by_local_name(root, _BATCH_INFORMATIE)
    if batch_informatie is None:
        raise ValueError(f"'{_BATCH_INFORMATIE}' not found in response")

    batch_id = _text_by_local_name(batch_informatie, _BATCH_ID)
    total_received = int(_text_by_local_name(batch_informatie, _TOTAAL_AANTAL_ONTVANGEN_BERICHTEN))
    successful_count = int(_text_by_local_name(batch_informatie, _AANTAL_BERICHTEN_SUCCESVOL_VERWERKT))

    berichten = _find_by_local_name(root, _BERICHTEN)
    messages = []
    if berichten is not None:
        for bericht in _findall_by_local_name(berichten, _BERICHT):
            messages.append(
                ParsedBericht(
                    message_id=_text_by_local_name(bericht, _BERICHT_ID),
                    process_code=_text_by_local_name(bericht, _VERWERKINGS_CODE),
                )
            )

    return ParsedBerichtenBatch(
        batch_id=batch_id,
        total_received=total_received,
        successful_count=successful_count,
        messages=messages,
    )
