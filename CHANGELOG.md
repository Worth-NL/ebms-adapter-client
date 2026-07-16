# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/Worth-NL/ebms-adapter-client/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/Worth-NL/ebms-adapter-client/releases/tag/v0.2.0
[0.1.0]: https://github.com/Worth-NL/ebms-adapter-client/releases/tag/v0.1.0
