"""Manual CLI for exercising ``EbmsAdapterClient`` against a real ebms-core instance.

This is a developer tool, not part of the published package (excluded from
packaging by ``[tool.setuptools.packages.find] where = ["src"]`` in
pyproject.toml) and not part of the test suite (``testpaths = ["tests"]``).
It deliberately takes every identifier as a CLI argument with no hardcoded
defaults -- this package intentionally has no application-specific code (see
CONTRIBUTING.md), so any real CPA/OIN/BSN values are supplied by the caller
at invocation time, never baked into the repo.

Manual testing against a real ebms-core
----------------------------------------
Reaching a test-cluster ebms-core instance requires a ``kubectl
port-forward`` to the relevant namespace/service first, e.g.::

    kubectl port-forward -n <namespace> svc/<ebms-core-service> 8080:8080

Step 1 -- ``ping``: validates the CPA/envelope party IDs against the real
adapter with no BSN or deliverer OIN involved at all::

    uv run python scripts/manual_send.py ping \\
        --base-url http://localhost:8080 \\
        --cpa-id <pre-prod cpa id> \\
        --from-party-id urn:osb:oin:<worth ventures oin> \\
        --to-party-id urn:osb:oin:<logius oin>

Step 2 -- ``send``: builds the Berichtenbox XML, sends it, and polls the
resulting message status::

    uv run python scripts/manual_send.py send \\
        --base-url http://localhost:8080 \\
        --cpa-id <pre-prod cpa id> \\
        --from-party-id urn:osb:oin:<worth ventures oin> \\
        --to-party-id urn:osb:oin:<logius oin> \\
        --deliverer-id <client org oin, no prefix> \\
        --bsn <test bsn> \\
        --message "test message"

Note the ``urn:osb:oin:`` prefix on --from-party-id/--to-party-id: these are
the CPA's registered PartyId values, and ebms-core matches them literally --
a bare OIN with no prefix will fail CPA party lookup (EbmsServerError:
"No fromParty found for cpaId=..."), even though the CPA itself resolves.
--deliverer-id (BerichtLeverancierID) is a separate, body-level field and is
NOT prefixed -- it's the bare client-org OIN.
"""

from __future__ import annotations

import argparse
import sys
import time
import uuid

from ebms_adapter_client import (
    EbmsAdapterClient,
    EbmsAdapterClientConfig,
    EbmsAdapterError,
    EbmsServerError,
)
from ebms_adapter_client.berichtenbox.builder import (
    BerichtenboxContractConfig,
    build_berichten_xml,
    build_message_request,
)


def _add_connection_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--base-url", default="http://localhost:8080", help="URL to ebms-core instance")
    parser.add_argument("--username", default=None, help="omit if the server runs without --authentication")
    parser.add_argument("--password", default=None)
    verify_ssl = parser.add_mutually_exclusive_group()
    verify_ssl.add_argument("--verify-ssl", dest="verify_ssl", action="store_true", default=True)
    verify_ssl.add_argument("--no-verify-ssl", dest="verify_ssl", action="store_false")


def _add_envelope_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--cpa-id", required=True)
    parser.add_argument("--from-party-id", required=True)
    parser.add_argument("--to-party-id", required=True)


def _build_config(args: argparse.Namespace) -> EbmsAdapterClientConfig:
    return EbmsAdapterClientConfig(
        base_url=args.base_url,
        username=args.username,
        password=args.password,
        verify_ssl=args.verify_ssl,
    )


def _run_ping(args: argparse.Namespace) -> int:
    with EbmsAdapterClient(_build_config(args)) as client:
        client.ping(cpa_id=args.cpa_id, from_party_id=args.from_party_id, to_party_id=args.to_party_id)
    print("ping OK: CPA and envelope party IDs are accepted by the real ebms-core.")
    return 0


def _run_send(args: argparse.Namespace) -> int:
    notification_id = args.notification_id or str(uuid.uuid4())
    batch_id = args.batch_id or str(uuid.uuid4())

    xml_content = build_berichten_xml(
        batch_id=batch_id,
        notification_id=notification_id,
        bsn=args.bsn,
        message=args.message,
        subject=args.subject,
        deliverer_id=args.deliverer_id,
    )
    message_request = build_message_request(
        contract=BerichtenboxContractConfig(cpa_id=args.cpa_id),
        from_party_id=args.from_party_id,
        to_party_id=args.to_party_id,
        notification_id=notification_id,
        xml_content=xml_content,
    )

    with EbmsAdapterClient(_build_config(args)) as client:
        message_id = client.send_message(message_request)
        print(f"sent: message_id={message_id}")
        _poll_status(client, message_id)
    return 0


def _poll_status(client: EbmsAdapterClient, message_id: str, *, attempts: int = 3, delay_seconds: float = 1.0) -> None:
    """Best-effort only: on at least one observed ebms-core deployment, GET
    .../status consistently raises EbmsServerError("No valid response
    received!") for this GLOBE-R-BV push flow, even for messages confirmed
    delivered (SOAP Acknowledgment + StatusCode=204 in the adapter's own
    logs, and arrival in the recipient's pre-production berichtenbox inbox).
    So a failure here is NOT evidence the send failed -- this endpoint just
    doesn't appear to return a valid status for this flow on that
    deployment. Treat the adapter logs / recipient inbox as the source of
    truth for delivery confirmation, not this call."""
    for attempt in range(1, attempts + 1):
        try:
            status = client.get_message_status(message_id)
        except EbmsServerError as exc:
            if attempt == attempts:
                print(
                    f"status: unavailable after {attempts} attempts ({exc}) -- this does NOT necessarily mean "
                    "the send failed; check the adapter logs or the recipient's berichtenbox inbox instead",
                    file=sys.stderr,
                )
                return
            time.sleep(delay_seconds)
            continue
        print(f"status: {status.status.value} (timestamp={status.timestamp})")
        return


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest="command", required=True)

    ping_parser = subparsers.add_parser("ping", help="Validate CPA/envelope party IDs -- no BSN required.")
    _add_connection_args(ping_parser)
    _add_envelope_args(ping_parser)
    ping_parser.set_defaults(func=_run_ping)

    send_parser = subparsers.add_parser("send", help="Build, send, and poll the status of a Berichtenbox message.")
    _add_connection_args(send_parser)
    _add_envelope_args(send_parser)
    send_parser.add_argument("--deliverer-id", required=True, help="BerichtLeverancierID (client-org OIN)")
    send_parser.add_argument("--bsn", required=True)
    send_parser.add_argument("--message", required=True)
    send_parser.add_argument("--subject", default="Berichtenboxbericht")
    send_parser.add_argument("--notification-id", default=None, help="defaults to a generated UUID")
    send_parser.add_argument("--batch-id", default=None, help="defaults to a generated UUID")
    send_parser.set_defaults(func=_run_send)

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    try:
        return int(args.func(args))
    except EbmsAdapterError as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        if exc.response_body:
            print(f"response body: {exc.response_body}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
