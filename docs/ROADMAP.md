# Roadmap

Keep milestones functional, not paperwork-heavy.

| Milestone | Scope | State |
|---|---|---|
| 0.1 | Core bootstrap, browser setup, local administrator and shared landing page | Initial implementation; runtime validation pending |
| 0.2 | Generic Compose worker, catalog, live job progress and lifecycle | Four lifecycle and batch wizard CI passed; shared dependency handling pending |
| 0.3 | Kiwix, Homebox, Grocy, Kopia independently installable | Four module lifecycles passed hosted CI; native setup and backup restoration remain pending |
| 0.4 | Household organization, ownership/location mapping, inventory reporting, stable QR links | Shared household directory, native discovery and admin location reports implemented; native API acceptance, family reporting and QR validation pending |
| 0.5 | Regional maps, downloads, offline routing | Local archive serving CI passed; regional extract manager implemented, validation pending. Styled offline viewer implemented; local graphical region selection and presets implemented; browser acceptance and routing next |
| 0.6 | Meshtastic, MeshCore, TAK, hardware/client setup | Planned |
| 0.7 | Kolibri, media, notes, PACE, content packs | Planned |
| 0.8 | Controlled manual and opt-in automatic updates, backup/restore | Planned |
| 1.0 | Real disconnected operation and clean-machine recovery, documentation | Planned |

Basic data preservation and security start now. Full offline recovery and AI must not block functional module development. Additional candidates: file sharing, documents, power monitoring, weather stations, offline translation, local AI and optional inter-household synchronization.

## Immediate next test
Install the core in a clean Debian/Ubuntu guest. Open setup, create admin, log out/in, restart core, confirm account persists and only core is installed. Check multi-module selection, job progress and independent retries. Next: guided native setup and stable local URLs, then offline content and maps.

## Content manager
Initial admin catalog search and local storage inventory implemented. Native downloader, checksum checks, disk checks and indexing implemented. Next: validate real upstream metadata and transfer, verify native indexing and offline reader reload; then add safe removal and USB imports.

Local import/index, recoverable removal, restore and purge implemented; CI fixture test added. Next: live official catalog/Metalink transfer, offline reading validation, then households and regional maps.

Valhalla graph preparation and local route planner implemented; native smoke tests pending. Next: regional PBF acquisition and updates, saved waypoints/routes and GPX/KML.

Shared waypoints, saved geometry and GPX/KML exports implemented; CI pending. Next: regional PBF acquisition, GPX/KML import, address search and browser validation.

Bounded GPX/KML import implemented; address search, regional routing data acquisition and full disconnected browser acceptance remain pending.

Regional PBF acquisition implemented with initial region presets and safe replacement staging. Next: graph preparation/activation/rollback for staged data, place search, alternatives and disconnected browser acceptance.

Replacement graph preparation, activation and rollback implemented with two retained slots; CI pending. Repeated update slot retirement, offline address/place search, alternative routes and disconnected browser validation remain outstanding.

Offline point/address-node search and native route alternatives implemented. Full address geocoding, repeated slot retirement and browser offline acceptance remain outstanding; latest CI pending.

Repeatable routing updates implemented through inactive-slot archiving and alternating source/graph slots. Browser-level offline validation remains next.

Chromium browser acceptance test added with off-server HTTP(S) requests blocked. Physical disconnected LAN and server egress isolation plus styled vector labels remain separate acceptance gates.

Communications: optional MeshMonitor module for Meshtastic and MeshCore implemented using one native application; radio connection, native offline acceptance, serial/BLE bridge support and TAK remain outstanding.

Optional MicroTAK backend implemented with locked enrollment and native TLS. Native client acceptance, consolidated communications status and PACE planning remain outstanding.

Core communications dashboard, shared PACE plans and manual device checks implemented. Navigation browser acceptance passed with off-server browser requests blocked; native communications CI and physical device acceptance remain pending.

0.7: Kolibri education integration implemented; native provisioning and lifecycle CI pending. Mesh/TAK bridge evaluation documented, no automatic bridge enabled. Next: media and shared documents, then consolidated inventory, updates and offline recovery.

