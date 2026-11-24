# Backup coverage and recovery prerequisites

Kopia is the backup engine. The AfterGrid administrator can inspect a read-only source plan for the core and each reviewed application, even before installing Kopia. Module plans derive candidate source paths from normalized Compose bind mounts beneath the configured AfterGrid root. A path mapping is not a check of file existence, filesystem permissions, repository configuration, snapshot consistency or restore success. No credentials or Compose environment variables are returned.

| Component | Native Kopia source | Consistency requirement |
|---|---|---|
| Core | /source/data/core | Quiesce background downloads and core or use validated SQLite export |
| Homebox | /source/data/homebox | Stop app or validated native export; preserve worker pepper |
| Grocy | /source/data/grocy | Stop app |
| Kiwix | /source/content/kiwix | Finish downloads and index changes |
| Maps | /source/content/maps | Finish downloads |
| Routing | /source/content/routing | Finish graph operations and downloads; stop routing |
| MeshMonitor | /source/data/meshmonitor | Stop app; preserve worker secrets |
| MicroTAK | /source/data/tak/data and /source/data/tak/backup | Stop app; preserve CA and credentials |
| Kolibri | /source/data/kolibri | Finish imports and stop app |
| Jellyfin | /source/data/media/config and /source/content/media | Stop app; finish media imports; cache excluded |
| DokuWiki | /source/data/notes | Stop app or prevent all edits |
| Reviewed module definitions | /source/modules | Capture with matching release |

Kopia's repository, restore destination and working folders are excluded from its own source plan. Do not configure recursive snapshots of /source/data. Use individual paths. Repository encryption does not replace off-server storage and secure credential retention. Source plans are lexical classifications, not validation of host symlinks or bind mount contents. Review actual sources in native Kopia.

## Missing recovery coverage

Worker state is a separate Docker volume containing sharing settings, jobs, generated secrets and credentials. The current Kopia source mounts cannot access it. The core release, host .env, exact images and recovery metadata also need an explicit recovery workflow. Do not claim complete backups or enable unattended updates from source plans. Native repository initialization, consistent snapshot execution, snapshot verification, policy scheduling and clean-machine restore remain outstanding.

## Native repository setup

Install Kopia, securely save its generated repository password outside the server, and verify the intended filesystem is mounted at the configured backup destination before creating a new repository. In the portal, Check repository connection reads the authenticated native Kopia UI API. Create empty local repository queues a fixed Kopia-only job that refuses a connected/initializing server and a nonempty or unreadable /repository directory. Native Kopia initializes and connects using its default encryption and the generated password. No raw native responses or passwords are returned or logged. Do not concurrently administer the native UI or change mounts during initialization. If the job fails or times out, inspect the native UI before retrying; creation may already have succeeded. Existing repositories, remote storage and different credentials remain native UI workflows; no automatic reconnection or overwrite is attempted. Status reflects the running native server connection, not a repository integrity test or verified snapshot. No snapshot is started by this feature.
