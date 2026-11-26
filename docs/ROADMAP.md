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

Installation progress: persistent latest install outcome for each reviewed application (independent of 30-job activity limit); administrator-only summary, actual stage counters and individual retry controls. No synthetic byte-progress percentage or readiness claim. Tests added. Near the end of this phase, audit each module’s native authentication and first-time account workflow: ordinary LAN users should not need SSH or port forwarding. Prefer supported anonymous read-only access for appropriate shared content, native authenticated access for sensitive/admin data, and supported secure browser onboarding from the portal. Keep native security intact; no mandatory external identity service or blanket authentication bypass. Include phone/desktop LAN acceptance and explicitly document any exceptional hardware or native setup requirement.

Application port preflight: before an install pulls images, derive all published host ports/protocols from normalized reviewed Compose configuration and compare against running Docker container publications. Ignore same-module containers so independent retries work; conservatively treat matching port/protocol across bind addresses as conflicts. Show bounded conflict details in the persistent installation summary. No unrelated workloads stopped or removed. Docker remains the final authority for non-Docker listeners, host-network services and races; no host namespace access added. Unit tests added; native acceptance pending. Prior persistent-install-summary run 45535479965 passed Python, guided recovery and disconnected recovery at review.

Core updating: host-only candidate preparation added. Exact reviewed commit and archive checksum, unchanged Compose/module scope, isolated builds and prior image identity report. Activation deliberately unavailable until verified consistent state backups, maintenance and rollback tests are implemented.

Core update backup evidence: reuse the existing sealed core-only recovery maintenance flow, native Kopia protected snapshots and isolated verification. Host read-only evidence check validates freshness, inventory identity, exact job records and current native pins; activation remains unavailable. Candidate preparation regression passed in run 45536543583; this new integration awaits CI.

Core update prior image retention: exact prior image tags and Docker save archive, image configuration digest verification and full archive checksum; generate fixed no-pull candidate/prior image overrides without running Compose. Unit fixture added. CI run 45536730899 passed Python and recovered-core startup but was blocked by GHCR rate limit before guided native test. Bounded retries added for reviewed CI pulls. Activation and state rollback are still gated.

Core update durable maintenance claim and read-only activation gate: bind candidate plan to sealed inventory; persist updating phase across restart, prevent portal mutations and release, verify prior archive and fixed overrides plus live Kopia evidence. Host cancellation permitted only before any activation journal with original healthy containers. Local stopped-service checkpoint and actual activation/rollback still pending. Prior image-retention regression passed (45537261548); native acceptance underway.

Core updating scope clarification: only portal and worker may stop; independent application projects and shared network stay running. Added internal stopped-state checkpoint archive validation and disposable guided CI coverage checking Kiwix accessibility and unchanged Kopia/Kiwix container identities through the core outage. Production activation and restoration remain disabled pending verification and transaction work. Prior maintenance regression passed in run 45537919688.

Core updating: journaled disposable core replacement trial on private checkpoint copies, fixed no-pull Compose scope, exact prior-state return on success or probe failure. Native fixture uses local image IDs under candidate tags; regression covers injected probe failure. No production activation or promotion. Prior stopped-checkpoint Python tests passed (45538588061); native acceptance still pending at review.

Core updating: stopped-state native guided acceptance passed in run 45538588061 (independent Kiwix/Kopia availability). Prior candidate replacement Python regression passed (45539031965). Added distinct local candidate image IDs, successful and intentionally failed native trial probes, candidate source digest binding, and read-only journal inspection. Production promotion/crash recovery remains pending; new native tests await CI.

Core update validation: run 45539031965 passed guided native same-image replacement and return; run 45539341662 passed Python and outage checkpoint but distinct fixture failed startup. Removed fixture entrypoint override and explicitly compare runtime configuration. Added interrupted disposable trial reconciliation, abrupt-process-exit native scenario and foreign-container rejection regression. New validation pending. Production activation remains gated.

Core updating: added digest-checked, restart-reconcilable same-filesystem source transition, retaining old and new trees. Disposable successful-trial promotion now tests canonical data mounts and default Compose image tags, source identity, and recreation persistence while optional applications remain online. Failed canonical promotion remains held for manual inspection; production data restoration and browser handoff remain gated. Corrected distinct-image CI still underway (45539975376).

Core updating: added disposable canonical startup/probe failure rollback of both state locations, source and exact prior images; retain failed core and worker state for inspection. Native fixture simulates schema changes in both databases and checks their removal after rollback, plus Kiwix/Kopia uptime. Corrected reused trial directory for promotion. Latest promotion Python regressions passed (45540158265); broader native acceptance and new rollback tests pending. Production activation and interrupted canonical rollback reconciliation remain disabled.

Core update closeout evidence: guided native distinct-image success/failure/interruption passed (45539975376). Permanent-promotion run 45540158265 passed Python but hit the duplicate fixture directory fixed in 856a9f1; latest canonical rollback Python regression passed (45540553164), native still running. Added admin-only read-only update status, safe terminal disposable promotion/rollback hold finalization and tests. Release remains gated on native canonical rollback/promotion and interrupted restoration plus production execution/handoff. Do not mark one-click updating shipped.

Core update closeout: dashboard Python regression passed (45541062798), canonical rollback Python regression passed (45540553164), native runs still underway at review. Added resumable core rename and worker quarantine phases plus scoped disposable canonical restore resume and unit fixture. Mid-worker restore and prior-startup reconciliation still need native acceptance. Do not mark production updating shipped.


## Phase 3 closeout baseline — appliance-first

Full CI passed on commits 856a9f1 (45540553164), 0070483 (45541062798), and b010d7c (45541686525): Python regression, guided native recovery including canonical promotion and schema rollback, disconnected replacement archive acceptance, and Compose lifecycle. Kiwix and Kopia remained available during scoped core operations in guided CI. These are disposable tests with local fixture images, not a released production updater or real-machine acceptance.

The next deliverable is a manually approved, single-action core update for a reviewed release, using the existing Compose/Kopia workflow. Do not expand the automatic update system, add a new permanent service, or implement speculative recovery frameworks. Verify the existing restore resume behavior, authorize a fixed host-side execution/handoff and test an actual release build before exposing the update action. The current status UI is read-only. Rare ambiguous failures may remain safely held with a clear documented recovery procedure rather than requiring automatic repair of every possible state. Then move to non-destructive uninstall/reinstall, LAN first-run and module authentication, followed by clean-host acceptance. Treat an SSH-only setup workflow as a usability gap, not a successful end-user design.


## Phase 3 master checklist — installation and deployment

Current: **9 of 13 checklist items complete** (1–8 and 10). Runtime evidence and remaining limitations are recorded below. Bare-metal verification is explicitly deferred by the operator; production core activation remains gated.

