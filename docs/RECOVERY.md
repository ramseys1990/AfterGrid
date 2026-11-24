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


## Start a restored optional module

After all selected data has been restored and the guarded core started, explicitly start each desired restored module:

```sh
sudo python3 recovery_data.py --root /opt/aftergrid \
  --assets /secure/aftergrid-assets --inventory /secure/recovery-inventory.json \
  --module kiwix --start --confirm-replacement
```

The host command requires a matching unused restoration receipt and exact imported image, verifies the guarded core containers, preserves existing generated credentials, checks reviewed Compose mounts and loopback-only ports, and starts with --no-build --pull never. It checks the running image ID and existing worker readiness probe, then records readiness in the receipt. This is not full native login/content acceptance. The core-only guard remains active; do not disable it manually. Optional worker lifecycle mapping, Kopia repository reconnection, and reviewed recovery completion still need development. A failed start may leave a replacement container; inspect manually. MicroTAK remains blocked rather than silently skipped in the recovery inventory.

## Prepare offline worker lifecycle policy (not activation)

After optional module startup, `recovery_data.py --root /opt/aftergrid --assets /secure/aftergrid-assets --inventory /secure/recovery-inventory.json --prepare-offline-module kiwix --prepare-offline-module maps --confirm-replacement` stages exact per-module image mappings for the selected started modules. It does not change the core-only guard or restart anything. A future explicit completion command will enable AFTERGRID_RECOVERY_OFFLINE=1 only with the reviewed policy. In that mode the worker admits only start/stop/restart/uninstall/share/unshare of mapped modules, checks imported IDs and existing credentials, and adds no-build/no-pull Compose settings. Registry checks, new installs, updates, routing changes and backup jobs are blocked until separately reviewed. Do not enable the environment flag manually. Kopia reconnection and recovery completion remain outstanding. CI pending.


## Guided replacement recovery (0.8.23 development)

The preferred entry point is now recover.py from a trusted matching release. Use an empty replacement Docker daemon, a new installation root, the independently copied quiescent filesystem Kopia repository, verified assets and downloaded recovery inventory. Select only modules with captured images and verified snapshots. Omitted captured modules are explicitly reported; this is not a complete recovery assertion. The original repository password is prompted without echo.

```sh
sudo python3 recover.py restore --root /opt/aftergrid \
  --assets /secure/aftergrid-assets --repository /secure/kopia-repository \
  --inventory /secure/recovery-inventory.json \
  --module kiwix --module maps --confirm-empty-replacement
```

The command imports images, restores the exact core and worker exports directly through native Kopia, stages the replacement, restores selected app data, creates an independent working repository copy (cp -a --reflink=auto; allow enough disk space), configures native Kopia read-only, starts the guarded core and selected modules, and prepares offline mappings. The input repository is never mounted writable. A failed operation can leave imported images or a partial root; inspect receipts and logs before continuing, do not automatically delete or rerun. Use the lower-level tools for diagnosis. The native copy and reconnection require CI acceptance.

After checking original native accounts, content and repository access, explicitly enable restricted lifecycle mode:

```sh
sudo python3 recover.py activate-offline --root /opt/aftergrid \
  --assets /secure/aftergrid-assets --inventory /secure/recovery-inventory.json \
  --confirm-native-checks
```

This verifies the selected started-module receipts and exact image mappings and recreates only the recovered core and worker without builds or pulls. The portal allows authentication, local route requests, native credential retrieval and mapped lifecycle actions; downloads, external catalog, installs, updates and other configuration writes remain blocked. Kopia is initially connected read-only; normal writable backup scheduling, LAN changes, native full application acceptance, and coordinated capture are separate. This is not an air-gap firewall: third-party applications may attempt network access if the host is online. MicroTAK consistent capture remains blocked (SIGTERM exit 143). Do not claim full recovery until disconnected acceptance is completed.

### Guided recovery acceptance gate

A dedicated disposable CI step now runs before broad lifecycle smoke. It creates real managed core, worker and Kiwix snapshots and inventory, quiesces the original installation, executes guided recovery, checks original login/household and byte-identical ZIM plus live reader catalog, reconnects native Kopia, activates restricted offline administration, exercises Kiwix stop/start, and checks that source repository file hashes are unchanged. The test reuses exact local image IDs rather than emptying the runner daemon; native Docker image archive save/load remains a separate gate. Network connectivity is still available to the runner; this is not disconnected acceptance. CI pending.

### Optional writable backup reconnection

