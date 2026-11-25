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

Baseline: **8 of 13 implementation items complete**. A complete row preserves the existing development checklist; it does not imply clean-host or browser acceptance. Runtime evidence is recorded separately below. Production core activation remains gated.

| # | Checklist item | Implementation status | Real-machine acceptance |
|---|---|---|---|
| 1 | Installer audit | Complete | Fresh Ubuntu 24.04 guest install passed through healthy core/worker and LAN setup page |
| 2 | Read-only installation preflight | Complete | Passed on fresh Ubuntu 24.04 unprivileged Proxmox guest |
| 3 | Existing Docker workload protection | Complete | Worker and four app IDs/start times unchanged during scoped test core rebuild; deliberate conflicting fixture preserved; existing shared-host coverage remains partial |
| 4 | Interrupted installation recovery | Complete | Real failed-start/resume acceptance pending |
| 5 | First-run setup improvements | Complete | Administrator setup, logout/login, guest controls and portal restart/session persistence passed |
| 6 | Application selection validation | Complete | Four-app wizard batch passed; independent Kiwix retry completed as job #12 after resolved port conflict |
| 7 | Installation progress reporting | Complete | Real per-app Compose activity and completed-stage summaries observed; failed summary persisted after refresh |
| 8 | Application port conflict handling | Complete | Real occupied-port rejection passed before image pull; error and retry survived refresh; Retry job #12 completed; native retained article reopened |
| 9 | AfterGrid core updating | Open — production activation gated | Native disposable tests passed; reviewed production release/handoff pending |
| 10 | Safe uninstall and reinstall | Open | Kiwix uninstall passed; archive SHA-256 unchanged; Kiwix reinstall/reopen and subsequent independent restart passed; core/full-appliance removal remains untested |
| 11 | LAN deployment validation | Open | Desktop setup, signed-out portal and anonymous Kiwix reading passed; guest WAN-routing-loss test passed; phone and native app onboarding pending |
| 12 | Module authentication and simplified onboarding | Open | Native browser setup required; SSH-only initial setup remains a usability gap |
| 13 | System requirements and clean-host acceptance | Open | Core plus four essentials installed on 4-core/4-GiB/100-GiB guest; guest WAN-loss reading passed; full resource, bare-metal and clean-machine recovery acceptance pending |

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