| # | Checklist item | Implementation status | Real-machine acceptance |
|---|---|---|---|
| 1 | Installer audit | Complete | Fresh Ubuntu 24.04 guest install passed through healthy core/worker and LAN setup page |
| 2 | Read-only installation preflight | Complete | Passed on fresh Ubuntu 24.04 unprivileged Proxmox guest |
| 3 | Existing Docker workload protection | Complete | Worker and four app IDs/start times unchanged during scoped test core rebuild; deliberate conflicting fixture preserved; existing shared-host coverage remains partial |
| 4 | Interrupted installation recovery | Complete | CT116: real failed startup, interrupted resume and successful resume passed after Docker inspection fix; browser setup and guest reboot persistence also passed |
| 5 | First-run setup improvements | Complete | CT115 and CT116 administrator setup/logout/login passed; CT116 core-only choice, account and session survived guest reboot |
| 6 | Application selection validation | Complete | Four-app wizard batch passed; independent Kiwix retry completed as job #12 after resolved port conflict |
| 7 | Installation progress reporting | Complete | Real per-app Compose activity and completed-stage summaries observed; failed summary persisted after refresh |
| 8 | Application port conflict handling | Complete | Real occupied-port rejection passed before image pull; error and retry survived refresh; Retry job #12 completed; native retained article reopened |
| 9 | AfterGrid core updating | Open — production activation gated | Native disposable tests passed; reviewed production release/handoff pending |
| 10 | Safe uninstall and reinstall | Complete | Selected optional-app dashboard uninstall/reinstall and documented exact-image core/worker removal/reinstall passed; data and independent apps preserved. Exceptional recovery retains its own overrides |
| 11 | LAN deployment validation | Open | Original and recovered portal/article passed desktop and user-observed physical phone; recovered guest WAN-loss and reboot passed. Homebox/Grocy browser setup, authenticated native LAN journeys and populated backups passed; user-observed physical-phone Homebox QR opening passed; stable label hostname remains pending |
| 12 | Module authentication and simplified onboarding | Open | Homebox/Grocy setup, LAN journeys, phone QR and populated native restored startup passed; PR #3 merged. Other catalog apps still require private native onboarding; broader simplified onboarding remains open |
| 13 | System requirements and clean-host acceptance | Open — bare-metal verification deferred by operator | CT116 empty-daemon offline package restore, six exact images, selected native state, new backup/restore, LAN and reboot passed on 2 cores/1 GiB; Populated native restored startup passed on CT115; 60-request and 45-second/1,030-request exercises passed across CT115/116. Larger datasets/peak sizing remain unverified; bare-metal verification is deferred |

The test guest is disposable, but acceptance must preserve installed application data unless a distinct test explicitly calls for deletion. Keep all infrastructure changes confined to the designated guest. Retain native application permissions, use Compose and Kopia, and defer the major UI overhaul until the approach to 1.0.


### Real Proxmox installation evidence — 2026-11-24

Tested source: `ebbb27c0566bb085bbcff16f005b9553385a83bb`.
Fresh Ubuntu 24.04 amd64 unprivileged guest, nesting enabled, 4 cores,
4 GiB RAM, 512 MiB swap and 100 GiB root disk. The initial guest had
blank static IPv4 settings; selecting DHCP provided its private LAN address
and default route. No unrelated guests or workloads were modified.

- Installed missing curl/CA prerequisites from Ubuntu packages.
- The pinned installer `--check` passed without Docker installed and
  automatically selected the guest's private address and port 8080.
- Installed the pinned source using `AFTERGRID_REF`; Docker Engine
  29.10.1 and Compose 5.8.0 came from Docker's official Ubuntu repository.
- Both locally built core and worker started healthy. `docker ps -a`
  showed only those two containers; no optional modules were installed.
- The private LAN `/health` endpoint returned `{"status":"ok"}`.
  The initial-install pending marker was absent after success.
- The connected desktop browser rendered the first-run setup form at
  the printed LAN URL. No SSH tunnel, custom DNS or proxy was needed.
- One idle `docker stats --no-stream` sample reported core 38.73 MiB and
  worker 52.25 MiB. This is a point-in-time core-only observation, not a
  system requirement or full appliance resource certification.

At the initial evidence capture, administrator creation and subsequent journeys
were still pending. The follow-up evidence below supersedes that pending status
where an observed result is recorded. Production core update activation remains
gated; the implementation checklist stays at **8/13**. No new architecture or
authentication service was added.


### Live acceptance follow-up — 2026-11-25

The initial installation used `ebbb27c`. Two observed downloader failures were
fixed and tested on the same designated disposable guest:

- `04213f8`: official Metalink metadata requests now use Kiwix's canonical
  `lb.download.kiwix.org` endpoint directly. Arbitrary metadata redirects remain
  blocked. The previous origin returned HTTP 301.
- `c71095a`: native curl retries an unavailable selected mirror once using
  `mirror.download.kiwix.org`, with the same resume, HTTPS, size and SHA-256
  checks. The selected mirror's TLS connection timed out; the official primary
  was reachable from the same container.

The downloader suite passed **7 tests on Linux** in a disposable container.
A Windows run could not execute the hard-link filesystem tests under its
sandbox; it is not evidence of a complete Windows pass. Only the portal was
rebuilt for the test patches using normal Compose. Exact worker and four
application container IDs and native start times were unchanged during the
second rebuild. This development patch exercise does not release production
core update activation.

| Journey | Observed result | Remaining limit |
|---|---|---|
| Administrator setup | Operator created the account; logout/login passed | Other native application accounts are separate |
| Guest access | Signed-out portal remained accessible and administrative controls were hidden | Broader authorization/CSRF testing remains separate |
| Core restart | Administrator session and unsubmitted first-run wizard survived a portal-only restart; worker stayed up | Interrupted initial installation/resume not yet exercised on this guest |
| Optional selection | Selected Kiwix, Homebox, Grocy and Kopia in the browser; four separate install jobs completed | Other optional modules were not installed |
| Install feedback | Actual Compose stages/output and persistent per-app summaries observed | No synthetic transfer progress or configuration-readiness claim |
| Live content | Official catalog search found a 2.5 MiB JavaScript Docs archive; normal queue downloaded, verified and indexed it after the fixes | Technical sample content, not an accepted preparedness collection |
| Native reader | Kiwix reloaded the library and served the archive and a local article without a login | Other native applications still require their supported setup |
| Kopia initialization | New encrypted repository initialized at the configured local test destination | This same-disk test repository is not independent disaster protection |
| Core recovery | Consistent core export/snapshot and isolated restore/application-data check succeeded | No live database replacement or full clean-machine recovery performed |
| Worker recovery | Worker-state snapshot and isolated export/database/generated-secret verification succeeded | No claim that every application dataset has been restored |
| Scoped WAN loss | Temporary unreachable IPv4 routes blocked default/public-DNS egress; no IPv6 default existed. External hostname and public-IP requests from core failed; LAN health, signed-out portal and a newly opened/reloaded Kiwix article worked | Browser device itself retained WAN; no physical whole-LAN disconnection or off-server browser-request block was tested |
| Network cleanup | Removed both temporary routes; private guest routing and an official HTTPS metadata request worked again | No unrelated host or guest networking changed |
| Kiwix removal | Browser uninstall completed; native Docker listing showed the reader removed; the retained ZIM matched its pre-removal SHA-256 | Reinstallation and post-reinstall reader opening remain unverified |
| Port conflict | A labeled disposable fixture occupied the reader port. Install job #11 failed at application-port preflight with the exact 8081/tcp conflict; error and individual retry persisted after browser refresh | No unrelated workload was stopped to resolve the conflict |
| Conflict cleanup/retry | Verified the fixture label and stopped only that auto-removing test fixture; accepted “Retry Kiwix using existing data?” | Retry completion was not observed before local browser controls became unavailable |

