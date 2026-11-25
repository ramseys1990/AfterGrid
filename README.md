# AfterGrid

**Life beyond the grid.**

AfterGrid is an open-source, self-hosted, offline-first preparedness platform for families, homesteads and communities. It manages existing applications using Docker Compose instead of rebuilding them.

## Development status

Early development (0.8.26-dev). The core contains local setup, administrator authentication, a shared dashboard and a private Compose worker. The Compose worker and Kiwix lifecycle passed disposable hosted CI. Homebox, Grocy and Kopia have module definitions and initial native setup; their basic lifecycle passed disposable hosted CI. Other catalog entries remain planned. No optional applications are installed by default. Do not expose the development build to the public internet.

## Try the core

On a Debian or Ubuntu Linux machine (bare metal or a suitable Proxmox guest), with curl available:

```sh
curl -fsSL https://raw.githubusercontent.com/ramseys1990/AfterGrid/main/install.sh -o /tmp/aftergrid-install.sh && sudo bash /tmp/aftergrid-install.sh
```

This development installer downloads the source and builds the core locally. It installs Docker Engine and Compose on supported clean hosts when needed; existing Docker installations are not replaced. The installer normally detects a private LAN address; loopback is the fallback or an explicit choice. On a remote machine, use an SSH tunnel (see installer output). To choose a specific trusted-LAN address, set AFTERGRID_BIND to a private IPv4 address assigned to the server when invoking the installer. HTTP is not encrypted; use a tunnel or a trusted HTTPS reverse proxy for administrative access.

To inspect a host before installing, use the same downloaded script with `sudo bash /tmp/aftergrid-install.sh --check`. This read-only preflight checks the supported OS, private bind, portal TCP port, local Docker context and existing AfterGrid resources; it does not install packages, download source, or create containers. Choose a different AFTERGRID_PORT if the selected TCP port is already occupied. The check is conservative and cannot reserve the port or guarantee Docker guest compatibility.

Follow the browser setup using the one-time token printed by the installer. Docker guest compatibility and end-to-end installation still need real-machine validation.

## Direction

Kiwix for knowledge, Homebox for QR-tagged equipment, Grocy for consumables and recipes, Kopia for backups, regional offline maps and routing, Meshtastic, MeshCore, TAK, education, media, notes, PACE planning and optional local AI.

Households organize shared resources rather than enforce tenant isolation. Administration requires a local login; applications may retain native authentication. No mandatory OIDC, Authentik or cloud accounts.

See [development rules](AGENTS.md), [architecture](docs/ARCHITECTURE.md) and [roadmap](docs/ROADMAP.md).

## First module

Sign in as administrator, choose Kiwix, and inspect installation activity. The worker runs fixed Compose commands and persists jobs. The reader starts with an empty content library; see [Kiwix setup](modules/kiwix/README.md). Refresh applications to see current Docker state. Update currently re-pulls the reviewed image digest; automatic version selection and backups are later milestones.

## Essential optional modules

Homebox (8082), Grocy (8083) and Kopia (51515) use native authentication and initially bind loopback only. Use SSH forwarding for remote setup; stable LAN access is a later milestone. See their module READMEs. Kopia uses its native repository and snapshot UI; no backup is scheduled merely by installing it. Image tags for these three services are version-pinned, not digest-pinned.
After creating the administrator, choose optional apps in the first-run browser wizard or skip to keep the core only. Nothing is preselected. The selected applications are queued atomically and run one at a time using Compose, with real job output. A repeated submission of the same selection returns the original jobs.

For optional inventory sharing on a trusted network, see [LAN access and stable QR URLs](docs/LAN_ACCESS.md). Homebox and Grocy are local-only until explicitly shared; Kopia can also be explicitly shared using native administrator credentials.

The normal deployment is LAN-first. No local DNS is required for IP-based access. Set AFTERGRID_LAN_DOMAIN at install if you want stable separate hostnames for the portal and shared apps. See the LAN guide for HTTP risks and first-time native account setup.

The administrator content panel now shows local ZIM files and disk space and searches the upstream Kiwix OPDS catalog on demand. Catalog queries are on demand. The download queue runs only after an administrator requests an archive.

Content downloads now use a persistent unprivileged queue and native curl, official Metalink SHA-256 metadata and kiwix-manage indexing. Existing development installations must make content/kiwix writable by UID 10001 (sudo chown -R 10001:10001 /opt/aftergrid/content/kiwix) before enabling downloads. New installs handle this automatically. Catalog entries without a supported official download path or SHA-256 metadata are not supported. Actual upstream download and reader reload validation remain pending. Delete corrupt .part files manually after confirming no job is running; local imports and recoverable removal are available.

Local archive management: copy trusted ZIMs to content/kiwix (USB or LAN transfer outside the portal), refresh local archives, then Add to library. Remove unindexes and retains a copy under .removed; Restore reindexes, and Delete permanently reclaims storage. Local actions are blocked while a download runs. Native tool and reader reload smoke tests use a pinned OpenZIM fixture; live upstream download and physical offline LAN testing remain separate.

