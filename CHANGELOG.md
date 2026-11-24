# Changelog

## 0.8.26-dev
- Formalize unsupported MicroTAK 0.18.1 recovery scope after pinned-source review: block guided restore and require explicit omission acknowledgment for portable packages containing its image. Preserve strict diagnostic shutdown checks and native lifecycle. CI pending.
- Add persistent portal recovery maintenance, capture-owner backup admission, verified inventory seal and optional required host package handoff. Explicit release; native writers and source shutdown remain operator-controlled. CI pending.
- Add fresh capture coordinator using existing authenticated native snapshot/verification jobs; bind final inventory to exact new job IDs and refuse observed concurrent work. Operator-controlled maintenance and service stops remain required. CI pending.
- Add portable recovery package creation, verification and guided restore commands. Require a quiescent source, captured image inventory, exact verified snapshot selection, native manifest presence on copied repository, and deterministic repository byte digest.
- Extend guided CI to assemble and verify package before and after recovery. Independent capture points remain explicitly non-atomic; CI pending.

## 0.8.25-dev
- Add explicit writable Kopia working-copy opt-in before offline activation, with guarded replacement validation and native reconnect/rollback.
- Permit reviewed managed offline backup jobs only with mapped images, opt-in and confirmed native writable repository. Extend guided CI to new snapshot/restore and source repository hash checks. CI pending.

## 0.8.24-dev
- Add independent guided native recovery CI fixture: actual managed core, worker and Kiwix snapshots, generated inventory, replacement restore, read-only Kopia reconnect, native login and catalog comparison, offline activation and no-pull lifecycle, source repository digest comparison.
- Reuse exact locally built/pulled images in the fixture; native archive import is exercised separately. Full disconnected and writable backup acceptance remain outstanding. CI pending.

## 0.8.23-dev
- Add guided replacement recovery command, exact native core/worker restore, independent read-only Kopia working copy, selected application startup and explicit restricted offline lifecycle activation.
- Correct native Kiwix recovery fixture after earlier intentional purge. Keep MicroTAK clean-stop blocker and full disconnected acceptance explicit. CI pending.

## 0.8.22-dev
- Prepare exact offline worker image policy from selected started module receipts. Add worker-side fail-closed local image mapping, credential and no-build/no-pull checks, restrict lifecycle operations and registry access in future offline mode.
- Do not activate offline mode or lift core-only guard yet. CI pending.

## 0.8.21-dev
- Start restored modules explicitly using exact local images and restoration receipts while core-only recovery protection remains active. Validate mounts, loopback ports, credentials and readiness.
- Add native read-only Kiwix restore fixture; continue unrelated integration checks after only the known MicroTAK backup refusal with confirmed restart. Keep TAK missing in recovery inventory. CI pending.

## 0.8.20-dev
- Restore exact verified application and offline-content snapshots into a staged replacement root using a network-isolated native Kopia helper and read-only repository.
- Preserve native ownership, refuse non-placeholder destinations and unsafe restored file types, record per-module restoration receipts. CI pending; optional startup not included.

## 0.8.19-dev
- Add independent disposable recovered-core startup acceptance before application smoke, with original login, household, session exclusion, exact worker credentials/sharing, and no-pull startup checks.
- Guard core-only recovery against portal and worker mutation requests; require compatible captured core image labels before starting. Fix stale portal version string. CI pending.

## 0.8.18-dev
- Add host-only replacement core and worker staging, validated private files, ownership, preserved original environment, and explicit no-pull/no-build core-only start.
- Add bounded shutdown refusal diagnostics; retain MicroTAK strict consistency gate. Routing native verification passed prior Core checks milestone; latest CI pending.

## 0.8.17-dev
- Add explicit image import on an empty matching replacement daemon, exact image-ID checks, recovery-only tags and no-pull Compose override generation.
- Correct native content read verification to account for Kopia's distinct-object tree traversal rather than requiring one read per path. Preserve zero-error and manifest count checks.
- Full integration remains blocked by MicroTAK clean shutdown and pending CI. No live startup or restore application.