No new native account was provisioned for Homebox or Grocy, no authentication
was bypassed, and no SSH tunnel was introduced. Their current loopback-only
first-run instructions are a confirmed appliance-usability gap. Kopia's native
UI also remained local-only; the browser portal drove its tested repository
and managed snapshot actions.

#### Resume the live run

1. Inspect the submitted Kiwix retry; do not submit a duplicate blindly. Confirm
   successful installation, unchanged retained archive hash/library and
   anonymous article reopening. Keep core and other application data intact.
2. Exercise the selected application's backup/restore and data-preserving
   lifecycle, then address Homebox/Grocy native browser onboarding using
   supported upstream setup and permissions. Record any credential-entry
   handoff separately from product usability.
3. Continue interrupted-install/resume, full appliance preservation,
   phone/desktop LAN, remaining selected-module and clean-machine acceptance.
   Keep production core activation gated and defer the major UI overhaul.


### Live browser continuation — 2026-11-25

- Kiwix's previously submitted retry completed as job #12; the installation summary shows four completed selected applications. Reloading the retained JavaScript Docs globalThis article rendered its content from the native LAN reader without a login. This does not repeat the archive checksum comparison or prove physical disconnection.
- Kiwix managed content snapshot succeeded. The subsequent content-verify job succeeded with “Native content read verification passed; restore not tested”. File restoration and recovered native startup remain separate gates.
- Homebox consistent snapshot was accepted and observed running at “Check repository and application”. Completion, return to prior state and isolated restore verification are pending; inspect the existing job before retrying.
- Production core activation remains gated. Implementation baseline remains 8/13.

#### UI overhaul observations — deferred

| Observed issue | Proposed later improvement |
|---|---|
| Browser-native confirmation dialogs repeatedly coincide with Windows browser-control URL-confidence stops. The address remains visible in the browser inventory/accessibility tree; root cause is not confirmed. | Replace JavaScript confirm/alert dialogs with accessible in-page modals that retain the action, application, consequences and explicit confirm/cancel buttons. Preserve all existing server-side authorization and operation guards. Include keyboard focus, Escape/cancel and focus return. |
| Status refreshes collapse expanded application backup details and hide controls being used. | Preserve expanded sections, focus and scroll position across status updates. |
| Administration is one long page; narrow cards wrap setup text and push actions far below headings. | Group administration by task and give native setup/progress a clear dedicated view. |
| A generic “Failed to fetch” alert appeared without identifying the failed operation or recovery action. | Associate errors with their operation and provide a concrete next step. |
| Homebox/Grocy are running but their initial setup instructions require SSH forwarding. | Resolve supported secure browser onboarding as functional Phase 3 work; do not count an installed container as completed onboarding. |
| Snapshot creation continues to display its historical “verification pending” message after a separate verification succeeds. | Show linked current snapshot and verification evidence while preserving accurate historical job outcomes. |

These observations do not authorize bypassing native application security or the browser tool's policy checks. Live verification takes priority over visual redesign.


### Selected-module backup acceptance — 2026-11-25

| Live journey | Observed result | Remaining limit |
|---|---|---|
| Homebox consistent snapshot | Managed snapshot succeeded; portal subsequently showed running | Native account and representative user inventory have not been created |
| Homebox isolated restore | verify-snapshot succeeded: isolated restore and application data check passed | Not a live data replacement or native recovered-startup test |
| Grocy consistent snapshot | Managed snapshot succeeded; portal subsequently showed running | Native onboarding and representative stock/recipe data remain untested |
| Grocy isolated restore | verify-snapshot succeeded: isolated restore and application data check passed | Not a live data replacement or native recovered-startup test |
| Recovery inventory | Job #19 succeeded; output reported 5 of 13 reviewed sources present | Not atomic or a complete recovery package; no off-server copy claimed |
| Backup health | Connected filesystem repository; five latest captures have recorded verification: core, worker, Homebox, Grocy and Kiwix content; zero need review, zero schedules due | Repository remains the local same-disk test destination; optional absent sources are not verified |
| Kiwix restart | Independent restart job succeeded; a fresh reader tab rendered the retained globalThis article from the native LAN URL | No new archive-hash comparison or physical disconnection test in this slice |

The user confirmed Homebox's restore dialog. A dedicated browser tab subsequently
allowed Grocy confirmation handling through the browser's dialog API; intermittent
focus/click timeouts still occurred, but the exact existing jobs were inspected
before any further submission. Do not infer a failed operation from a browser
timeout or blindly duplicate it.

Additional deferred UI issue: inventory output counts 13 reviewed sources while
backup health counts 12 and separately lists TAK as excluded. Make the denominator
and exclusion rules explicit, and distinguish uninstalled optional sources from
missing protection for installed applications.

Phase 3 remains 8/13 implemented. Native Homebox/Grocy onboarding is blocked by
loopback-only initial setup instructions; browser onboarding must be resolved
without SSH tunnels before LAN usability can pass. Physical phone/LAN,
interrupted installer/resume, full-appliance preserving uninstall/reinstall,
representative native application data, bare-metal/clean-machine recovery and
reviewed production core update/handoff remain open. Production core activation
is still gated.


### Lifecycle and recoverable content acceptance — 2026-11-25

- Homebox stop and start jobs both succeeded; the application returned to running.
- Grocy stop and start jobs both succeeded. The native effective Kopia policy read succeeded for application/grocy (latest 10, hourly 48, daily 7, weekly 4, monthly 24, annual 3). No retention policy was changed.
- Browser removal of the JavaScript Docs ZIM moved it into Removed archives and left no active local ZIM entry. Restore returned the same named 2.5 MiB archive to indexed status. A fresh native reader tab rendered the globalThis article afterward. Permanent deletion was not used. This is recoverable local removal/restore, not Kopia file restoration or a new full-file hash comparison.
- A temporary 390-by-844 desktop viewport rendered stacked portal application cards; measured page width was 375 CSS pixels and viewport width 390, with no horizontal page overflow at that observation. The viewport override was reset. Physical phone/LAN access and all responsive states remain unverified.
- Resource inspection could not proceed because the existing Proxmox tab displayed an expired login session. No hypervisor or guest configuration was changed.

