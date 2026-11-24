# Changelog

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