## 0.8.16-dev
- Add host-only offline installation asset capture and verification: reviewed release files, raw private environment, exact local image IDs, native Docker archive and SHA-256 manifest.
- Add unit tests and native disposable Docker archive save/load fixture. No live recovery application or image import command yet. CI pending.

## 0.8.15-dev
- Add stable download and regional metadata to core exports, guarded against active operations; invalidate stale estimates in the copy.
- Verify metadata on isolated restoration, reconstruct it in offline preparation and record its inclusion in recovery inventory. Legacy exports remain supported. CI pending.

## 0.8.14-dev
- Add native recovery inventory generation and administrator-only JSON download, with exact snapshot IDs, original job evidence, native manifest presence, file counts and sizes, and worker envelope digest.
- Explicitly distinguish independent capture points, missing sources and read verification from a complete recovery package. CI pending.

## 0.8.13-dev
- Add managed native snapshots and full-file read verification for Kiwix, maps, routing and Jellyfin media without a second content copy.
- Guard portal content admission during snapshots; refuse queued/active download operations and require external writers to be stopped.
- Add API, worker, maintenance guard and disposable native fixture coverage. CI pending; large content restoration is not yet automated.

## 0.8.12-dev
- Expand managed snapshots and isolated data checks to MeshMonitor, MicroTAK, Kolibri and Jellyfin configuration; preserve native CA and node identity fixture comparisons.
- Keep Kopia online through disposable smoke acceptance to avoid redundant registry pulls; retain final uninstall and persistence checks.
- Core restore CI passed; worker snapshot milestone passed before registry throttling. Expanded CI pending.

## 0.8.11-dev
- Add standalone offline recovery preparation tool for restored core and worker exports; reconstruct private databases and generated secret files into a new directory without touching Docker or live data.
- Add refusal and recovery fixture tests and explicit clean-machine recovery prerequisites. CI pending.

## 0.8.10-dev
- Verify isolated worker-state restores against an exact captured envelope digest, job markers, SQLite integrity and reviewed secret sets; reject queued/running jobs in the copy.
- Add admin-only control and disposable original-secret comparison without exposing values. CI pending; no live recovery application.

## 0.8.9-dev
- Add private worker database and reviewed generated-secret export into native encrypted Kopia snapshots, without mounting worker state into Kopia.
- Mark unfinished jobs interrupted in the exported copy, bound size and time, transfer via stdin and clean owned staging.
- Add admin confirmation, unit/API tests and disposable snapshot test. Worker restore verification and full recovery remain pending.

## 0.8.8-dev
- Add isolated restoration and verification of the latest successful core database snapshot, including exact export job marker, integrity, schema, administrator and absent session records.
- Confirm prior Homebox/DokuWiki backup and core export CI passed. Add native disposable core restoration test; new CI pending.

## 0.8.7-dev
- Add administrator-confirmed private online core SQLite export with integrity and schema checks, session removal from copy only, and native Kopia snapshot.
- Bound export size/time and clean owned staging after normal execution or ordinary snapshot failure. Do not overwrite interrupted staging.
- Add unit/API and disposable snapshot tests. CI pending; core restore verification and worker secrets remain outstanding.

## 0.8.6-dev
- Expand the validated Grocy maintenance-stop snapshot pattern to Homebox and DokuWiki.
- Verify isolated Homebox SQLite integrity/schema and DokuWiki configuration, ACL/account files and page presence; compare restored private wiki fixture in disposable CI.
- Keep worker-secret recovery separate and automatic updates disabled. Expanded CI pending.

## 0.8.5.1-dev
- Request native Kopia verbose snapshot JSON so required statistics are available, and share strict validation between creation and restore lookup.
- Distinguish missing statistics, command errors, invalid JSON and nonzero error/exclusion counters without exposing native output.
- Add regression tests for verbose flag and missing counters; preserve complete integration test. CI pending.