Offline media: Jellyfin module implemented with read-only original media and native account/library management. Previous communications and Kolibri lifecycle CI passed. Media CI pending; next shared notes/documents, consolidated reporting and recovery.

Shared notes and emergency documents: DokuWiki implemented as a native file-based wiki with local accounts, explicit LAN sharing and persistent storage. Jellyfin CI passed. Notes CI pending; next consolidated inventory reporting, controlled updates and offline recovery.

Consolidated inventory: administrator live overview across mapped Homebox and Grocy locations with independent ownership/storage filters, bounded pagination and explicit partial failures implemented. Unit and API tests added; CI and native authenticated acceptance pending. Next: preparedness content organization and controlled application updates.

Preparedness: shared LAN landing-page indicators for indexed knowledge, local map archives, prepared graph marker, saved plans, manual device checks and mapped locations; links to native apps with their existing permissions. Suggested content packs are explicit catalog search presets, not verified bundles or automatic downloads. Unit and browser tests added; CI pending. Next: controlled application updates and backup/recovery.

0.8: local Docker version visibility and administrator backup acknowledgment for manual updates implemented. Routing updates blocked until graph migration validation. CI pending. Next: registry checks against reviewed targets, backup verification, update policy and core/recovery workflow.

0.8.1: explicit administrator registry metadata check for reviewed image references, comparing remote image config digests with installed IDs; no layers pulled, no tag discovery or automatic updates. CI pending. Next: application backup coverage, native Kopia setup and verified pre-update snapshots.

0.8.2: core and module backup coverage plans, normalized Compose mount classification, consistency guidance and explicit missing worker state/image coverage implemented. No snapshots scheduled or verified. CI pending. Next: native Kopia repository and application-consistent snapshot workflow.

0.8.3: native Kopia authenticated connection status and explicit empty-local-repository creation via the serialized worker queue. CI pending, including disposable native initialization. Next: consistent snapshot execution and restore verification.

0.8.4: initial managed Grocy snapshot with clean shutdown check, bounded native Kopia CLI, completeness checks and prior-state restoration on ordinary failures. CI pending; actual restore verification and expansion to other apps remain next. Prior repository setup CI unit/build checks passed but browser dependency installation failed before smoke; rerun requested.

0.8.5: isolated Grocy restore verification and SQLite integrity/schema checks implemented; CI pending. Registry checks and backup source plans passed CI. Repository initialization reached connected status in CI but obsolete host marker assertion failed; replace with restart/reconnection and subsequent native snapshot/restore. Next: resolve any native lifecycle failures before expanding backup coverage.

0.8.5.1: correct native snapshot JSON compatibility (verbose statistics) and fail-closed diagnostics. CI 45481862223 passed unit/build checks, repository restart/reconnect and Grocy stop/restart, but failed snapshot confirmation. New CI pending. Do not expand coverage or enable unattended updates until the full Grocy workflow passes.

0.8.6: Grocy managed snapshot and isolated restore validated by CI 45482855682. Expand managed snapshots to Homebox and DokuWiki, with isolated SQLite or configuration/page checks and native disposable smoke coverage. Expanded CI pending. Worker secrets and core consistency remain next.

0.8.7: implement private online core SQLite export and native Kopia snapshot; clear active sessions in copy, check integrity, remove owned staging. CI pending. Core database restore verification and worker-state recovery next. Homebox/DokuWiki expanded CI still running at start of this slice.

0.8.8: previous expanded application backups and online core export passed CI 45485912415 / 45486710318. Add isolated core snapshot restoration with exact job marker, schema, administrator and absent session checks. CI pending. Next: worker-state consistent recovery export and verification, including generated secrets.

0.8.9: worker state and generated secret consistent export and encrypted Kopia snapshot implemented, no pending job replay, no new mounts, private staging cleanup; CI pending. Core isolated restoration workflow still running at start. Next verify worker export restoration and then expand remaining app coverage.