## Households

The shared LAN directory supports household names and manual native Homebox/Grocy location references, with separate ownership and storage households. Only the local administrator edits the directory. No personal accounts or duplicate inventory databases. Counts describe mapped locations, not stock quantities. The administrator can connect native API keys, discover locations and request live location reports. Family-wide live reporting is not yet enabled. Do not put sensitive details in the shared labels.

## Offline maps

Install the optional [Maps module](modules/maps/README.md) for local PMTiles/MBTiles serving and native browser previews over the LAN (port 8084). Map content is separate: copy a trusted regional archive into the map content directory and restart. No automatic demo download. Styled vector basemaps, regional downloads, waypoints and routing are later slices. New Docker smoke tests are pending.

Regional map extracts: select a published Protomaps build date, bounding box and maximum zoom, run an estimate and explicitly confirm the download. Native pmtiles CLI performs range extraction and structural verification. Existing PMTiles never overwritten. Development limit 4 GiB per extract; logs show actual tool output, not file-size progress (the CLI preallocates). Existing installations must give UID 10001 ownership of content/maps directory before downloading. Live upstream extraction and styled vector rendering remain unverified.

Styled offline map: open the Maps card's styled viewer. It uses local MapLibre, PMTiles and Protomaps styles, fonts and sprites, served by the core. Compatible Protomaps MVT and raster PMTiles supported; other vector schemas and MBTiles retain the native viewer. No browser CDN dependency. Local range serving and packaged assets are covered by tests; actual browser/WebGL and vector label rendering still need acceptance.

Regional selection now includes a bundled Natural Earth overview, drag-to-select bounding boxes, geographic extent choices and approximate SC/NC/GA/Southeast presets. The existing numeric bounds remain editable and the same server validation/estimate/confirmation flow applies. No internet request is required for selection itself. This is an overview, not a navigation map or exact jurisdiction boundary.

Optional [offline routing](modules/routing/README.md) uses native Valhalla graph building and route planning through the LAN portal. Supply a regional OSM PBF first. Existing graphs are retained. No internet fallback, native data downloads or automatic graph rebuild yet.

The map planner also supports shared emergency waypoints, using saved points as route endpoints, static saved route geometry and GPX/KML export. The administrator edits; all LAN users can view and export. Keep sensitive locations out of the shared directory. Saved geometry is not a live route or evidence of current access. Bounded local GPX/KML import is implemented; geocoding remains planned; regional PBF download is now available.

Regional routing downloads: choose an initial supported Geofabrik region, estimate the published PBF size and explicitly confirm. curl transfers the file, matching publisher MD5 checks integrity, and AfterGrid stages it without overwriting an existing source or graph. 2 GiB PBF development cap; graph construction requires additional resources. Existing installations need content/routing owned by UID 10001. Replacement graph preparation, activation and rollback UI implemented; live Geofabrik transfer and replacement acceptance not yet tested.

Offline point search uses native Osmium and SQLite FTS5, with an explicit administrator build from the selected local PBF. Includes named nodes and nodes with street/house-number tags; not full address geocoding, polygon POIs, interpolation or street lookup. Indexes are separate by graph slot and checked against source file metadata. Native Valhalla alternatives (up to two requested) can be selected, viewed and saved; alternatives are not guaranteed. New native smoke coverage pending.

Repeatable routing updates alternate the two graph slots. Archive the inactive slot through the portal to retain both its source and graph, then acquire another source and build the newly vacant slot. Archiving does not free disk space; no automatic deletion. The current graph stays selected during preparation. New lifecycle coverage pending.

Browser acceptance uses a fresh Chromium context, blocks all off-server browser HTTP(S) requests and checks local raster PMTiles range loading, region presets, route overlay, place search, saved route/waypoint persistence and guest access. This is not a physical LAN WAN-disconnection test or proof of server egress isolation; styled vector label rendering is a separate gate. CI results pending.

Optional [MeshMonitor](modules/meshmonitor/README.md) provides one native local interface for Meshtastic and MeshCore. Generated initial login, explicit LAN sharing, persistent native data; no automatic radio connection, broker or USB bridge. Native radio and disconnected acceptance pending.

Optional [MicroTAK](modules/tak/README.md) provides a lightweight native TLS TAK backend with locked certificate enrollment, local CA, explicit LAN sharing and retained data. Native admin CLI and compatible TAK clients required; no web dashboard or automatic device enrollment. Existing development installations must prepare private TAK directories. CI and client acceptance pending.

The core communications page lists native service status, shared PACE plans and manually recorded device readiness. Administrators edit; LAN guests view. No credential storage, radio commands or claims of live device connectivity. Planning remains available with both optional communications services stopped.

