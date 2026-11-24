# Recovery preparation (development)

The initial installation may be online. Complete offline reinstallation is not yet supported. Keep the exact release, repository copy and recovery password separately from the server.

This workflow prepares core and worker files on a replacement Linux machine using Python 3 and the matching reviewed AfterGrid checkout. It does not install, start or modify Docker, overwrite existing data, or restore applications. Keep the machine offline if desired; no network is used by the tool.

## Prerequisites

- A readable, independently stored native Kopia repository, with its password retained separately.
- A successful core export snapshot and successful worker export snapshot with the recorded full envelope SHA-256. Record both source job IDs, native snapshot IDs, worker envelope digest and AfterGrid release in your recovery records off-server. Older worker snapshots without a digest must be recaptured.
- Restore each exact native snapshot into a separate private directory using native Kopia. The core directory contains core.sqlite3 and job-id; the worker directory contains worker-recovery.json and job-id. Do not restore over an existing installation. If the original portal is available, its isolated verification jobs produce these directories.
- Use an owner-only parent directory on a trusted Linux filesystem. Do not place the restored inputs or prepared output on a public share.

From the matching checkout, run with your actual paths, job IDs and recorded digest:

```sh
python3 recovery_prepare.py \
  --core-dir /secure/recovered/core/data \
  --worker-dir /secure/recovered/worker/data \
  --core-job 101 --worker-job 102 \
  --worker-sha256 YOUR_RECORDED_64_HEX_DIGEST \
  --destination /secure/aftergrid-prepared
```

