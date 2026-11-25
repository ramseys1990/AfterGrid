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

0.8.10: isolated worker-state restore, exact envelope SHA-256, job marker, database integrity and no pending replay checks; CI verifies original generated secret values without logging them. CI pending. Previous core restore and worker snapshot unit/build checks passed; native smoke still running at start of this slice. Next expand managed application coverage and plan clean-machine recovery.

0.8.11: standalone offline recovery preparation from validated core and worker exports; private reconstructed files, no live Docker writes, no overwrite. Unit tests pending. Remaining: application coverage, exact release/image capture, coordinated backup set and actual clean-machine startup.

0.8.12: expand managed maintenance-stop snapshots/isolated verification to MeshMonitor, MicroTAK, Kolibri and Jellyfin configuration. CI pending; avoid redundant Kopia registry pull in disposable integration. Core restore passed; worker export smoke milestone passed, full workflow blocked by Docker Hub rate limit. Worker restore and recovery preparation still require validation. Remaining content datasets and clean-machine recovery.

0.8.13: 0.8.11 CI passed (core/worker isolated recovery and offline preparation). Add managed snapshots for Kiwix, maps, routing and Jellyfin media, guarded portal content admission and exact native full-file read verification without duplicate restore staging. Expanded CI pending. Full content restore, download metadata and coordinated recovery set next.

0.8.14: native recovery inventory of exact snapshot IDs, job and verification evidence, worker envelope digest and manifest presence. Admin-only JSON download. Expanded application CI passed 45494302655; offline content CI running. Inventory is not atomic or a complete package. Next preserve download state and host/release metadata, then exact images and replacement installation.

0.8.15: extend core recovery export to stable download and regional metadata, validate on isolated restore, reconstruct during offline preparation, expose inclusion in inventory. Legacy snapshots remain supported and labeled. CI pending. Next host configuration, exact release/images and coordinated recovery sets.

0.8.16: host-only offline asset export of reviewed installed release and raw environment, exact existing container image IDs via docker image save, checksum manifest and verification. Native Docker fixture and unit tests pending. No data repository or recovery apply included. 0.8.14 inventory CI passed. Next no-pull image import/Compose recovery and coordinated recovery package.

0.8.17: explicit empty replacement-daemon image import, exact ID validation, recovery tags, no-pull overrides; pending CI. Correct routing verification dedup count mismatch; MicroTAK clean shutdown remains blocked. Prior 0.8.12/0.8.13/0.8.14/0.8.15 Core checks failed, even where other GitHub workflows passed. Next native clean-stop or application-native consistent export for TAK, replacement state application and offline startup.

0.8.18: core/worker replacement staging and explicit loopback-only core startup with exact local image overrides, ownership and no-pull/no-build. Unit fixtures pending; full replacement startup not yet validated. Routing read verification passed 45496581667. MicroTAK strict shutdown blocked; add exit diagnostics rather than accept unclean termination. Next application data placement, offline module image mappings and native disposable recovered-core startup.

0.8.19: independent native recovered-core startup acceptance before full application smoke; core-only portal/worker write guards and compatible image labels. Core checks 45496581667 passed archive fixture and routing milestone, failed MicroTAK. Next validate replacement acceptance, add optional data placement and offline module startup; TAK consistency remains blocked.

0.8.20: native application/content restore to new staged root, exact verified inventory/source mapping, read-only offline Kopia helper, restricted replacement placement and receipts. 0.8.19 disposable recovered-core startup acceptance passed 45500462447; full integration running. Next native data restoration fixture and no-pull module start. MicroTAK still blocked.

0.8.21: explicit no-pull optional module startup from a verified restoration receipt, exact image and guarded core, loopback/mount checks, readiness receipt; native Kiwix restoration fixture. Continue smoke after only the known TAK refusal/restart and require missing snapshot in inventory. Next worker offline lifecycle mapping, Kopia reconnection, recovery completion and full acceptance. CI pending.

0.8.22: stage selected started module offline image mappings and implement opt-in worker offline lifecycle admission and exact image override enforcement. Core-only protection stays active; no activation command yet. Next Kopia reconnect, controlled completion, native module recovery acceptance and full disconnected test. CI pending.

0.8.23: guided replacement command directly restores exact core/worker exports and selected app snapshots, prepares independent read-only Kopia working copy, guarded startup and offline policy; explicit restricted lifecycle activation after operator native checks. Native Kiwix fixture corrected: prior smoke purged archive before capture, so retain pinned fixture separately. 0.8.22 unit/core startup passed; latest native integration pending. TAK exit 143 still blocked. Remaining writable backup reconnection, coordinated capture, disconnected end-to-end acceptance and scheduling.