UI follow-up: the stopped Homebox/Grocy cards expose both Start and Install, plus Stop, leaving the distinction unclear for an ordinary user. Prefer actions appropriate to current installed/running state and clear explanations where reinstall is needed. Native browser confirmation handling worked through the dedicated browser dialog API, though click/focus timeout reports still required inspecting actual job admission.

Native setup remains a functional blocker: both current module READMEs still require SSH forwarding before initial LAN sharing. Do not mark module onboarding complete based on snapshot/lifecycle checks. Phase 3 remains 8/13; production core activation remains gated.


### Real guest resource and native reinstall acceptance — 2026-11-25

Proxmox sign-in was restored. All following shell checks ran in the embedded
console of guest 115, hostname aftergrid, under /opt/aftergrid.

- Point-in-time guest sample: 4096 MiB memory total, 268 MiB used, 3827 MiB available; 85 MiB swap allocated out of 512 MiB. Memory PSI some/full averages were 0.00 for 10/60/300 seconds. This does not measure current swap-in/out or certify minimum requirements. Filesystem used 3.6 GiB with approximately 90 GiB available.
- Six selected containers were up. Docker memory samples: core 47.68 MiB, worker 96.84 MiB, Kiwix 9.188 MiB, Kopia 48.03 MiB, Grocy 28.54 MiB, Homebox 17.64 MiB. These are samples after the preceding tests, not load/peak measurements.
- Homebox was cleanly stopped through the portal, then its native database SHA-256 recorded. Browser uninstall succeeded and removed its container. The retained database passed sha256sum -c. Browser reinstall succeeded as job #27, native container health returned healthy, loopback HTTP returned 200, and the database still matched the original stopped-state hash.
- Grocy underwent the same stopped-baseline/uninstall/reinstall journey. Its retained native database passed the original SHA-256 check after removal and after reinstall. Native HTTP returned 302 and following the native redirect returned 200.
- For each application's uninstall and reinstall, exact IDs and StartedAt values for the other five AfterGrid containers matched their respective pre-test baseline. No unrelated container was changed.
- Both native databases remain initial/pre-onboarding databases. No representative inventory, user-account continuity, QR scan or browser-native account creation is claimed.

Additional UI follow-up: application status can briefly show the prior state or
“starting or unhealthy” after a completed lifecycle job. Installation summaries
correctly describe historical attempts but need clearer separation from current
operational state. Use job completion together with refreshed native readiness;
do not infer current readiness from the historical installation summary alone.

Core/full-appliance preservation, interrupted initial installation, phone/native
onboarding and clean-machine recovery remain open. Phase 3 stays 8/13 and
production core activation remains gated.


### Scoped core recreation and installed-host guards — 2026-11-25

- Captured optional application container IDs/StartedAt values and exact core/worker image IDs.
- Removed only the core and worker containers using the existing core Compose project, without removing volumes or networks. All four optional applications remained running. A fresh native Kiwix browser tab rendered the retained article during the core outage.
- Recreated only core/worker with --no-build --pull never and waited for native health. Both returned healthy. Exact core/worker image IDs matched the pre-test baseline; optional app IDs and start times were unchanged.
- Reloaded the portal: existing administrator session survived, installation records included Homebox job #27 and Grocy job #30, restored content metadata remained present, and backup health reconnected to the filesystem repository with all five prior verification records.
- The installed script's --check refused the existing /opt/aftergrid root with exit 1; --resume refused the completed installation because no unfinished marker existed, also exit 1. Configuration checksum checks passed and all six container identities/start times were unchanged afterward.
- These are current-image container removal/recreation and safe refusal tests, not a new release activation, an interrupted fresh install, deletion/recovery of persistent data or full clean-machine installation. Production activation remains gated.

UI follow-up: lifecycle and recovery status messages can remain “queued” after
the activity job succeeds; correlate messages with their jobs and replace them
with terminal results. Recovery health evidence must remain explicit about
historical verification versus live protection.

Physical-phone LAN acceptance has been requested separately. No result is
assumed. Native account onboarding remains blocked by SSH-only setup; genuine
fresh-install failure/resume and clean-machine recovery still need isolated
acceptance. Phase 3 implementation baseline remains 8/13.


### Kopia reinstall and physical-phone confirmation — 2026-11-25

- Stopped Kopia through the portal with no active backup job, then recorded SHA-256 for all 29 existing files under its repository and configuration directories.
- Browser uninstall completed and removed the Kopia container. All 29 retained files passed the original checksum list.
- Browser reinstall completed and the existing filesystem repository reconnected. All 29 prior files still passed their checksum list. Exact IDs and start times for the other five containers were unchanged.
- A new Kiwix content-verify job then succeeded against the prior managed encrypted snapshot: native content read verification passed. This confirms post-reinstall access to retained encrypted backup content, not a full restore or independent disaster backup.
- The user explicitly reported that a physical phone on the same LAN opened both the portal and a Kiwix article successfully. This is user-observed evidence, distinct from the earlier desktop viewport simulation.

Remaining live gates: secure Homebox/Grocy browser onboarding and populated
native user journeys; genuine failed fresh-install/resume on a separate empty
environment; full clean-host recovery and resource/load/bare-metal acceptance;
reviewed production core activation/handoff. Current-image core recreation and
all four selected optional application removal/reinstall have now been exercised
individually with data-preservation evidence. No persistent volumes, application
data or unrelated workloads were deleted.


### Additional acceptance guest authorized and created — 2026-11-25

The user explicitly authorized one additional disposable LXC for interrupted
installation and clean-host testing. ID 116 was absent from the live inventory
and selected by Proxmox's creation wizard. Created aftergrid-acceptance from the
existing Ubuntu 24.04 amd64 template: 2 cores, 1024 MiB RAM, 512 MiB swap,
20 GiB local-lvm root disk, unprivileged mode, nesting, vmbr0 and IPv4 DHCP.
Creation and start tasks both returned OK. Guest hostname and DHCP address
192.168.4.73 were verified in its console. No Docker executable or existing
/opt/aftergrid root was present.

Initial package preparation stalled because inherited host DNS pointed to
Tailscale resolvers inaccessible from the fresh guest. Set explicit DNS only
for CT116 (8.8.8.8 and 1.1.1.1), preserved the guest's prior resolv.conf, and
applied matching nameservers inside that guest. Resolution and official Ubuntu
package metadata downloads then worked. Host DNS, CT115 and unrelated workloads
were not modified. Package preparation is not installer acceptance.

