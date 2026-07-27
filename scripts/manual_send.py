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

Step 2 -- ``send``: builds the Berichtenbox XML and sends it, then makes a
short, best-effort attempt to spot the resulting message in
``/ebms/messages/unprocessed`` right away. Logius's technical connection
manual gives no fixed turnaround for the GLOBE-R-BV-Result receipt (unlike
AbonnementService's documented 4-hour SLA), so finding nothing yet is normal
-- re-run ``poll-unprocessed`` (Step 3) later instead of treating that as a
failure::

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

Step 3 -- ``poll-unprocessed``: the real status-retrieval mechanism (the
same one ``notifynl-api``'s ``messagebox_process_unprocessed_messages``
Celery task uses in production) -- lists unprocessed envelopes, fetches and
parses each one's ``BerichtVerwerkResponse`` XML, and prints the result.
Read-only by default (never calls ``PATCH .../messages/{id}``, i.e. never
marks an envelope processed), so it's safe to re-run repeatedly against a
shared pre-prod instance without racing the real Celery beat task or other
developers' in-flight tests. Pass ``--mark-processed`` only when you
deliberately want to drain a specific envelope::

    uv run python scripts/manual_send.py poll-unprocessed \\
        --base-url http://localhost:8080

Step 4 -- ``status`` (diagnostic only, expected to fail on this flow): calls
``GET /ebms/messages/{message_id}/status`` directly. Per
``eluinstra/ebms-core`` (branch ``ebms-core-2.20.x``), this does not read a
local delivery-status column -- ``EbMSControllerHandler.getMessageStatus``
sends a live, synchronous ebMS StatusRequest/StatusResponse SOAP round-trip
to the *counterparty's* own MSH (``deliveryManager.sendMessage``, the same
primitive ``ping`` uses), and even a valid response only ever carries the
coarse transport-level RECEIVED/PROCESSED/FORWARDED status, never
business-level delivery. Logius's own connection manual confirms this
split explicitly: sending an ebMS Acknowledgment does not mean a message was
correctly processed by the receiving side's software. On the GLOBE-R-BV push
flow, Logius's ebms-core does not answer this StatusRequest at all, so this
reliably raises ``EbmsServerError("No valid response received!")``
regardless of real delivery outcome -- use ``poll-unprocessed`` instead for
anything that matters::

    uv run python scripts/manual_send.py status \\
        --base-url http://localhost:8080 \\
        --message-id <message id returned by send>
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
from ebms_adapter_client.berichtenbox import ParsedBericht, parse_berichten_verwerk_response
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
    bericht_id = args.bericht_id or str(uuid.uuid4())
    batch_id = args.batch_id or str(uuid.uuid4())

    xml_content = build_berichten_xml(
        batch_id=batch_id,
        bericht_id=bericht_id,
        bsn=args.bsn,
        message=args.message,
        subject=args.subject,
        deliverer_id=args.deliverer_id,
    )
    message_request = build_message_request(
        contract=BerichtenboxContractConfig(cpa_id=args.cpa_id),
        from_party_id=args.from_party_id,
        to_party_id=args.to_party_id,
        bericht_id=bericht_id,
        xml_content=xml_content,
    )

    with EbmsAdapterClient(_build_config(args)) as client:
        message_id = client.send_message(message_request)
        print(f"sent: message_id={message_id} bericht_id={bericht_id}")
        _poll_for_bericht_result(client, bericht_id, attempts=args.attempts, delay_seconds=args.delay_seconds)
    return 0


def _find_bericht(client: EbmsAdapterClient, bericht_id: str) -> ParsedBericht | None:
    """Best-effort, read-only scan of the unprocessed envelope queue for a
    ``Bericht`` matching ``bericht_id``. Skips envelopes that fail to
    fetch or parse -- ``poll-unprocessed`` is the tool for surfacing those
    errors individually, this is just a quick "did it show up" check."""
    for envelope_id in client.list_unprocessed_message_ids():
        try:
            message = client.get_message(envelope_id)
            batch = parse_berichten_verwerk_response(message.data_sources[0].content)
        except Exception:  # noqa: S112 -- best-effort scan; poll-unprocessed reports per-envelope errors
            continue
        for bericht in batch.messages:
            if bericht.message_id == bericht_id:
                return bericht
    return None


def _poll_for_bericht_result(
    client: EbmsAdapterClient, bericht_id: str, *, attempts: int, delay_seconds: float
) -> None:
    for attempt in range(1, attempts + 1):
        bericht = _find_bericht(client, bericht_id)
        if bericht is not None:
            print(f"status: process_code={bericht.process_code} (found in unprocessed envelope queue)")
            return
        if attempt < attempts:
            time.sleep(delay_seconds)

    print(
        f"status: not seen yet after {attempts} attempt(s) -- this does NOT mean the send failed. "
        "Logius gives no fixed turnaround for this receipt; re-run `poll-unprocessed` later and look for "
        f"bericht_id={bericht_id}.",
        file=sys.stderr,
    )


