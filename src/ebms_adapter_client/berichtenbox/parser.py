from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from xml.etree import ElementTree as ET

from defusedxml import ElementTree as DefusedET

_BATCH_INFORMATIE = "BatchInformatie"
_BERICHTEN = "Berichten"
_BERICHT = "Bericht"
_BERICHT_LEVERANCIER_CODE = "BerichtLeverancierCode"
_BATCH_ID = "BatchID"
_TOTAAL_AANTAL_ONTVANGEN_BERICHTEN = "TotaalAantalOntvangenBerichten"
_AANTAL_BERICHTEN_SUCCESVOL_VERWERKT = "AantalBerichtenSuccesvolVerwerkt"
_AANTAL_BERICHTEN_GEEN_ACTIEVE_BOX = "AantalBerichtenGeenActieveBoxOfGeabonneertOpLeverancier"
_AANTAL_BERICHTEN_MET_TECHNISCH_PROBLEEM = "AantalBerichtenMetTechnischProbleem"
_AANTAL_BERICHTEN_BERICHT_TYPE_NIET_CORRECT = "AantalBerichtenBerichtTypeNietCorrect"
_AANTAL_BERICHTEN_PUBLICATIE_DATUM_NIET_CORRECT = "AantalBerichtenPublicatieDatumNietCorrect"
_AANTAL_BERICHTEN_AANMAAK_DATUM_NIET_CORRECT = "AantalBerichtenAanmaakDatumNietCorrect"
_DATUM_ONTVANGEN = "DatumOntvangen"
_DATUM_VERWERKT = "DatumVerwerkt"
_BERICHT_ID = "BerichtID"
_BERICHT_TYPE = "BerichtType"
_VERWERKINGS_CODE = "VerwerkingsCode"
_STADIUM = "Stadium"


def _parse_datum(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@dataclass(frozen=True)
class ParsedBericht:
    message_id: str
    process_code: str
    bericht_type: str
    stadium: str


@dataclass(frozen=True)
class ParsedBerichtenBatch:
    batch_id: str
    berichtleverancier_code: str
    total_received: int
    successful_count: int
    geen_actieve_box_of_geabonneerd_count: int
    technisch_probleem_count: int
    bericht_type_niet_correct_count: int
    publicatie_datum_niet_correct_count: int
    aanmaak_datum_niet_correct_count: int
    datum_ontvangen: datetime
    datum_verwerkt: datetime
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

    Matches tag names by local name only (ignoring namespace prefixes) --
    confirmed against real BerichtVerwerkResponse envelopes from a live
    ebms-core deployment, which parsed without error. A live response's
    ``Bericht`` elements use the namespace
    ``http://schemas.rdw.nl/GEB/BerichtVerwerkService/BerichtResultaat/Types/2009/01``,
    not ``http://schemas.rdw.nl/GEB/BerichtenProsessor/Bericht/Types/2009/01``
    (the namespace this package's own request-side builder uses for its
    outbound ``Bericht`` elements, ``NS_BERICHT`` in ``berichtenbox/builder.py``)
    -- matching by local name only is what makes this robust to that
    difference, not a gap to close.
    """
    root = DefusedET.fromstring(xml_content)
    if "BerichtVerwerkResponse" not in _local_name(root.tag):
        raise ValueError(f"Unexpected root element '{root.tag}', expected a BerichtVerwerkResponse")

    batch_informatie = _find_by_local_name(root, _BATCH_INFORMATIE)
    if batch_informatie is None:
        raise ValueError(f"'{_BATCH_INFORMATIE}' not found in response")

    batch_id = _text_by_local_name(batch_informatie, _BATCH_ID)
    berichtleverancier_code = _text_by_local_name(batch_informatie, _BERICHT_LEVERANCIER_CODE)
    total_received = int(_text_by_local_name(batch_informatie, _TOTAAL_AANTAL_ONTVANGEN_BERICHTEN))
    successful_count = int(_text_by_local_name(batch_informatie, _AANTAL_BERICHTEN_SUCCESVOL_VERWERKT))
    geen_actieve_box_of_geabonneerd_count = int(
        _text_by_local_name(batch_informatie, _AANTAL_BERICHTEN_GEEN_ACTIEVE_BOX)
    )
    technisch_probleem_count = int(_text_by_local_name(batch_informatie, _AANTAL_BERICHTEN_MET_TECHNISCH_PROBLEEM))
    bericht_type_niet_correct_count = int(
        _text_by_local_name(batch_informatie, _AANTAL_BERICHTEN_BERICHT_TYPE_NIET_CORRECT)
    )
    publicatie_datum_niet_correct_count = int(
        _text_by_local_name(batch_informatie, _AANTAL_BERICHTEN_PUBLICATIE_DATUM_NIET_CORRECT)
    )
    aanmaak_datum_niet_correct_count = int(
        _text_by_local_name(batch_informatie, _AANTAL_BERICHTEN_AANMAAK_DATUM_NIET_CORRECT)
    )
    datum_ontvangen = _parse_datum(_text_by_local_name(batch_informatie, _DATUM_ONTVANGEN))
    datum_verwerkt = _parse_datum(_text_by_local_name(batch_informatie, _DATUM_VERWERKT))

    berichten = _find_by_local_name(root, _BERICHTEN)
    messages = []
    if berichten is not None:
        for bericht in _findall_by_local_name(berichten, _BERICHT):
            messages.append(
                ParsedBericht(
                    message_id=_text_by_local_name(bericht, _BERICHT_ID),
                    process_code=_text_by_local_name(bericht, _VERWERKINGS_CODE),
                    bericht_type=_text_by_local_name(bericht, _BERICHT_TYPE),
                    stadium=_text_by_local_name(bericht, _STADIUM),
                )
            )

    return ParsedBerichtenBatch(
        batch_id=batch_id,
        berichtleverancier_code=berichtleverancier_code,
        total_received=total_received,
        successful_count=successful_count,
        geen_actieve_box_of_geabonneerd_count=geen_actieve_box_of_geabonneerd_count,
        technisch_probleem_count=technisch_probleem_count,
        bericht_type_niet_correct_count=bericht_type_niet_correct_count,
        publicatie_datum_niet_correct_count=publicatie_datum_niet_correct_count,
        aanmaak_datum_niet_correct_count=aanmaak_datum_niet_correct_count,
        datum_ontvangen=datum_ontvangen,
        datum_verwerkt=datum_verwerkt,
        messages=messages,
    )