## 0.8.5-dev
- Add isolated latest managed Grocy snapshot restoration and SQLite integrity/schema checks, fixed private destinations and bounded native commands.
- Replace Kopia host marker assertion with native restart/reconnection and extend disposable smoke test to restoration. Prior repository creation reached connected state; smoke stopped at marker assertion.
- No live data replacement or automatic updates. CI pending.

## 0.8.4-dev
- Add initial administrator-confirmed Grocy snapshot workflow with clean stop, native Kopia CLI, bounded runtime, manifest completeness checks and prior-state restart on ordinary failures.
- Record native snapshot ID without claiming restore verification; reject unsupported apps and partial/excluded snapshots.
- Add unit/API and disposable integration tests. CI pending; previous repository setup unit/build passed but hosted browser dependency install failed before smoke, rerun requested.

## 0.8.3-dev
- Add native authenticated Kopia repository connection status and explicit empty local repository initialization through the existing job queue.
- Refuse connected/initializing servers and nonempty or unreadable destinations; preserve native existing-repository connection workflow.
- Add authorization, empty-destination and disposable native repository smoke tests; CI pending. No verified snapshots yet.

## 0.8.2-dev
- Add administrator-only backup source plans for core and reviewed application mounts, using native Kopia paths and application consistency guidance.
- Exclude Kopia self-backup and regenerable media cache; identify missing worker secrets/state, host configuration and images.
- No new backup engine, host mounts, automatic snapshots or claims of verified recovery. Add unit/API and Compose smoke coverage; CI pending.

## 0.8.1-dev
- Add explicit administrator-only online registry metadata checks through native Docker Buildx, using reviewed image references and platform-aware config digest comparison.
- No layer downloads, automatic checks, new tag selection or claims of latest upstream release. Unknown registry/platform states are explicit.
- Add registry parsing, authorization, offline failure and disposable live metadata smoke tests; CI pending.

## 0.8.0-dev
- Add administrator-only reviewed image reference, installed image IDs, local target comparison and recent update history via fixed Docker reads.
- Require explicit backup acknowledgment for manual updates at API and worker boundaries; running supported modules only, routing upgrade deferred.
- No registry freshness claim or automatic updates. Add unit/API tests and a local Docker smoke assertion; CI pending.

## 0.7.4-dev
- Add shared LAN preparedness overview with local content indicators, native application shortcuts and explicit unknown states; no readiness score or new services.
- Add administrator topic presets for the existing Kiwix catalog search; no automatic downloads or claimed curated archive verification.
- Add guest access, privacy, failure isolation and disconnected-browser coverage; CI pending.
- Prior DokuWiki and consolidated inventory CI passed. Physical and native authenticated inventory acceptance remain pending.

## 0.7.3-dev
- Add administrator-only consolidated live inventory across mapped Homebox/Grocy locations, with ownership/storage filters and shared/unassigned selection.
- Bounded eight-location pages, reused native metadata, explicit partial failures, preserved units and no inventory database duplication.
- Add mocked integration, filter, authorization and pagination tests. Native authenticated acceptance and CI pending.

## 0.7.2-dev
- Add optional DokuWiki 2026-07-14c for local notes, revision history and emergency document attachments, with native ACL setup and persistent storage.
- Add disposable native setup, page editing, guest access denial, LAN sharing and lifecycle tests; CI pending.
- Jellyfin native setup, authentication, read-only media and lifecycle CI passed. Physical playback and disconnected acceptance remain outstanding.

## 0.7.1-dev
- Optional Jellyfin 12.4 media library with native local setup, accounts and LAN sharing; original videos/audio mounted read-only, persistent configuration/cache.
- Native setup, library, authentication, mount and lifecycle smoke tests added. Playback and disconnected media acceptance pending.
- Prior corrective communications and Kolibri CI completed successfully, including native enrollment and provisioning.