After guided restore and native account/content checks, but **before** activation, an administrator can run `sudo python3 recover.py enable-backups --root /opt/aftergrid --assets /secure/aftergrid-assets --inventory /secure/recovery-inventory.json --confirm-working-copy-writes`. This is a separate explicit choice: the original repository remains untouched, while native Kopia connects its independent copy writable. Existing repository policies may resume native maintenance or scheduling on that copy; inspect policies and retention before opting in. The guarded core remains active. After activation, the worker permits reviewed managed snapshot/verification/inventory jobs only for mapped modules and only when the opt-in marker and native writable status agree. Registry downloads and new installations remain blocked. A failed switch restores the previous config where possible; inspect before retrying. The guided fixture now requires a new core snapshot and isolated restore on the working copy and compares original repository hashes. CI pending.


## Portable recovery package

After generating the latest verified recovery inventory and completing all intended snapshots, enter an exclusive maintenance window. Stop all AfterGrid containers (do not uninstall; retained container IDs identify exact images), pause external repository writers, and keep the repository quiescent throughout the operation. The host command refuses running AfterGrid projects and does not stop services itself:

```sh
sudo python3 recover.py pack --root /opt/aftergrid \
  --inventory /secure/recovery-inventory.json \
  --destination /secure/aftergrid-package \
  --module kiwix --module maps --confirm-quiescent
sudo python3 recover.py verify-package --package /secure/aftergrid-package
```

The new private package contains assets/, inventory.json, repository/, and package.json. It captures exact stopped-container image IDs, copies the repository natively (reflink when available), compares deterministic path/size/content digests of original and copy, checks selected exact native manifests in the copy with an offline read-only helper, and records omitted captured modules. It is an independent snapshot set assembled during a maintenance window, NOT a simultaneous/atomic capture, retention pin, or proof of every application restoration. Native reads may be expensive for large repositories; reserve space and time. The host does not stop or restart services. Store on encrypted/off-host media and keep the password separately.

On an empty replacement daemon:

```sh
sudo python3 recover.py restore-package --root /opt/aftergrid \
  --package /secure/aftergrid-package --confirm-empty-replacement
```

This verifies package files and uses the selected snapshot set recorded in package.json. After native account/content checks, use enable-backups and activate-offline with the package's assets/ and inventory.json if desired. Do not modify the package's repository. The working copy is separate. Checksums do not authenticate a maliciously substituted package. Full disconnected acceptance and MicroTAK consistent backup remain outstanding. CI pending.


## Recovery closeout acceptance (0.8.26 development)

The supported package path deliberately preserves independent source snapshots. The pack command pins the exact inventory bytes it validates, checks source and copied repository digests after native manifest inspection, and refuses replacement roots inside the portable package. These are integrity safeguards, not a lock against external writers or proof of simultaneous capture.

| Gate | Evidence required | Current status |
| --- | --- | --- |
| Guided recovery baseline | Real core/worker/Kiwix snapshots, recovered original login and content, exact local images and read-only Kopia reconnect | Passed in Core checks run 45503443558 |
| Writable working copy | Explicit opt-in, native writable status, fresh managed snapshot and isolated restore, unchanged original repository | New fixture; result must be verified |
| Portable package | Successful pack, checksum verification, actual package restore entry point, tamper refusal, unchanged package after activation and fresh backup | New regression and native fixture coverage; result must be verified |
| Coordinated capture | Defined maintenance boundary covering source changes, all selected snapshot jobs and verification, explicit omissions, final inventory and asset capture | Open; existing snapshots remain independent |
| MicroTAK | Native supported consistent capture and certificate/data verification after restoration | Blocked on clean shutdown (exit 143); do not waive consistency |
| Disconnected replacement | Clean same-architecture Linux host with preinstalled Docker/Compose and Python, WAN absent, actual archive import, restore, native login/content, local lifecycle and fresh backup on working copy | Not accepted |
| Target-host acceptance | Disposable Proxmox guest and/or bare Linux with trusted LAN client; confirm host networking, approved LAN access and recovery from separate media | Not accepted |

### Disconnected replacement drill

Use a disposable host with no production mounts or Docker socket access to other hosts. Prepare its compatible OS, Python and Docker/Compose beforehand; packaging the OS or Docker installer is outside the current scope. Keep a second independent copy of the package and original password. Disconnect WAN at the lab network or virtual NIC boundary while preserving a private test LAN if needed; do not merely block browser requests. Record a failed external connectivity probe and successful local access before and after recovery. Use the trusted matching recovery utilities and a completely empty replacement Docker daemon. Verify the package, perform the actual native archive import via restore-package (no image-reuse shortcut), check original accounts and selected native data, optionally enable backups, activate restricted offline administration, exercise a mapped module restart and verify a fresh snapshot on the independent copy. Verify package checksums again. Review loopback/LAN restrictions rather than exposing old addresses or altering production networking. Record exact versions, selected and omitted applications, observed checks, failures and source/package digests without recording credentials.

Do not mark complete recovery or all-application consistency as passed based on a no-pull Compose run, separate archive fixture, checksum-only verification, or a subset of restored modules. Keep MicroTAK excluded from a supported recovery claim until its separate acceptance gate passes.
