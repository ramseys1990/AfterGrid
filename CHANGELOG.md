# Changelog

## 0.3.0-dev
- Add Homebox, Grocy and Kopia as independent optional Compose modules.
- Generate persistent module secrets and expose only Kopia's setup credentials to an authenticated local administrator.
- Loopback-only native setup for inventory and backup services; stable LAN access and QR verification pending.
- Extend disposable CI lifecycle coverage; do not claim live data backup or recovery validation.

## 0.2.0-dev
- Catalog entries are derived from module manifests; additional reviewed modules need no core allowlist edits.
- Refresh module state when a job changes; keep expanded output visible.
- Add worker socket readiness and a disposable end-to-end Compose lifecycle CI test.
- Add a private Compose worker, persistent jobs and actual Docker output.
- Add Kiwix using upstream pinned image and independent project; content remains separate.
- Add admin lifecycle buttons, progress and job history. Runtime tests pending.


## 0.1.0-dev
- Initial project charter and practical development roadmap.
- Core-only development bootstrap and Docker Compose definition.
- Local administrator setup and shared dashboard.
- Planned module catalog preview; no Docker module operations yet.
- Authentication tests and minimal CI; real Linux/Docker installation not yet validated.