0.8.24: independent guided native recovery fixture for core/worker/Kiwix through real Kopia snapshots, exact local image startup, read-only reconnect, offline activation and lifecycle, unchanged source repository hashes. Prior 0.8.23 unit and recovered-core startup passed; full smoke running. No new runtime architecture; closeout acceptance pending.

0.8.25: guided native recovery step passed in Core checks 45503443558 (core/worker/Kiwix). Add explicit native writable working-copy reconnection before activation and reviewed offline backup admission with native status check. Extend fixture to prove new managed core snapshot/restore and original repo unchanged. CI pending. TAK and full disconnected acceptance remain open.

0.8.26: coordinated portable package assembly/verification/restore from quiescent source containers and selected verified snapshots, deterministic source/copy repository digest, native exact manifest presence, recorded omissions. Guided acceptance now packages the original stopped installation. 0.8.23 full Core checks passed 45502154482 except explicitly blocked TAK; 0.8.24 guided acceptance passed 45503443558. Latest package and writable-copy validation pending. Simultaneous system capture and disconnected acceptance remain outstanding.

Recovery closeout (0.8.26 development): add administrator-confirmed fresh capture coordinator using existing authenticated native snapshot/verification jobs, both media sources, exact snapshot and verification job IDs, concurrent-worker activity refusal and explicit MicroTAK exclusion. It publishes a new verified inventory; operator retains exclusive maintenance and explicitly stops source services before portable pack. No atomic capture or global write lock. Guided native fixture now exercises the coordinator. CI pending; next maintenance admission/handoff, MicroTAK disposition and disconnected acceptance.

Recovery closeout: persistent source portal maintenance serializes mutation admission in the supported single-process deployment, refuses active work on entry, permits only capture-owner backup jobs, seals exact inventory digest/selection, and requires explicit release. Host pack validates sealed handoff; stop/restart and native writer quiescence remain operator-controlled. Regression and guided native fixture updated; CI pending. Next MicroTAK consistency and disconnected replacement acceptance.


Recovery scope closeout: pinned MicroTAK 0.18.1 source review confirms lack of graceful signal handling and an incremental native mirror rather than an accepted consistent export. Formalize the exclusion in supported capture/package/restore paths, require explicit acknowledgment if its image is captured, report the blocker in inventory, and retain strict diagnostic shutdown checks. Module remains usable; all-application recovery remains open. CI pending. Continue host handoff and disconnected acceptance for supported modules independently.

Recovery closeout: MicroTAK data recovery is explicitly deferred with administrator agreement. Add exact-container source shutdown/restart journal, sealed package verification and combined create-package command; leave maintenance sealed until native readiness inspection. Prior maintenance milestone Core checks passed (45509589268). Latest host-handoff unit tests passed in run 45513229695; native end-to-end results pending. Add separate hosted network-none replacement daemon acceptance using actual archive import, recovered Kiwix and writable native backup verification. Physical clean-host/LAN acceptance and broader selected-module coverage remain separate.

