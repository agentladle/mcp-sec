# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **Note:** Before releasing, please update the version number in this file and in `src/mcp_sec/__init__.py`.

## Environments

| Environment | Current Version | Description |
|-------------|-----------------|-------------|
| TestPyPI    | `0.1.5`         | Testing environment |
| PyPI        | `0.1.5`         | Production environment |

## Release Workflow

1. Update the target version number in this file.
2. Synchronize the `__version__` in `src/mcp_sec/__init__.py`.
3. Build the package: `python -m build`
4. Upload the package: 
   - Testing: `twine upload --repository testpypi dist/*`
   - Production: `twine upload dist/*`

---

## [0.1.5] - 2026-07-09

### Added
- Added HTM parsing support for Form 6-K filings.

### Changed
- Improved download/parse pipeline for HTML-based SEC exhibits.

## [0.1.4] - 2026-07-09

### Added
- Added `lookup_ticker_cik` tool to resolve ticker ↔ CIK mappings and diagnose missing mappings.

### Changed
- Improved downloader handling when ticker/CIK lookup fails.

## [0.1.3] - 2026-06-17

### Added
- Added demonstration videos.

### Changed
- Optimized the local configuration path (migrated to `~/.agentladle/mcp-sec/`).

### Fixed
- Fixed Glama Schema validation.

## [0.1.2] - 2026-06-15

### Added
- Released to PyPI.

### Changed
- Semantic refactoring: `filing_date` renamed to `report_date`.
- Optimized tool descriptions.

## [0.1.1]

### Added
- Published to TestPyPI.

## [0.1.0]

### Added
- Initial release to PyPI.
