# Changelog

## 0.3.5-dev
- Persistent single-worker content queue with curl resume, free-space checks, actual partial-file byte counts and SHA-256 verification from official Metalink metadata.
- Native kiwix-manage indexing and reader monitorLibrary option; no Docker access in downloader.
- Add selection, progress and retry controls; tests for official URL validation and queue persistence. Live metadata, transfer and reader reload unverified.
- Fix regression in Kopia credential endpoint test.


## 0.3.4-dev
- Read-only content inventory with available disk space, plus on-demand official Kiwix OPDS search, language filter and pagination.
- Keep local content inventory independent of internet availability. No automatic downloads or indexing yet.
- Add catalog parser, access-control and local inventory tests; live upstream feed and actual content handling pending.


## 0.3.3-dev
- Installer prefers the detected private LAN IP, with explicit address override and loopback fallback.
- Optional DNS; stable IP URLs work without a DNS server. Configure separate hostnames for stronger cookie isolation and stable QR labels.
- Kopia supports explicit LAN sharing with native authentication and origin-checked administrator credential retrieval.
- Expand Docker LAN binding tests to Kopia. Physical LAN and native account setup are not yet validated.


## 0.3.2-dev
- Explicit LAN sharing and local-only reconfiguration for Homebox and Grocy; Kopia stays loopback-only.
- Stable home.arpa application URLs, persistent sharing preferences and Homebox registration closure.
- Document local DNS, native account setup and unencrypted HTTP limitations. Unit tests and disposable Docker bind/reconfigure tests added; actual LAN and QR scan validation pending.


## 0.3.1-dev
- First-run browser application selection with no default selection, explicit skip, and optional essentials preset.
- Atomically queue selected modules; replay the same selection without duplicating jobs. Worker runs one job at a time.
- Add tests for authentication, origin checks, skip, invalid selections and batch replay. Extend hosted lifecycle smoke test to exercise batch install.
- Record prior successful hosted CI of all four module lifecycles. Native QR and backup restoration are not validated.


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
