import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ebms_adapter_client import CpaParseError, CpaPartyId, parse_cpa_summary

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_CPA = (FIXTURES_DIR / "cpa_sample.xml").read_text()

SP_OIN = "00000001000000000001"
SR_OIN = "00000001000000000002"


def _without_embedded_certificates(cpa_xml: str) -> str:
    return re.sub(r"<ds:X509Certificate>[^<]*</ds:X509Certificate>", "", cpa_xml)


def test_parse_cpa_summary_reads_the_agreement():
    summary = parse_cpa_summary(SAMPLE_CPA)

    assert summary.cpa_id == f"EXAMPLE-EBMS-BB-2-0_{SP_OIN}-{SR_OIN}_0001"
    assert summary.status == "agreed"
    assert summary.start == datetime(2026, 11, 5, tzinfo=UTC)
    assert summary.end == datetime(2028, 3, 31, 13, 49, 59, tzinfo=UTC)
    assert [party.name for party in summary.parties] == ["Example Service Provider", "Example Service Requester"]


def test_parse_cpa_summary_accepts_bytes():
    assert parse_cpa_summary(SAMPLE_CPA.encode()).cpa_id == parse_cpa_summary(SAMPLE_CPA).cpa_id


def test_parse_cpa_summary_reads_each_party():
    requester = parse_cpa_summary(SAMPLE_CPA).parties[1]

    assert requester.party_ids == (CpaPartyId(value=SR_OIN, type="urn:osb:oin"),)
    assert requester.party_ids[0].qualified == f"urn:osb:oin:{SR_OIN}"
    assert requester.endpoints == ("https://ebms-sr.example.invalid/ebms",)
    assert requester.endpoint_hosts == ("ebms-sr.example.invalid",)

    (role,) = requester.collaboration_roles
    assert role.process == "MijnOverheid_BB_R"
    assert role.role == "SR"
    assert role.service == "MIJNOVERHEID.ebMS.BB.2.0"
    assert role.service_type == "urn:osb:services"
    assert role.can_send == ("GLOBE-R-A-Request", "GLOBE-R-BV-Request")
    assert role.can_receive == ("GLOBE-R-A-Result", "GLOBE-R-BV-Result")


def test_parse_cpa_summary_reads_certificates_from_the_embedded_certificate():
    provider, requester = parse_cpa_summary(SAMPLE_CPA).parties

    (provider_certificate,) = provider.certificates
    assert provider_certificate.cert_id == "SP_ServerCert"
    assert provider_certificate.subject == "O=Example,CN=sp.example.invalid"
    assert provider_certificate.issuer == "O=Example,CN=sp.example.invalid"
    assert provider_certificate.serial_number == "1001"
    assert provider_certificate.not_after == datetime(2028, 3, 31, 13, 49, 59, tzinfo=UTC)
    assert requester.certificates[0].not_after == datetime(2027, 1, 16, 12, tzinfo=UTC)


def test_parse_cpa_summary_falls_back_to_x509_data_names_without_an_embedded_certificate():
    (certificate,) = parse_cpa_summary(_without_embedded_certificates(SAMPLE_CPA)).parties[0].certificates

    assert certificate.subject == "CN=sp.example.invalid,O=Example"
    assert certificate.issuer == "CN=sp.example.invalid,O=Example"
    assert certificate.serial_number == "1001"
    assert certificate.not_after is None


@pytest.mark.parametrize("party_id", [SR_OIN, f"urn:osb:oin:{SR_OIN}"])
def test_find_party_matches_bare_and_qualified_ids(party_id):
    summary = parse_cpa_summary(SAMPLE_CPA)

    party = summary.find_party(party_id)

    assert party is summary.parties[1]
    assert summary.other_parties(party) == (summary.parties[0],)


def test_find_party_returns_none_for_an_unknown_party():
    assert parse_cpa_summary(SAMPLE_CPA).find_party("urn:osb:oin:99999999999999999999") is None


@pytest.mark.parametrize(
    ("action", "process", "expected"),
    [
        ("GLOBE-R-BV-Request", None, True),
        ("GLOBE-R-BV-Request", "MijnOverheid_BB_R", True),
        ("GLOBE-R-BV-Request", "MijnOverheid_BB", False),
        ("GLOBE-R-BV-Result", None, False),
    ],
)
def test_can_send(action, process, expected):
    requester = parse_cpa_summary(SAMPLE_CPA).parties[1]

    assert requester.can_send(action, process=process) is expected


@pytest.mark.parametrize(
    ("at", "expected"),
    [
        (datetime(2026, 11, 4, 23, 59, 59, tzinfo=UTC), False),
        (datetime(2026, 11, 5, tzinfo=UTC), True),
        (datetime(2028, 3, 31, 13, 49, 59, tzinfo=UTC), True),
        (datetime(2028, 3, 31, 13, 50, tzinfo=UTC), False),
    ],
)
def test_is_active(at, expected):
    assert parse_cpa_summary(SAMPLE_CPA).is_active(at) is expected


def test_naive_start_and_end_are_read_as_utc():
    cpa_xml = SAMPLE_CPA.replace("2026-11-05T00:00:00Z", "2026-11-05T00:00:00")

    assert parse_cpa_summary(cpa_xml).start == datetime(2026, 11, 5, tzinfo=UTC)


@pytest.mark.parametrize(
    ("cpa_xml", "message"),
    [
        ("<not-closed>", "not well-formed"),
        (
            '<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">]>'
            "<tp:CollaborationProtocolAgreement>&lol;</tp:CollaborationProtocolAgreement>",
            "not well-formed or safe",
        ),
        ("<Something/>", "Expected a CollaborationProtocolAgreement"),
        (SAMPLE_CPA.replace(' tp:cpaid="', ' tp:other="'), "no cpaid"),
        (SAMPLE_CPA.replace("<tp:Start>2026-11-05T00:00:00Z</tp:Start>", ""), "no Start"),
        (SAMPLE_CPA.replace("2028-03-31T13:49:59Z", "end of time"), "End is not a valid date-time"),
        (re.sub(r"<tp:PartyInfo .*?</tp:PartyInfo>", "", SAMPLE_CPA, flags=re.DOTALL), "no PartyInfo"),
        (re.sub(r"<ds:X509Certificate>[^<]*<", "<ds:X509Certificate>not base64!<", SAMPLE_CPA), "not a valid X.509"),
    ],
    ids=[
        "malformed",
        "entity-declaration",
        "wrong-root",
        "no-cpaid",
        "no-start",
        "bad-end",
        "no-parties",
        "bad-certificate",
    ],
)
def test_parse_cpa_summary_rejects(cpa_xml, message):
    with pytest.raises(CpaParseError, match=message):
        parse_cpa_summary(cpa_xml)