Next test: run pinned unmodified installer preflight, inject a temporary
port-8080 listener only after the installer publishes its pending installation,
observe real Compose startup failure, remove only that fixture and resume.
Compare preserved configuration and setup-token hashes without recording token
values. Genuine failed-start/resume and clean-host recovery remain pending.


### Failed fresh install and interrupted resume — 2026-11-25

On the explicitly authorized disposable CT116 (Ubuntu 24.04, 2 cores, 1 GiB RAM), the pinned cfb0f3e installer passed read-only preflight before Docker or /opt/aftergrid existed. A temporary host listener admitted only after pending installation publication forced a real Compose portal-port binding failure. The installer returned 1 and retained the pending marker, configuration and original setup token. The fixture was removed without modifying unrelated workloads.

The first resume exposed a real defect: Docker 29.10.1 rejects the installer's negative label filter with invalid filter 'label!'. The correction reads supported project/port fields and excludes only the already validated core project. Regression coverage checks own-core exclusion, labeled and unlabeled foreign conflicts, native listeners, unexpected project/root/service/configuration labels and inspection failure. The regression fails against the original script; bash syntax validation and all 8 installer tests pass on native Linux. Windows Bash was unavailable and is not passing test evidence.

With the patched installer from caa13a1b209944e3018df85a374007f4dfb5100c:

- A disposable foreign Docker fixture publishing 8080 was refused with the expected conflict message and exit 1. The installer did not stop it. After checking its acceptance label, only that fixture was removed. Configuration/token hashes stayed unchanged.
- A real resume interrupted by SIGINT timeout returned 124 after entering the Docker build/start phase. The pending marker and all three original hashes remained intact.
- Normal --resume returned 0, cleared the pending marker, and left only core and worker containers, both healthy. The original .env, compose.yaml and one-time setup-token hashes all passed. Native LAN health returned {"status":"ok"}.

This closes the failed-start/interrupted-resume runtime gate for the corrected installer on this guest. Source core/worker remain the pinned cfb0f3e release with the focused installer correction applied; this is not a production updater activation or full clean-host recovery. Native logs and exit receipts remain under /root/aftergrid-* in CT116; token values are not recorded here.

The browser client blocked navigation to http://192.168.4.73:8080/ with ERR_BLOCKED_BY_CLIENT, so fresh administrator setup, browser wizard and guest reboot persistence are still pending. Server health alone does not close these browser journeys. CT115 and unrelated workloads were not modified by this slice. Phase 3 implementation baseline remains 8/13; production core activation stays gated. Existing deferred UI observations, including replacing browser-native confirmations with accessible in-page modals, remain on the later overhaul list.


### Fresh browser setup and guest reboot — 2026-11-25

The browser setup page at CT116's normal LAN URL became readable despite the earlier navigation error. No browser restriction was changed or bypassed. The original preserved token created a disposable administrator and named the server AfterGrid acceptance. Logout returned to the signed-out portal with administrative controls hidden; normal administrator login succeeded. Selected Skip for now with no optional applications installed.

Rebooted only CT116 using its native OS. The changed boot ID confirmed an actual reboot. Core and worker automatically returned healthy, native LAN health returned OK, and the browser reloaded the named portal with its administrator session intact. Administration was visible and the dismissed first-run wizard remained absent. Only core and worker containers existed after reboot. This passes core-only first-run and guest reboot persistence on this Ubuntu/Proxmox configuration, not full clean-machine recovery or minimum-resource certification.

Installer fix and regression/evidence changes were merged through PR #1, squash commit 49ce77898c84b95a35ed2a86f4a9253f911b248d. Eight installer regression tests passed on native Linux before merge; hosted checks were still running at merge and are not claimed passed. Phase 3 remains 8/13 implemented, with open items 9–13 as summarized above.

UI observation: a successful sign-out briefly displayed Administrator login required on the shared portal. Make intentional sign-out a neutral confirmation and prevent background administrative requests from producing a misleading authentication error. This joins the deferred modal/status/layout improvements; major redesign remains deferred.


### Real empty-daemon recovery and recovered LAN acceptance — 2026-11-25

