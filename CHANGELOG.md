# Changelog

All notable changes to Daily Money Transfer Manager 2026 are listed here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.0.0] - 2026-11-05

First public Windows desktop release.

### Added
- Windows desktop application (`DailyMoneyTransferManager.exe`): native window
  (Microsoft Edge WebView2) with a loading screen, automatic local server start
  on `127.0.0.1` with a free port, clean shutdown when the window closes, single
  instance guard and readable error pages.
- Windows installer (`DailyMoneyTransferManager-Setup.exe`, Inno Setup, per-user,
  no administrator rights) and portable ZIP edition.
- Persistent data folder `%LOCALAPPDATA%\DailyMoneyTransferManager` (database,
  backups, exports, logs) that survives updates and uninstallation.
- Database backups: one-click backup, download, restore with confirmation and
  automatic safety copy, restore from an uploaded file, automatic backup before
  schema migrations.
- Excel Upload import modes: **Merge** (keep existing records, add new rows) and
  **Replace** (delete every existing record first, after explicit confirmation).
- GitHub Actions workflow that tests, builds and publishes releases from `v*` tags.
- Sample workbook (`sample_data/`) and screenshots contain synthetic data only
  ("Demo Person NN", non-allocatable phone numbers, all-zero account numbers).

### Changed
- Settings page explains that "Remove records" only removes what that import
  added and shows the number of manually entered records.

### Fixed
- Dashboard crashed with `StreamlitInvalidHeightError` on Streamlit 1.50+ because
  a table was given `height=None`.

[Unreleased]: https://github.com/Mohamed-Qadar/Financial_Dashboard/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/Mohamed-Qadar/Financial_Dashboard/releases/tag/v1.0.0