## 0.7.0-dev
- Fix communications startup regression caused by referencing a request model before declaration (preceding corrective commit).
- Add official Kolibri 0.19.5 optional education module with native facility setup, persistent data, dual-port LAN sharing and native content management; lifecycle smoke tests added.
- Document native mesh/TAK interoperability candidates without enabling an unauthenticated CoT feed or automatic bridging. Hardware and native communication validation remain pending.


## 0.6.2-dev
- Local communications readiness page with service status, shared PACE plan CRUD, device directory and administrator-confirmed manual checks. No live radio status or credentials.
- Fix native MeshMonitor login smoke test to acquire the upstream CSRF token without bypassing protection.
- Prior CI reached successful repeated routing updates and Chromium offline-browser acceptance, then failed at MeshMonitor login. New communications tests pending.


## 0.6.1-dev
- Add optional MicroTAK native TLS server, locked enrollment, private initial bindings and explicit trusted LAN sharing. Disable unencrypted CoT and native automatic backups; keep native data and CA in private persistent directories.
- Portal displays native client endpoints rather than a nonexistent web interface. Native admin CLI for bootstrap; no token reveal through portal.
- Add disposable native CA/enrollment/TLS and lifecycle smoke coverage; client compatibility and CI pending.


## 0.6.0-dev
- Add optional native MeshMonitor module for Meshtastic and MeshCore, generated initial credentials, disabled anonymous access, explicit LAN sharing and preserved native data.
- No automatic source or hardware connection; native messaging/monitoring acceptance pending.
- Pin CI to Ubuntu 24.04 for the existing Playwright runtime; bounded retry for known transient registry throttling in disposable install tests. Previous place/search CI passed; repeated graph update and browser test results still pending.


### Browser acceptance follow-up
- Add pinned Playwright Chromium test in disposable CI with off-server browser HTTP(S) requests blocked and recorded. Exercise real raster map rendering, region presets, route overlay, search, saved plans and guest access.
- Keep route/waypoint rendering enabled after the map's initial load even while subsequent tiles load. New browser CI pending.


## 0.5.10-dev
- Alternate the two fixed routing graph/source slots across repeatable updates, with explicit inactive-slot archiving and no deletion.
- Refuse occupied graph/source slots and selected-graph retirement; retained archive status and incomplete archive visibility.
- Extend real Compose tests to archive, refill, rebuild and switch a second time. New CI pending.


## 0.5.9-dev
- Local named-node and tagged-address search using native Osmium extraction and SQLite FTS5, no geocoding server or runtime internet dependency.
- Explicit admin index build, bounded native extraction, selected-source identity checks and independent retained indexes. Search results can populate routing endpoints.
- Request up to two native Valhalla alternatives and choose the displayed/saved route; none may be returned. Tests for source changes, API access and native fixture search added.


## 0.5.8-dev
- Prepare a second Valhalla graph from incoming.osm.pbf without changing the original graph; check minimum disk headroom and bound native build time.
- Administrator graph activation and rollback through fixed Compose jobs and an atomic selected-slot marker; readiness failure triggers an attempted restoration of the previous slot.
- Retain both graph/source slots; status distinguishes selected-on-disk from actual app availability. No automatic slot retirement or deletion.
- Extend native lifecycle smoke test for preparation, activation, rollback and routes, plus worker failure-recovery unit test. CI pending.


## 0.5.7-dev
- Regional Geofabrik PBF acquisition with metadata estimate, explicit confirmation, actual byte progress, storage checks and publisher MD5 verification.
- New source published atomically; existing region and graph retained; replacement staged separately as incoming.osm.pbf. No automatic rebuild or activation.
- Correct routing lifecycle smoke test to use administrator status rather than inaccessible graph directory. Previous smoke reached all three native route modes and uninstall successfully.
- Add staging, checksum and API tests. Live Geofabrik transfer and update activation pending.


## 0.5.6-dev
- Administrator-only GPX/KML import of local waypoints, routes and tracks, with separate track segments preserved.
- UTF-8, 1 MB limit, bounded records/coordinates, no XML entities or external KML links. Atomic SQLite insert; imported geometry is static and shared on LAN.
- Add parser, API and atomic rejection tests; browser and native graph integration validation pending.