def _run_poll_unprocessed(args: argparse.Namespace) -> int:
    with EbmsAdapterClient(_build_config(args)) as client:
        envelope_ids = client.list_unprocessed_message_ids()
        if not envelope_ids:
            print("no unprocessed envelopes.")
            return 0

        print(f"{len(envelope_ids)} unprocessed envelope(s):")
        for envelope_id in envelope_ids:
            print(f"\n--- envelope {envelope_id} ---")
            try:
                message = client.get_message(envelope_id)
                content = message.data_sources[0].content
            except Exception as exc:
                print(f"  failed to fetch: {exc}", file=sys.stderr)
                continue

            print(f"  raw content:\n{content.decode('utf-8', errors='replace')}")

            try:
                batch = parse_berichten_verwerk_response(content)
            except Exception as exc:
                print(f"  PARSE FAILED (BerichtVerwerkResponse shape mismatch?): {exc}", file=sys.stderr)
                continue

            print(
                f"  batch_id={batch.batch_id} total_received={batch.total_received} "
                f"successful_count={batch.successful_count} batch_success={batch.batch_success}"
            )
            for bericht in batch.messages:
                print(f"    message_id={bericht.message_id} process_code={bericht.process_code}")

            if args.mark_processed:
                client.process_message(envelope_id)
                print("  marked processed.")
    return 0


def _run_status(args: argparse.Namespace) -> int:
    """Diagnostic only -- see the ``status`` subcommand's docstring section
    (module-level, Step 4) for why this is expected to fail on the
    GLOBE-R-BV push flow."""
    with EbmsAdapterClient(_build_config(args)) as client:
        for attempt in range(1, args.attempts + 1):
            try:
                status = client.get_message_status(args.message_id)
            except EbmsServerError as exc:
                if attempt == args.attempts:
                    print(
                        f"status: unavailable after {args.attempts} attempts ({exc}) -- expected on the "
                        "GLOBE-R-BV push flow (see this command's --help); use `poll-unprocessed` instead",
                        file=sys.stderr,
                    )
                    return 0
                time.sleep(args.delay_seconds)
                continue
            print(f"status: {status.status.value} (timestamp={status.timestamp})")
            return 0
    return 0


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest="command", required=True)

    ping_parser = subparsers.add_parser("ping", help="Validate CPA/envelope party IDs -- no BSN required.")
    _add_connection_args(ping_parser)
    _add_envelope_args(ping_parser)
    ping_parser.set_defaults(func=_run_ping)

    send_parser = subparsers.add_parser(
        "send", help="Build, send, and make a best-effort check for a Berichtenbox message's result."
    )
    _add_connection_args(send_parser)
    _add_envelope_args(send_parser)
    send_parser.add_argument("--deliverer-id", required=True, help="BerichtLeverancierID (client-org OIN)")
    send_parser.add_argument("--bsn", required=True)
    send_parser.add_argument("--message", required=True)
    send_parser.add_argument("--subject", default="Berichtenboxbericht")
    send_parser.add_argument("--bericht-id", default=None, help="defaults to a generated UUID")
    send_parser.add_argument("--batch-id", default=None, help="defaults to a generated UUID")
    send_parser.add_argument("--attempts", type=int, default=3)
    send_parser.add_argument("--delay-seconds", type=float, default=1.0)
    send_parser.set_defaults(func=_run_send)

    poll_parser = subparsers.add_parser(
        "poll-unprocessed",
        help="List, fetch and parse unprocessed envelopes -- the real status-retrieval mechanism.",
    )
    _add_connection_args(poll_parser)
    poll_parser.add_argument(
        "--mark-processed",
        action="store_true",
        default=False,
        help="PATCH each envelope as processed after parsing it. Off by default: read-only, safe to "
        "re-run against a shared instance without racing the real Celery task.",
    )
    poll_parser.set_defaults(func=_run_poll_unprocessed)

    status_parser = subparsers.add_parser(
        "status",
        help="Diagnostic only: query GET .../status directly. Expected to fail on the GLOBE-R-BV push flow.",
    )
    _add_connection_args(status_parser)
    status_parser.add_argument("--message-id", required=True)
    status_parser.add_argument("--attempts", type=int, default=3)
    status_parser.add_argument("--delay-seconds", type=float, default=1.0)
    status_parser.set_defaults(func=_run_status)

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
