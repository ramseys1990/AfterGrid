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
