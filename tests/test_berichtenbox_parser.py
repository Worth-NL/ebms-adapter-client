from datetime import UTC, datetime
from pathlib import Path

import pytest

from ebms_adapter_client.berichtenbox import ParsedBericht, parse_berichten_verwerk_response

FIXTURES_DIR = Path(__file__).parent / "fixtures"

_BATCH_INFORMATIE_FIELDS = """
        <BerichtLeverancierCode>00000000000000000000</BerichtLeverancierCode>
        <AantalBerichtenGeenActieveBoxOfGeabonneertOpLeverancier>0</AantalBerichtenGeenActieveBoxOfGeabonneertOpLeverancier>
        <AantalBerichtenMetTechnischProbleem>0</AantalBerichtenMetTechnischProbleem>
        <AantalBerichtenBerichtTypeNietCorrect>0</AantalBerichtenBerichtTypeNietCorrect>
        <AantalBerichtenPublicatieDatumNietCorrect>0</AantalBerichtenPublicatieDatumNietCorrect>
        <AantalBerichtenAanmaakDatumNietCorrect>0</AantalBerichtenAanmaakDatumNietCorrect>
        <DatumOntvangen>2024-01-01T09:00:00.000Z</DatumOntvangen>
        <DatumVerwerkt>2024-01-01T09:01:30.000Z</DatumVerwerkt>
"""


def test_parse_berichten_verwerk_response_single_message():
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
    <ns0:BerichtVerwerkResponse xmlns:ns0="http://schemas.rdw.nl/GEB/BerichtVerwerkService/Types/2009/01"
                                 xmlns:ns1="http://schemas.rdw.nl/GEB/BerichtenProsessor/Bericht/Types/2009/01">
      <ns0:BatchInformatie>
        <ns0:BatchID>batch-1</ns0:BatchID>
        <ns0:TotaalAantalOntvangenBerichten>1</ns0:TotaalAantalOntvangenBerichten>
        <ns0:AantalBerichtenSuccesvolVerwerkt>1</ns0:AantalBerichtenSuccesvolVerwerkt>
        {_BATCH_INFORMATIE_FIELDS}
      </ns0:BatchInformatie>
      <ns0:Berichten>
        <ns1:Bericht>
          <ns1:BerichtID>11111111-1111-1111-1111-111111111111</ns1:BerichtID>
          <ns1:BerichtType>bericht</ns1:BerichtType>
          <ns1:VerwerkingsCode>00</ns1:VerwerkingsCode>
          <ns1:Stadium>NA</ns1:Stadium>
        </ns1:Bericht>
      </ns0:Berichten>
    </ns0:BerichtVerwerkResponse>"""

    batch = parse_berichten_verwerk_response(xml)

    assert batch.batch_id == "batch-1"
    assert batch.berichtleverancier_code == "00000000000000000000"
    assert batch.total_received == 1
    assert batch.successful_count == 1
    assert batch.batch_success is True
    assert batch.geen_actieve_box_of_geabonneerd_count == 0
    assert batch.technisch_probleem_count == 0
    assert batch.bericht_type_niet_correct_count == 0
    assert batch.publicatie_datum_niet_correct_count == 0
    assert batch.aanmaak_datum_niet_correct_count == 0
    assert batch.datum_ontvangen == datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)
    assert batch.datum_verwerkt == datetime(2024, 1, 1, 9, 1, 30, tzinfo=UTC)
    assert batch.messages == [
        ParsedBericht(
            message_id="11111111-1111-1111-1111-111111111111",
            process_code="00",
            bericht_type="bericht",
            stadium="NA",
        )
    ]


def test_parse_berichten_verwerk_response_multiple_messages_from_fixture():
    xml_bytes = (FIXTURES_DIR / "berichten_verwerk_response_sample.xml").read_bytes()

    batch = parse_berichten_verwerk_response(xml_bytes)

    assert batch.batch_id == "batch-123"
    assert batch.berichtleverancier_code == "00000000000000000000"
    assert batch.total_received == 2
    assert batch.successful_count == 2
    assert batch.batch_success is True
    assert batch.geen_actieve_box_of_geabonneerd_count == 0
    assert batch.technisch_probleem_count == 0
    assert batch.bericht_type_niet_correct_count == 0
    assert batch.publicatie_datum_niet_correct_count == 0
    assert batch.aanmaak_datum_niet_correct_count == 0
    assert batch.datum_ontvangen == datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)
    assert batch.datum_verwerkt == datetime(2024, 1, 1, 9, 1, 30, tzinfo=UTC)
    assert batch.messages == [
        ParsedBericht(
            message_id="11111111-1111-1111-1111-111111111111", process_code="00", bericht_type="bericht", stadium="NA"
        ),
        ParsedBericht(
            message_id="22222222-2222-2222-2222-222222222222", process_code="00", bericht_type="bericht", stadium="NA"
        ),
    ]


@pytest.mark.parametrize(
    ("total_received", "successful_count", "expected_success"),
    [
        (2, 2, True),
        (2, 1, False),
        (0, 0, False),
    ],
)
def test_parsed_batch_success_property(total_received, successful_count, expected_success):
    xml = f"""<BerichtVerwerkResponse xmlns="http://schemas.rdw.nl/GEB/BerichtVerwerkService/Types/2009/01">
      <BatchInformatie>
        <BatchID>batch-1</BatchID>
        <TotaalAantalOntvangenBerichten>{total_received}</TotaalAantalOntvangenBerichten>
        <AantalBerichtenSuccesvolVerwerkt>{successful_count}</AantalBerichtenSuccesvolVerwerkt>
        {_BATCH_INFORMATIE_FIELDS}
      </BatchInformatie>
      <Berichten/>
    </BerichtVerwerkResponse>"""

    batch = parse_berichten_verwerk_response(xml)

    assert batch.batch_success is expected_success
    assert batch.messages == []


def test_parse_berichten_verwerk_response_raises_on_unexpected_root():
    with pytest.raises(ValueError, match="BerichtVerwerkResponse"):
        parse_berichten_verwerk_response("<SomethingElse/>")


def test_parse_berichten_verwerk_response_raises_when_batch_informatie_missing():
    with pytest.raises(ValueError, match="BatchInformatie"):
        parse_berichten_verwerk_response(
            '<BerichtVerwerkResponse xmlns="http://schemas.rdw.nl/GEB/BerichtVerwerkService/Types/2009/01"/>'
        )