Optional [Kolibri](modules/kolibri/README.md) uses the official image for native offline education. Complete facility setup, select content channels and share both native ports on trusted LAN. No automatic content download or separate identity system. [Mesh/TAK interoperability review](docs/COMMUNICATIONS-INTEROP.md) documents native options and security boundaries without enabling an unauthenticated feed.

Optional [Jellyfin media library](modules/media/README.md) uses the official native image, local accounts and read-only original media under content/media. Complete native setup and explicitly enable LAN sharing. No automatic media downloads or GPU passthrough. Existing development installations need module directories prepared. Actual playback and offline acceptance remain unverified.

Optional [DokuWiki](modules/notes/README.md) supplies shared notes, emergency instructions and document attachments with local accounts, ACLs and a persistent file-based store. Complete native private setup on port 8097, then explicitly share on LAN. No additional database. Native CI pending.

The administrator consolidated inventory overview reads mapped Homebox and Grocy locations together, with separate ownership and storage filters, native units and explicit unavailable states. It does not duplicate stock records or expose inventory keys to LAN guests.

The shared preparedness overview brings local resource indicators and native application links together without exposing private stock or credentials. Suggested content packs populate the administrator's existing Kiwix catalog search; downloads remain individually reviewed and confirmed. Presence indicators are not proof of readiness.

[Application version visibility and manual updates](docs/UPDATES.md): compare reviewed image references with local Docker image IDs and see update history. Manual updates require backup acknowledgment; no unattended upgrades or registry freshness claims.

Optional online registry checks compare the exact reviewed image reference with the installed image, without downloading layers or selecting new release tags. See the update guide.

[Backup coverage](docs/BACKUPS.md): administrator source plans derived from reviewed Compose mounts, consistency guidance and explicit recovery gaps. Kopia remains responsible for actual snapshots and retention.

Kopia repository setup supports explicit creation at the configured empty local destination and native connection status. Existing repository connection remains in Kopia; no snapshots or restore verification are implied.

Initial managed Grocy snapshots use a clean maintenance stop and native Kopia, restoring previous running state on ordinary failure. Restore verification and other application coverage remain pending.

Grocy restore verification uses a fresh isolated destination and SQLite integrity checks; production data is never replaced. Native application startup and clean-machine recovery remain unverified.

Managed backup coverage expands to Homebox and DokuWiki with application-specific isolated restore checks; worker-generated secrets still require separate recovery.

Core database backups use SQLite online export and native Kopia snapshots, excluding active login sessions from the copy. Full core and worker recovery are not yet complete.

Core database isolated restore verification checks exact export job, SQLite integrity, administrator presence and absence of active sessions. Full clean-machine recovery remains outstanding.

Managed worker-state snapshots preserve existing reviewed generated credentials and worker database settings; isolated verification and clean-machine recovery remain pending.

See [recovery preparation](docs/RECOVERY.md) for the standalone offline tool that validates and reconstructs private core/worker recovery staging. It does not apply data to a live installation.

Additional managed backup sources: MeshMonitor, MicroTAK, Kolibri and Jellyfin configuration. Native data-specific isolated verification is under CI validation; large content and media are separate recovery work.

Offline content snapshots use native Kopia deduplication and full-file read verification without creating a second on-disk content collection. Full recovery remains pending.

Download an administrator recovery inventory listing exact snapshot IDs, recorded verification and repository presence; this is not a complete recovery package.

Core recovery exports now include stable content download metadata and regional job records, excluding rebuildable place indexes.

The [offline installation asset capture](docs/RECOVERY.md) host command saves reviewed release files, private environment settings and exact existing Docker images, with a checksum inventory. Full offline reinstallation remains pending.

The host-only recovery_install.py utility stages validated core and worker exports into a new root and provides an explicit core-only no-pull Compose startup. Optional data restoration and full disconnected acceptance remain outstanding.

Native replacement application data restoration uses recovery_data.py with a copied read-only filesystem repository and exact verified snapshot IDs. Startup is separate.

A guided replacement recovery entry point (`recover.py restore`) coordinates native Docker image import, exact snapshot restoration, read-only Kopia reconnection and guarded startup. Explicit restricted offline activation follows native checks; full recovery acceptance remains pending.

Initial source installation is staged before publishing `/opt/aftergrid`, with a host installer lock to prevent overlapping installation attempts. If Docker startup fails after publication, retain the existing directory and setup token; do not delete data or rerun a fresh install. Once the staged directory has been published, correct the startup problem and run `sudo bash /opt/aftergrid/install.sh --resume`. Resume only accepts an unfinished initial install with unchanged configuration and the existing setup token. It does not download source, reset credentials or delete data. After a successful start, use normal Compose management instead.

Optional application installs now check normalized Compose host port publications against existing running Docker workloads before pulling images. A conflict is shown in installation activity; other services are not stopped or changed. Correct the conflict and retry the individual app. This conservative check does not detect every native host listener or reserve a port; Docker still validates actual binding. Custom application port selection remains a future option.