The destination must not already exist. It will contain core/core.sqlite3, worker-state/jobs.sqlite3, worker-state/secrets/*.json and recovery-metadata.json. Files are mode 0600 and directories 0700; ownership belongs to the account running the tool. Verify expected application selection, matching release and host configuration separately. The core database contains no live sessions, and the worker database contains no queued or running jobs. Recovered secrets are not regenerated.

All prepared data and native restores contain sensitive plaintext. Keep access restricted, and remove unneeded copies after review.

## Not yet automated or accepted

- Apply the prepared files to a new AfterGrid installation or worker volume with appropriate ownership.
- Coordinate core and worker capture points; these exports may be from different times.
- Capture missing core download state, application data, host configuration, exact release and Docker images.
- Reconnect the native repository on a replacement machine, restore all application data, start services and validate login, native authentication, LAN sharing, offline content and data integrity.
- Perform complete recovery while disconnected, including Docker image import and installer acceptance.

Do not use this tool as evidence that the entire server can be rebuilt. It validates and reconstructs only the primary core and worker exports into an isolated staging directory.

## Recovery inventory

Generate and download the administrator recovery inventory after all intended snapshots and verification jobs finish. It lists the exact snapshot IDs, source jobs and worker envelope digest for the preparation command above, plus explicit missing sources. Preserve it off-server together with the repository password and independent repository copy. Do not infer that an uninstalled or missing source is safe to omit without reviewing the original application selection. The report does not pin snapshots or establish a coordinated system capture.

New core exports also contain content-metadata.json. Preparation validates and reconstructs downloads.sqlite3 and reviewed regional records into the private core staging tree. Existing estimated downloads are reset to failed in the copy; new estimates are required. Rebuild place indexes after restoring routing content. Legacy core exports may lack metadata; recovery-metadata.json reports its inclusion. Capture points remain independent.


## Offline installation assets (host command)

During an exclusive administration window, with all installs/updates and external Docker changes paused, run from the installed release (Linux, Python 3.11+, local Docker Engine/Compose). Use an existing private destination parent on encrypted/off-server storage. The destination itself must not exist and must be outside the installed root:

```sh
sudo python3 /opt/aftergrid/recovery_assets.py capture \
  --root /opt/aftergrid --destination /secure/aftergrid-assets
sudo python3 /opt/aftergrid/recovery_assets.py verify /secure/aftergrid-assets
```

The export copies reviewed installed release source, module definitions, and raw .env (never evaluated), and uses native docker image save for the exact locally installed image IDs of the core and currently existing reviewed module containers (running or stopped). It records original references and state, platform, and SHA-256/size for each asset. No image pulls, builds, tag changes, or service restarts occur. Uninstalled apps without containers are not included; review the inventory before relying on it. The release copy is the current on-disk reviewed source, not proof of the Git commit or that a manually modified source matches the built images. The archive can be large; check space in advance. Capture is not a coordinated system snapshot and does not include the Kopia repository or data.

The asset tree contains sensitive plaintext host configuration; private permissions are not encryption. Store securely and keep the data repository/password and recovery inventory separately. Verification checks the file set and checksums against the recorded manifest, not authenticity against a malicious replacement. Image restoration into a disposable Docker daemon and a no-pull Compose recovery launcher are next; do not load into a production daemon without reviewing tag conflicts. The target must already have compatible Linux, Python, Docker Engine and Compose; offline installation of Docker itself is not included.


## Import saved images (replacement host only)

The replacement Linux host must already have local Docker and the matching architecture. The daemon must have no containers or images; the command deliberately refuses nonempty daemons because native Docker load can restore tags. Use the trusted matching recovery utility and verified private asset directory:

```sh
sudo python3 recovery_assets.py import-images /secure/aftergrid-assets --confirm-empty-daemon
sudo python3 recovery_assets.py prepare-overrides /secure/aftergrid-assets \
  --destination /secure/aftergrid-overrides
```

Import verifies the entire asset file set first, loads images natively, checks the exact set of image IDs and adds deterministic recovery-only tags. Overrides reference those tags with pull_policy: never. Future Compose startup must additionally specify --no-build --pull never; this step does not start any service, alter live data, or reconnect Kopia. Failed imports may leave images on the replacement daemon; inspect manually, never automatically prune. The eventual recovery launcher must reconcile worker-managed module actions and digest-pinned references with recovered images. Use only trusted archives; checksums are integrity evidence, not signatures.


## Stage and start the recovered core (development)

After verifying and importing installation assets, use the original native core/worker restore directories, their job IDs and recorded worker envelope digest. Run the trusted matching recovery_install.py on a replacement Linux host as root. Use a new root outside the asset directory, e.g. /opt/aftergrid, and keep all data private:

```sh
sudo python3 recovery_install.py stage \
  --assets /secure/aftergrid-assets \
  --core-dir /secure/recovered/core/data --worker-dir /secure/recovered/worker/data \
  --core-job 101 --worker-job 102 --worker-sha256 YOUR_64_HEX_DIGEST \
  --destination /opt/aftergrid
sudo python3 recovery_install.py start-core \
  --assets /secure/aftergrid-assets --root /opt/aftergrid --confirm-core-only
```

Staging reconstructs validated databases, reviewed secrets and available metadata, assigns core UID/GID 10001, binds private recovered worker state, and preserves original host settings in recovery-original.env. Initial recovered access is loopback-only on port 8080; use a trusted SSH tunnel. LAN configuration must be reviewed before re-enabling it. Core startup refuses existing containers and AfterGrid networks/volumes, checks exact imported IDs, uses --no-build --pull never, waits for health and checks running IDs. No application data is restored or optional services started. Empty content folders and the initial Kiwix library are placeholders only; do not mistake them for original data. Do not start optional modules from the portal before their data and offline image mappings are restored. A failed start can leave containers; inspect rather than retry blindly. This is a development core-only recovery path; native clean-host startup acceptance is pending, as is recovery package coordination and full application restoration.

Core-only recovery now requires captured core and worker images advertising recovery write-guard support (0.8.19 onward). Both services receive AFTERGRID_RECOVERY_CORE_ONLY=1; login/logout remain available, other portal writes and worker POST/queued execution are disabled. The mode is deliberately not normal operation. A separate disposable hosted CI step exercises actual core export, worker export, asset capture, new root, no-build/no-pull startup, original account and household, session exclusion, and recovered worker secrets/sharing. It uses existing locally built exact IDs to avoid deleting unrelated runner images; native Docker archive import is tested separately. This is not a network-disconnected or full application recovery test. CI pending.


## Restore optional application data before core startup

After importing images and staging the replacement root, but BEFORE starting any containers, run the matching recovery utility once for each captured module:

```sh
sudo python3 recovery_data.py --root /opt/aftergrid \
  --assets /secure/aftergrid-assets --repository /secure/kopia-repository \
  --inventory /secure/recovery-inventory.json --module kiwix --confirm-replacement
```

Supported sources are Grocy, Homebox, MeshMonitor, MicroTAK, Kolibri, notes, Kiwix, maps, routing and Jellyfin (both configuration and media). A verified inventory entry and matching captured image are required; MicroTAK remains blocked until its consistent snapshot passes. The downloaded inventory must match staged core/worker job IDs and worker digest. A locally imported Kopia container runs with no network and read-only repository mount, connects read-only using the recovered password, locates the exact native manifest by ID and source, checks completeness and restores into a new private directory on the replacement filesystem. Restored ownership is retained; symlinks and special files are refused. Only known empty placeholders are replaced. A per-module receipt records snapshot IDs and inventory checksum. Re-run only after inspecting any failed partial restoration. Kopia repository connection and optional app startup are separate. This workflow does not claim atomic multi-source capture or application startup acceptance. CI pending.
