# Changelog

## 2.1.0

### Added

- XMRiGUI now looks for an executable XMRig binary under `/opt/xmrigui`, alongside the application, in its `miner/` subdirectory, and in the user's XDG data directory.
- If no miner is found, **Diagnostics → Download official XMRig…** can install the latest stable Linux x86-64 build from the official XMRig GitHub repository after confirmation. The installer checks the archive size and SHA-256 digest before installing without administrator privileges. It does not overwrite an existing binary.

### Changed

- Opening XMRiGUI no longer starts mining, even if profiles were active when the application last closed. Start mining manually or pass the explicit `start` command. Downloading XMRig does not start it either.

## 2.0.0

- Migrated the Linux GUI to PyQt6 and D-Bus integration to QtDBus.
- Added field-level validation for mining profiles, a live hashrate chart and session statistics.
- Added optional automatic restart after unexpected miner exits, with increasing delays and a five-attempt limit.
- Added miner diagnostics and log export with best-effort redaction of sensitive values.
- Added profile renaming and copying between the three profile slots. Copying requires confirmation and leaves the destination stopped.