Source CT115 was captured using existing guarded native jobs for Grocy, Homebox, Kiwix content, core and worker, with fresh verification and sealed inventory (source jobs #35–45). All selected app databases were still initial/pre-onboarding data; no populated stock, QR or native account continuity is claimed. The first combined create-package attempt refused a mistyped repository password and restored the original containers. After inspecting the seal, source state and installed release, the same sealed inventory was packaged successfully through pack_and_resume with the saved credential. All six source container IDs were unchanged, native health returned OK, a fresh browser article rendered, and maintenance was explicitly released.

- Preserved CT116's previous /opt/aftergrid, Docker and containerd state under /root/acceptance-before-recovery. The active replacement daemon had zero images, containers and volumes before restoration; only built-in Docker networks existed. No pruning or data deletion was needed.
- Copied the private package with native Proxmox transfer. The source, host transfer and CT116 archive SHA-256 values matched. All package checks passed before restore.
- Running utilities from inside the copied package initially created Python __pycache__ files, and asset verification correctly refused that modified file set before image import. Preserved the rejected copy, re-extracted the original archive and used matching external recovery utilities with python3 -B. No manifest/hash checks were relaxed. Document this prerequisite clearly.
- CT116 had an unreachable IPv4 default route plus an explicit public DNS-route block, with no IPv6 default. External public-IP connectivity failed before restore. Actual Docker archive import loaded all six exact captured images; there was no image-reuse shortcut, pull or build.
- restore-package returned 0. Core/worker, Kopia, Grocy, Homebox and Kiwix started from the recovered state. Native Homebox and Grocy HTTP returned 200. The restored ZIM matched the source full-file SHA-256, and native HTTP returned the expected globalThis article.
- Raw secret-file hashes differed because reconstruction rewrites JSON formatting. Canonical comparisons proved the original Homebox pepper and both Kopia credential values were unchanged; no secret values are recorded here.
- Original AfterGrid administrator login succeeded on the guarded replacement. The initial read-only independent repository connected. Lifecycle was correctly refused before activation. Opted into writes only on the independent working copy, then enabled restricted offline mode.
- On CT116, Kiwix stop/start jobs #44/#45 and a new managed core snapshot plus isolated restore verification #46/#47 all succeeded. Update, new install and download submissions were refused with HTTP 409. The original package still verified unchanged.
- Host public-IP curl failed with exit 7 and a socket connection from the recovered core returned errno 113 while the isolation routes were active. This is guest-scoped WAN isolation; the hypervisor, LAN and browser device were not physically disconnected.
- Manually restored the assigned private LAN address in the recovered .env and recreated only core/worker through the fixed recovery Compose overrides with no pulls/builds. Browser login using the original administrator passed. Browser Kiwix stop/start reapplied its LAN binding; a fresh native browser tab rendered the restored article at CT116's LAN URL. Homebox/Grocy/Kopia stayed loopback-only.
- Removed only the two temporary isolation routes, then rebooted CT116. Changed boot ID, all six exact running image IDs, package checksums, portal health, browser administrator-session persistence and reader reload passed after reboot. No claim of WAN-isolated boot is made after route cleanup.
- The user explicitly reported that a physical phone on the same LAN opened both the recovered portal and a Kiwix article successfully.

Point-in-time post-recovery sample on CT116: 1024 MiB RAM total, 291 used, 732 available; 84 MiB swap allocated of 512. Memory PSI some 10/60/300 averages 0.00/0.09/0.13 and full 0.00/0.09/0.10. Root disk used 5.6 GiB with 13 GiB available, including preserved baseline, duplicate test archives and rejected package copy. These are observations, not minimum/peak/load certification.

Private recovery inputs and receipts remain in CT115/CT116 and the native transfer location on the host. Source CT115 is online and unsealed. CT116 now runs the recovered restricted-offline installation at its own LAN address, with temporary isolation routes removed and the original acceptance installation preserved. No unrelated workload was changed. MicroTAK was not installed or selected. This passes the real selected-module empty-daemon recovery drill on this Proxmox guest; populated native-account/inventory journeys, bare-metal acceptance and a released normal-mode recovery handoff remain separate. Phase 3 implementation stays 8/13; production core activation remains gated.

Additional UI/workflow findings: recovery errors hide the failing phase/cause; the CLI needs clear credential/input versus Docker/repository failure guidance without leaking secrets. Recovery utilities must stay outside the immutable package, or suppress bytecode writes. Recovery's safe loopback-first start still requires an advanced manual LAN handoff. Restricted recovery shows uninstalled/unmapped modules as unavailable and still offers some actions that admission later refuses; explain the recovery mode and show usable controls. These join the deferred modal/status/layout list. Secure Homebox/Grocy browser onboarding is the next functional blocker, before visual redesign.


### Edge continuation and recovered worker backup — 2026-11-26

Continued against the recovered restricted-offline CT116 portal at its existing LAN address. Normal administrator login passed in Edge. Kiwix's library, JavaScript reference index and retained globalThis article rendered in a fresh tab without native-reader login. No guest routing, application sharing, credentials or container lifecycle was changed in this slice.

- Live backup health reported a connected filesystem repository and one worker review item: the restored interrupted snapshot job #43. The prior successful worker snapshot/verification remained historical evidence.
- A new managed worker-state snapshot, job #50, succeeded on the recovered working repository. Isolated worker restoration and application-data verification, job #51, succeeded against the latest successful capture.
- Fresh recovery inventory job #52 succeeded. Refreshed backup health showed five of twelve reviewed sources with recorded verification and zero needing review. Worker evidence linked capture #50 to verification #51 and inventory #52, with matching inventory present and no pin present. Managed schedules remain disabled/deferred in recovery mode. This is current working-repository evidence, not independent disaster protection or a new portable package.
- The portal still reports Homebox and Grocy running but unavailable from the browser, with SSH-forwarding setup instructions. Their native account and populated inventory journeys remain blocked. Share On LAN was not used before native security setup.
- Core update status still explicitly states activation is not released. No updater was activated. No unrelated guest or workload was modified.

Phase 3 remains **8/13 implemented**; this checkpoint adds recovered-worker runtime evidence without closing items 9–13. Next functional work is supported secure Homebox/Grocy onboarding through the browser, followed by representative inventory/recipe/QR journeys and backup verification of that populated state. The restricted recovered installation must not be mistaken for a normal-mode onboarding environment.


### Browser onboarding development handoff — 2026-11-26

Draft [PR #3](https://github.com/ramseys1990/AfterGrid/pull/3) implements private Homebox/Grocy browser account setup through fixed native APIs while keeping their ports local-only. The candidate is installed only as a scoped development portal overlay on CT115; runtime source is `0d0c4e7a9c218cfe80b65fd3d877352c7fd4e185`. All 51 native-setup/core tests passed in isolated Linux testing, and a real native Grocy administrator login probe passed without changing its password. Core-only Compose recreation returned healthy; the worker and all four optional applications retained exact container IDs and start times. Edge preserved the portal administrator session and rendered both setup forms.

The operator must now enter/save native passwords and submit the Homebox creation and Grocy default-password replacement forms. No native account-change success is claimed yet. Then verify account results before explicit LAN sharing, populated inventory/recipe/QR journeys and fresh backup/restore checks. Keep the draft open pending those results. CT116 and production updater activation remain unchanged; Phase 3 is still **8/13 implemented**. Detailed candidate evidence and preserved development baseline/override locations are recorded in the PR's roadmap changes.


### Native account setup and configured-state backups — 2026-11-26

The operator completed both native account forms on CT115. Edge showed Native account login verified for Homebox and Grocy. Homebox used the local account identifier prefilled by the setup page; Grocy's successful setup flow includes verified new native admin login and explicit rejection of the former default password. No account passwords are recorded here. This passes the candidate's native browser setup submissions, not the separate native application LAN-login or populated inventory journeys.

- Homebox managed snapshot #46 succeeded after account creation; isolated restore verification #48 succeeded against that latest successful snapshot.
- Grocy managed snapshot #47 succeeded after password replacement; isolated restore verification #49 succeeded against that latest successful snapshot.
- Refreshed source-guest backup health showed a connected filesystem repository, five of twelve reviewed sources with latest-capture verification and zero needing review. The application verification details linked #46/#48 and #47/#49 respectively. This is same-disk working-repository evidence, not independent disaster protection or a replacement of live application files.
- Native JavaScript confirmation dialogs caused browser-control timeouts. Existing job state was inspected before retrying. Edge's native controls allowed the intended confirmation and job completion; no duplicate snapshot success is assumed from a timeout.

Explicit LAN-sharing approval was requested for Homebox port 8082 and Grocy port 8083 and is still pending at this checkpoint. Neither sharing action was submitted. The operator supplied disposable credentials for subsequent native login, but their values are omitted from repository evidence. Next: obtain the pending access-change confirmation, share the two apps through the existing worker, verify native login and closed Homebox registration, then populate representative equipment/stock/recipes and verify fresh backups. CT116 and production updater activation are unchanged. Phase 3 remains **8/13 implemented**; [PR #3](https://github.com/ramseys1990/AfterGrid/pull/3) remains draft for continuing live acceptance.


### Populated native LAN journeys and restore inspection — 2026-11-26

The operator explicitly approved both application LAN bindings and completed the portal sharing actions after browser-control confirmation failures. Both share jobs succeeded. Native Homebox login on port 8082 and Grocy login on port 8083 passed. Homebox visibly reported Registration Disabled. Existing application authentication remains enabled.

- Homebox: created Acceptance storage and its Acceptance lantern equipment record, quantity 1, asset ID 000-010. Reload retained the parent, item and quantity. The rendered Page URL QR encodes the correct native LAN item URL. Physical-phone scanning and hostname-stable printed labels remain unverified; the current QR uses the guest IP.
- Grocy: created Acceptance pantry, Acceptance rice and a three-pack purchase due 2027-11-26; consumed one pack and verified two remaining. Created Acceptance rice meal with a one-pack ingredient, and the recipe correctly reported enough stock. Reload retained the recipe and two-pack availability. Early automation submissions failed because native quantity conversion had not received keyboard events; no successful duplicate purchases occurred. Triggering the native quantity control resolved the test input issue without a product change.
- New source captures succeeded: Homebox #52, Grocy #53 and worker #54. Exact-source isolated verification jobs #55/#56/#57 succeeded. Successful exact-source checks intentionally remove their private verification directories, so separate latest-snapshot verification #58/#59 retained inspectable copies. Logs confirmed the same Homebox and Grocy snapshot IDs as #55/#56.
- Read-only SQL inspection of those private restored copies confirmed Homebox storage and lantern records (quantity 1), Grocy pantry and rice records, stock amount 2 with the expected due date, recipe name and ingredient tuple (recipe 1, product 1, amount 1). Live data was not replaced. Native application startup from these populated restored copies has not been tested.
- Both native applications remained authenticated after backup stop/start and browser reload. This is application-consistent backup and populated isolated-restore evidence on the same-disk working repository, not an independent disaster backup or a new portable recovery drill.

Next acceptance: scan the open Homebox item QR with a physical phone on the same LAN, confirm native login/item access, and review stable hostname provisioning before printed-label acceptance. Review/integrate PR #3 and address its review feedback before treating the development overlay as a released workflow. CT116 remains unchanged and restricted; production core activation stays gated. Phase 3 remains **8/13 implemented** with the broader open criteria preserved.


### Physical-phone Homebox QR confirmation — 2026-11-26

After requesting the Homebox account email, the operator explicitly confirmed that scanning the open item QR on a physical phone opened Acceptance lantern. This closes the user-observed phone QR-opening gate for the current LAN item URL. The QR uses the guest IP; stable hostname provisioning and printed-label continuity across address changes remain unverified. No broader phase completion or populated replacement-app startup is implied. Phase 3 remains **8/13 implemented**; production core activation stays gated. Next: review PR #3 feedback and integration, then stable label addressing and the remaining recovery/resource acceptance criteria.


### Native inventory browser setup candidate — 2026-11-26

Implemented a focused browser onboarding candidate on branch `feat/native-inventory-browser-setup` (runtime code `0d0c4e7a9c218cfe80b65fd3d877352c7fd4e185`). AfterGrid administrators can create/verify a Homebox native account and replace Grocy's default password or verify an existing native admin. Requests use fixed native endpoints, bounded transient credentials, native login checks and session cleanup. Passwords do not enter worker jobs or portal storage. Sharing remains a separate explicit action; no new proxy, daemon, identity service or database was added. Recovery restrictions, administrator authentication, same-origin checks and maintenance admission stay active.

- Ten native HTTP client tests passed on Windows; the full portal suite could not import Linux-only `fcntl` there and is not claimed passed on Windows.
- On CT115, an isolated container running the existing core image plus candidate source passed all **51 native-setup/core tests** on Linux, with three read-only pytest cache warnings. Two earlier recovery test fixtures incorrectly enrolled an administrator after enabling recovery restrictions; they were corrected to enroll before enabling the guards.
- A real Grocy login probe exposed absolute same-origin redirects. The candidate accepts only the exact native success/invalid-login locations without following redirects. The corrected client verified the installed native admin login and logged out; the default password was not changed by that probe.
- Preserved the original core source files and image, captured worker/optional-app IDs and start times, and built a development overlay from the exact installed core image without pulls or network access during build. Recreated only core via Compose with no dependencies, no build and no pull. Native health returned OK; exact worker, Homebox, Grocy, Kopia and Kiwix identities/start times were unchanged.
- Edge retained its AfterGrid administrator session after the portal recreation. Both native setup pages rendered through the existing LAN portal origin; the cards expose Set up native account instead of SSH-forwarding instructions for these two apps.

Follow-up results recorded above supersede the original pending status: both operator account submissions, explicit LAN sharing, native login, populated journeys, isolated restore inspection and physical-phone QR opening passed. CT116 remains unchanged in restricted recovery mode. This scoped development patch is not a released production updater activation; Phase 3 stays **8/13 implemented** until its acceptance conditions are met.

The source guest's baseline and receipts are retained under `/root/aftergrid-native-setup-original` and `/root/aftergrid-native-setup-*`. Its development Compose image override is `/root/aftergrid-native-setup-override.json`; the original image is retained as `aftergrid-native-baseline:20261126`. Preserve these when continuing or rolling back this candidate.



### Onboarding review follow-up — 2026-11-26

The native HTTP test server now derives its absolute redirect from its loopback listener rather than an incoming Host header, resolving the response-splitting review finding without changing production code. All ten native HTTP-client tests passed on Windows after this correction. The earlier 51-test Linux run remains evidence for the unchanged production implementation; Linux portal tests were not rerun for this fixture-only correction. Native onboarding is ready for integration review; Phase 3 production updater, whole-appliance reinstall, stable addressing and resource/platform gates remain open.


### Phase 3 continuation: integrated onboarding and appliance runtime — 2026-11-26

Merged PR #3 as `ba7a6639ffd403fe0c94991c34a515c80774f12b` after the native fixture header correction and ten passing HTTP-client tests. This integrates the reviewed browser onboarding code into main; the live CT115 image remains the previously tested development overlay, not a production core-updater deployment. Hosted results for the final merge are not assumed.

**Populated native restored startup.** Copied the retained Homebox #58 and Grocy #59 restored data to new private directories on CT115. Started temporary containers from each exact installed native image with network none, no published ports and only the copied data mounts. Homebox returned native HTTP 200 and retained Acceptance storage/lantern quantities. Grocy returned its normal redirect at root; after correcting the probe to follow that local redirect, the native login page returned 200, and the copied stock amount 2, recipe and one-pack ingredient remained correct after startup. No login to the restored copies or portable cross-host recovery of this newly populated state is claimed. Both temporary containers are stopped; private copies remain under /root/aftergrid-populated-native-20261126. Source Homebox/Grocy remained running at their earlier start times.

**Core removal and reinstall.** With no pending worker jobs or recovery hold, captured exact installed core/worker image IDs in a private Compose override. Used scoped Compose stop and rm for only core and worker; no volume removal, network removal, image pull, source build or global down. Persistent-file hashes across the core bind and worker-state volume matched after removal. Recreated both services from their exact local images with no dependencies/build/pull and waited for native health. Both container IDs changed as expected and both were healthy. All four optional application IDs and start times were identical, with applications running. The browser portal retained its administrator session and activity/install history; native Homebox/Grocy records remained visible. Receipts are retained under /root/aftergrid-core-reinstall-20261126 and its adjacent log. Early fixture syntax/mount-admission failures occurred before stopping services; they are not product failures. This passes the underlying removal/recreation/data-preservation operation, not a released one-command appliance uninstall/reinstall workflow.

**Bounded concurrency/resource evidence.** Six concurrent workers made 60 total LAN requests, ten each to source portal health, Kiwix root, Homebox root, Grocy login, recovered portal health and recovered Kiwix root. All returned 200; elapsed 0.8 seconds, p95 0.456 seconds and maximum 0.66 seconds. This is a short small-page exercise, not sustained capacity, authenticated write load or map/large-content sizing. Source CT115 afterward reported 4096 MiB total, 278 used, 3817 available and 85 MiB allocated swap; memory PSI averages were 0.00. Each of its six installed services reported no OOM kill and restart count zero at inspection.

The recovered CT116 was only inspected, with no policy, routing or lifecycle change. It reported 1024 MiB total, 162 used, 861 available, 137 MiB allocated swap, memory PSI averages 0.00, and 5.6 GiB root usage with 13 GiB available. All six recovered services reported no OOM kill and restart count zero. Swap allocation and point-in-time figures do not establish peak/minimum requirements.

**Authentication review of the current catalog.** Keep native authentication for editable/private applications; no account bypass is introduced. Kiwix is the already-tested account-free reader. Homebox/Grocy now have tested portal account forms and explicit sharing. Kopia keeps generated native credentials and administrator-only controls; normal managed backup actions are available in the portal. MeshMonitor has generated native credentials but radio setup is unverified. Kolibri, Jellyfin and DokuWiki still require native private first-run setup; their supported browser-only onboarding is not solved by the Homebox/Grocy change. Maps/routing have no separate user login in their reviewed module definitions but still require content/native acceptance. MicroTAK remains excluded from this live test as requested, with certificate enrollment unvalidated. Do not mark the broader authentication row complete merely because the two inventory apps passed.

The operator explicitly reports no reserved/static test IP or local DNS name and no available bare-metal test machine. Physical-phone QR opening works at the current DHCP address; address-change/printed-label continuity and bare-metal acceptance remain unverified. These are unavailable prerequisites, not waived or passing tests.

Remaining Phase 3 closure gates:

| Item | Remaining concrete condition |
|---|---|
| 9 — core update | Reviewed actual release build, narrow manually approved production execution/browser handoff, and native activation/rollback acceptance; current production activation remains deliberately disabled |
| 10 — appliance reinstall | Turn the verified scoped operation into a documented ordinary-operator workflow with preserved settings, data and supported recovery variants |
| 11 — stable LAN deployment | Establish and verify reserved addressing/local naming for durable labels; current IP-based LAN and phone access already passed |
| 12 — simplified native onboarding | Resolve private first-run access for the remaining offered editable catalog apps, retaining supported native permissions |
| 13 — requirements/platform | Sustained/peak representative use and generic bare-metal acceptance; no suitable bare-metal machine is available |

Phase 3 remains **8/13 implemented**. The new runtime subchecks are passed evidence, not justification for silently removing these acceptance conditions. No unrelated workload was modified and no production updater was enabled.


### Bare-metal deferral and supported reinstall procedure — 2026-11-26

The operator explicitly deferred bare-metal verification for now. Preserve that test as **deferred/unverified**, not a passing test or an available-machine blocker for continuing repository and Proxmox work. Sustained guest-based acceptance and the remaining software gates continue.

[Appliance maintenance](APPLIANCE_MAINTENANCE.md) documents the verified distinction between ordinary browser optional-app removal/reinstall and exceptional host-level portal/worker removal/reinstall. The latter uses scoped native Compose, exact retained image identities, preserved data and an explicit repeatable startup command. Normal-mode instructions refuse recovery mode and maintenance; recovered/update installations must retain their own reviewed overrides. The exact published normal-mode instruction block passed Bash syntax validation and returned 0 on CT115. Both core services returned healthy; optional app IDs/start times matched before/after, and portal health, administrator session, install history and native reader remained available. The published startup-only retry also returned 0. On recovered CT116 the same block refused recovery mode with exit 1 before any container mutation. This completes row 10, including the documented exceptional host workflow; no browser action can reinstall an absent portal.


Current Phase 3 checklist: **9/13 complete** (rows 1–8 and 10). Rows 9, 11, 12 and 13 remain open. Bare-metal verification is explicitly deferred by the operator; it is not claimed passed. The production updater remains gated. Retain /opt/aftergrid/.core-reinstall-images.json on CT115 and its installed source/settings for any future repeat of the tested startup command.


### Published reinstall closeout and longer LAN exercise — 2026-11-26

PR #4 merged as `9e129bc4438a8611b2b4dc8ad165e67857dfdd77`. Safe uninstall/reinstall row 10 is complete on the tested selected-module deployment: the exact published normal-mode command block and startup-only retry returned 0 on CT115, all four independent app identities/start times matched, and the portal session/history and native reader remained available. The same normal-mode block refused recovered CT116 before mutation. Preserve the image-identity receipt with its unchanged source and settings. This is host maintenance for an unavailable/removed portal; ordinary optional-app removal remains in the dashboard.

A longer bounded read exercise used six concurrent workers for 45.19 seconds against source portal HTML, the native globalThis article, Homebox landing page and Grocy login, plus recovered portal HTML and the same recovered article. All **1,030/1,030** requests passed HTTP/body checks, totaling 12,523,103 bytes. P95 latency was 0.038 seconds; maximum was 0.060 seconds. Per-target request counts were 173, 177, 177, 154, 172 and 177. The request report completed at epoch 1795698442.

CT116's independent 40-sample, one-second memory observation ran from epoch 1795698428.275 to 1795698468.402, overlapping approximately the last 14 seconds of that request exercise and then observing idle recovery. Minimum available memory across its full observation was 862,460 KiB on 1,048,576 KiB total; maximum allocated swap was 141,096 KiB. Ending memory-PSI averages were 0.00. All six services on each guest were running with no recorded OOM kill and restart count zero when inspected afterward. Both temporary measurement processes completed; no background service was installed. Private reports remain under /root/aftergrid-sustained-lan-20261126* on CT115 and /root/aftergrid-lan-memory-20261126* on CT116.

This establishes a bounded small-dataset portal/reader read workload on the selected deployment, not authenticated concurrent writes, multi-minute endurance, download/backup contention, large libraries, map/routing builds or universal minimum hardware requirements. Resource/platform row 13 retains those limits, with bare-metal verification explicitly deferred at the operator's request. Phase 3 remains **9/13 complete**; core production updates, durable addressing, broader catalog onboarding and remaining resource acceptance are not silently waived.
