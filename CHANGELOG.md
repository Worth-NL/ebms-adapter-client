# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2026-07-24

### Added

- `BerichtenboxValidationError`, raised by `build_berichten_xml` before any
  network call if the inputs would violate a documented Berichtenbox
  constraint: BSN (`GebruikerID`)/`BerichtLeverancierID` format, subject
  (`Onderwerp`)/message (`Berichttekst`) length, or attachment count/size.
- `build_berichten_xml` now encodes embedded line breaks in `Berichttekst`
  as the literal `\r\n` sequence Berichtenbox requires.

### Changed

- **Breaking**: `build_berichten_xml` and `build_message_request`'s
  `notification_id` parameter is renamed to `bericht_id`, matching
  Logius's own `BerichtID` field instead of a NotifyNL-domain term -- this
  package is a generic `ebms-core` client, not NotifyNL-specific.
- Fixed the per-message `BerichtInformatie/BatchID` element to repeat the
  batch-level `batch_id` instead of the message id, per the Technische
  Aansluithandleiding MijnOverheid Berichtenbox (v1.6.3, section 5.3).

## [0.2.0] - 2026-07-16

### Added

- `ParsedBerichtenBatch` now carries `berichtleverancier_code`, the five
  per-failure-reason batch counts, and `datum_ontvangen`/`datum_verwerkt` --
  fields confirmed present on every real `BerichtVerwerkResponse` envelope
  but previously discarded.
- `ParsedBericht` now carries `bericht_type` and `stadium` (the processing
  phase a failure was detected in), likewise confirmed present but
  previously discarded.

### Changed

- **Breaking for direct construction**: `ParsedBerichtenBatch` and
  `ParsedBericht` gained new required fields (see Added). Code that only
  consumes instances returned by `parse_berichten_verwerk_response` is
  unaffected; code that constructs these dataclasses directly (e.g. test
  doubles) needs to supply the new fields.

## [0.1.0]

### Added

- Initial `EbmsAdapterClient` covering the `/cpas`, `/urlMappings`,
  `/certificateMappings` and `/ebms` JSON REST resources of
  [eluinstra/ebms-core](https://github.com/eluinstra/ebms-core).
- `ebms_adapter_client.berichtenbox` sub-package for building and parsing
  MijnOverheid Berichtenbox 2.0 GLOBE-R-BV XML messages.

[Unreleased]: https://github.com/Worth-NL/ebms-adapter-client/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/Worth-NL/ebms-adapter-client/releases/tag/v0.3.0
[0.2.0]: https://github.com/Worth-NL/ebms-adapter-client/releases/tag/v0.2.0
[0.1.0]: https://github.com/Worth-NL/ebms-adapter-client/releases/tag/v0.1.0