## 0.5.5-dev
- Shared local waypoints and saved route snapshots with admin-only writes, persistent SQLite and LAN viewing.
- Use waypoint as start/destination, display map markers and saved geometry, export waypoint collections or individual routes to GPX/KML.
- Add access, coordinate, persistence and XML escaping tests. Imports, native graph runtime, address search and browser acceptance pending.


## 0.5.4-dev
- Optional Valhalla module with native regional graph preparation and preserved routing tiles; no directly exposed backend port.
- Local same-origin route planning for driving, walking and cycling, coordinate selection, route overlay and directions.
- Add response bounds, polyline decoding, access tests and native graph/mode smoke tests. Results pending.


## 0.5.3-dev
- Fix styled map asset build by bundling pinned upstream license notices rather than assuming npm packages include their source licenses.
- Add offline geographic overview, drag selection, numeric fields and initial regional presets using pinned Natural Earth land data.
- Test asset availability and JS syntax; browser interaction and real regional extraction remain unverified. Prior regional extract CI passed.


## 0.5.2-dev
- LAN styled offline map viewer with bundled MapLibre, PMTiles and Protomaps basemap assets; no CDN runtime requests.
- Read-only range serving of the existing PMTiles slot; no duplicate archive, no Docker access. Map-only CSP allows local workers and styling.
- Map controls, scale and click coordinates; compatible Protomaps MVT and raster PMTiles. Other formats remain in native tile viewer.
- Add range, asset, setup and symlink tests; actual browser acceptance and routing pending.


## 0.5.1-dev
- Regional PMTiles estimates and downloads using the pinned, SHA-256-checked upstream CLI; administrator confirmation, bounded region, storage checks and native structural verification.
- Show actual tool output and archive sizes; never overwrite the existing PMTiles slot. Interrupted jobs require a fresh estimate. No automatic WAN requests.
- Add API and publishing tests and native CLI verification of the existing map fixture. Prior map lifecycle CI passed; actual upstream extraction remains pending.


## 0.5.0-dev
- Optional LAN-accessible TileServer GL Light module with local PMTiles/MBTiles sources and native previews.
- Explicit configuration skips missing archives; no default map downloads. Map data mounted read-only and retained on uninstall.
- Add real upstream-pinned raster PMTiles fixture and lifecycle smoke coverage. Results pending; vector cartographic styling and routing are not implemented.
- Prior household and inventory logic CI passed; authenticated native inventory runtime validation remains pending.


## 0.4.1-dev
- Connect native Homebox and Grocy API keys, discover locations and populate household mappings.
- On-demand administrator-only Homebox item-record counts and Grocy stock totals by product and native stock unit at mapped locations.
- Fixed internal URLs, GET-only native requests, bounded responses, no arbitrary browser URLs and no key readback. Native credentials remain sensitive local SQLite data.
- Unit and access tests added; native service API response and live reporting acceptance pending.


## 0.4.0-dev
- Shared household directory and filter; administrator-only editing and deleting.
- Manual Homebox/Grocy native location references with independent owning and storage households; shared/unassigned supported.
- SQLite foreign keys protect referenced households. Native inventories and QR labels remain unchanged.
- Add persistence, duplicate, reference and authorization tests. Live inventory API discovery and stock reporting are next; no counts invented.
- Correct archive lifecycle smoke test to inspect removed files using the administrator API rather than inaccessible host directory.


## 0.3.6-dev
- Local ZIM indexing, recoverable removal, restoration and explicit purge; safe filenames and serialized native library mutations.
- Display indexed and removed archives, with disk usage and administrator-only origin-checked actions.
- Add local action tests and a real upstream-pinned ZIM fixture to the Docker smoke test for native indexing and reader catalog reload. New test results pending.
- Prior LAN-first and content download logic CI passed; actual upstream download remains unverified.


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