Recovery acceptance evidence (0.8.26): Core checks run [45513492158](https://github.com/ramseys1990/AfterGrid/actions/runs/45513492158), commit d5d2572, passed Python regression, native image archive, recovered-core startup, guided native recovery, actual network-isolated empty-daemon replacement restore, private fixture cleanup and module Compose validation. The final general lifecycle smoke was still running at evidence capture. Representative automated recovery gate is passed; broader per-module and physical clean-host/LAN production acceptance remain separate. MicroTAK data recovery remains explicitly excluded. No additional recovery architecture changes are needed absent a confirmed failure; next development milestone is native Kopia scheduling and retention after reviewing the final lifecycle result.

Backup scheduling/retention first slice: read-only native Kopia effective policy inspection through reviewed source IDs and the administrator portal. Do not send arbitrary paths, action commands or raw policy objects. Native schedule settings do not prove managed execution; keep scheduling and retention writes disabled until application-consistent admission and recovery-point retention are validated. MicroTAK remains excluded. Regression and native guided assertions added; CI pending. Previous recovery general lifecycle still running, disconnected representative gate already passed.

Managed scheduling first execution slice: opt-in daily/weekly reviewed source schedules, existing portal mutation lock and worker jobs, native effective schedule conflict check, one due snapshot at a time, no missed-slot replay, durable dispatch claim and pause on failed/interrupted/uncertain job. No schedule restoration or auto-execution in recovery mode; reconfigure after acceptance. Core data schedule file is not included in recovery exports. Manual verification remains required; retention writes still disabled. CI pending. Earlier full lifecycle run 45513229695 passed; disconnected gate 45513492158 passed, final general lifecycle pending at review.

Scheduled verification slice: every successful newly scheduled snapshot gets a separate exact-source verification job, prioritized over new due captures. Persist source and verification job identities, pause on failure/unknown outcomes, do not retroactively mark older snapshot-only records verified. Existing isolated restore and full content-read checks are reused; successful scheduled private restore directories are removed, failed ones retained for inspection. Disposable native fixture exercises a due core schedule and verification. No automatic verification in recovery mode, no retention mutation yet. CI pending.

Full recovery workflow 45513492158 passed, including final lifecycle smoke. Native protected-capture slice: Kopia 0.23.1 pin-at-creation (post-capture pin edits rewrite manifest IDs); explicit per-source protected snapshot, native exact-ID pin readback, inventory pin status independent of verification, no scheduled pin accumulation or automatic unpin. Existing records not mutated. Native fixture and regressions pending CI; retention writes remain disabled.

Source-specific retention slice: bounded native count edits, confirmed administrator selection, idle queue, stale-policy guard, latest verified protected capture with exact native pin before/after, effective readback and no explicit expiration or global policy mutation. Protected history is not a substitute for independent recovery packages. Regression and disposable native core policy roundtrip added; CI pending. Next backup health and consolidated acceptance.

Backup health slice: consolidated administrator read-only view of native connectivity, exact recorded verification, latest failed/active attempts, latest protected capture, matching historical inventory/pin observations, managed schedule due/deferred/paused status and last retention attempt. No raw logs/secrets or new verification on refresh. Regression and guided fixture assertions added; native acceptance pending. Protected capture guided run 45516059881 passed; retention regression run 45516413300 passed. Next consolidated CI review and fixes before automatic updates.

### Backup management acceptance review — 2026-11-24

All eleven implementation components are present. Core checks
[45515542489](https://github.com/ramseys1990/AfterGrid/actions/runs/45515542489)
(scheduling), [45515829974](https://github.com/ramseys1990/AfterGrid/actions/runs/45515829974)
(exact verification), [45516059881](https://github.com/ramseys1990/AfterGrid/actions/runs/45516059881)
(protection), and [45516413300](https://github.com/ramseys1990/AfterGrid/actions/runs/45516413300)
(retention) each passed regression, guided native and disconnected acceptance
steps. General lifecycle completion was still pending at review.
The consolidated health commit 35a33b4 run
[45516790640](https://github.com/ramseys1990/AfterGrid/actions/runs/45516790640)
passed regression, syntax, Compose build and recovered-core startup; guided
native, disconnected and general lifecycle results were still pending.
Do not mark consolidated acceptance complete until its observed result is
available. No confirmed failure required a code change during this review.

The next development plan is recorded in [UPDATES.md](UPDATES.md):
begin with read-only eligibility and a guarded Kiwix pilot on reviewed
digest-pinned targets, fresh verified protected pre-update snapshots,
exact image identity and real readiness, then opt-in scheduling.
No automatic update implementation or enablement in this documentation slice.

Update pilot first slice: repository-owned Kiwix candidate is deliberately null; narrow digest-pinned reviewed transition and platform image identities, local and explicit online advisory eligibility reports, administrator interface, no auto-execution. Missing candidate, uncertain registry, recovery mode, unapproved starting point and busy or unhealthy service cannot authorize an update. Regression and guided fixture added. Consolidated backup run 45516790640 passed guided native acceptance; disconnected and general lifecycle still pending at review. Native policy full run 45515045817 passed.

Pre-update preparation slice: explicit reviewed Kiwix transition, recheck registry/local identity and prior image availability, hold content guard through pinned capture and exact full native read, record successful preparation evidence separately. No pull, update, image preservation tag or reusable authorization. Candidate remains null; positive native acceptance pending. Consolidated backup run 45516790640 passed guided and disconnected steps; general lifecycle still pending. Eligibility regression run 45517498810 passed.

Previous image preservation: private exact-ID Docker save archive, atomic publication, checksum and config identity checks, deduplication, free-space and size/time bounds. Preparation rechecks identity after save and records metadata. Native disposable Kiwix save/load fixture and regression added; CI pending. No automatic update, archive deletion or production restore endpoint. Preparation regressions passed in run 45517718162; full consolidated backup lifecycle still pending. Next guarded Compose execution and explicit recovery handling.

Guarded update execution: explicit admin-only Kiwix job with fresh verified pinned content and prior image archive, continuous guard, durable pre-recreation evidence, reviewed digest-pinned pull/config-ID check, Compose up without pull/build, actual readiness, exact resulting image and bounded native catalog sample comparison. Failure retains evidence and blocks subsequent guarded execution; rollback and positive native transition acceptance pending. Candidate remains null, no unattended execution. Previous archive regression run 45517996676 passed; scheduling/verification full runs 45515542489 and 45515829974 passed.

Reader update failure recovery: image-only rollback after failed recreation, unchanged Compose fingerprint, verified archive and native pin, exact local load/tag, persistent private no-pull Compose hold, installed image and catalog readback. Update remains failed and blocks further guarded updates. No hold-clear endpoint or database rollback. Disposable native helper fixture and regressions added, CI pending. Guarded update regression 45518465357 and previous archive guided native 45517996676 passed; protection full run 45516059881 passed. Next positive transition/rollback acceptance and explicit per-module preferences.

Update preference slice: private administrator-only Kiwix opt-in preference and recurring UTC admission window with explicit confirmation, no dispatch and separate activation required after acceptance. Regression and API tests added. Rollback regression 45518793704 passed; retention 45516413300 fully passed. Next consolidated update status and positive native transition acceptance, then gated scheduling.

Update health dashboard: read-only local reader/image status, candidate, rollback hold, separate guarded/manual/preparation history, sanitized recorded recovery evidence, preferences and UTC window. No registry or archive re-verification, no execution. Preference regression run 45519004578 passed; guarded update guided run 45518465357 passed (null-candidate rejection, not positive transition). Positive native transition, hold resolution and gated scheduler dispatch remain outstanding.


Acceptance follow-up: consolidated backup management run [45516790640](https://github.com/ramseys1990/AfterGrid/actions/runs/45516790640) fully passed, including disconnected replacement and general Compose lifecycle. Physical clean-host acceptance remains separate. Rollback and preference runs [45518793704](https://github.com/ramseys1990/AfterGrid/actions/runs/45518793704) and [45519004578](https://github.com/ramseys1990/AfterGrid/actions/runs/45519004578) failed during later guided Kiwix content snapshot (job 15), after the rollback helper assertions; root cause not confirmed. Bounded CI diagnostics added in bec6c3d, regression passed in [45519497041](https://github.com/ramseys1990/AfterGrid/actions/runs/45519497041), native result pending at review. Update health now explicitly reports unavailable local image evidence even when readiness is running; regression added. No automatic dispatch or approved candidate. Resolve guided snapshot failure before native positive transition and scheduler activation.


Snapshot regression follow-up: diagnostic [45519497041](https://github.com/ramseys1990/AfterGrid/actions/runs/45519497041) failed at guided content snapshot job 15, progress 1/3, category=snapshot file count. Kopia v0.23.1 generation statistics omit cached files from fileCount (snapshot/upload/upload.go); native snapshot verify calculates expected totals from the root directory summary (cli/command_snapshot_verify.go). Use the mandatory native directory summary for logical file count and bytes, retaining strict generation error/exclusion checks and rejecting incomplete, empty, malformed or error-bearing summaries. This does not bypass exact manifest readback or native 100% content verification. Regression tests added; existing guided rollback fixture repeats a protected snapshot then fresh capture. Native CI acceptance remains pending. No automatic dispatch enabled.


Update closeout: corrected snapshot run 45520288017 passed regression and guided native recovery; positive version transition run 45520349270 passed regression and guided native acceptance (Kiwix 3.8.1 to 3.8.2), disconnected acceptance pending at review. Explicit rollback-resolution job implemented c0c9739; native fixture now exercises it using synthetic failed-job evidence from a real restored reader. Existing scheduler gains disabled-by-release-gate dispatch, separate activation and durable one-attempt-per-window claim. Regression and native acceptance pending; production candidate remains null. Physical installation and actual injected native failed transition remain separate acceptance items.


### Installation readiness (next milestone)

Installer audit: add read-only preflight and reject conflicting local TCP listeners, Docker published portal ports, remote Docker contexts and existing AfterGrid containers/networks/volumes before source deployment. Preserve unrelated Docker projects. Explicitly export fixed installation root. Next: interrupted-install resume, first-run and port conflict handling for selected apps, clean Debian/Ubuntu and suitable Proxmox guest acceptance. Physical host checks remain unverified.


Installer CI repair: reconstruct from the previously passing baseline rather than editing a malformed duplicate shell block. Fresh installation now uses a nonblocking host lock and stages the complete source, token, data directories and configuration under /opt before publishing the root by same-filesystem rename. This addresses partial source publication, not failed Docker startup; explicit safe resume remains pending. Full recovery/update CI at f3b614e passed (45521056086).

Installer resume: preserve staged configuration and original token, require a root-owned pending marker and matching configuration hashes, verify the local Docker context and existing core project labels, and reuse the same core-only Compose startup. No fresh install over existing data; no resume of completed or unmarked installations. Regression tests added, live startup acceptance pending. Fixed preflight test mock for single-argument Docker commands under nounset.

First-run wizard: persist submitted selection before worker admission; an ambiguous response survives refresh/restart and permits only the same selection replay. Worker checks existing batch token before catalog validation; definitive rejection allows correction. Initial selection remains optional and credentials are not returned. Failed latest install jobs offer individual retry using the existing Compose path. Tests added; browser acceptance pending.
