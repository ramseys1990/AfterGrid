# Remove and reinstall safely

Removing an optional application and repairing the AfterGrid portal are different operations. Both preserve stored data by default.

## Optional applications: use the dashboard

Sign in as AfterGrid administrator, stop the application, and choose Uninstall in its card. Read the confirmation: application data is retained. Install it again from the same card to reuse that data, then open the native application and check its records. Native accounts remain the application's responsibility.

Do not delete application data directories or Docker volumes to reinstall an application. Permanent deletion is a separate operation, not part of reinstall.

Live acceptance has exercised this removal/reinstall flow independently for Kiwix, Homebox, Grocy and Kopia, including retained content/configuration and subsequent native use.

## Portal and worker: host maintenance

Use this exceptional procedure at the server console when removing/reinstalling the portal and worker. The portal cannot reinstall itself after its own container has been removed. Optional applications continue running at their existing addresses.

Finish all installation, update, download and backup activity first. Keep a verified backup and its credentials off-server. This procedure preserves existing files; it does not recover a failed disk or missing data. Use [portable recovery](RECOVERY.md) for a replacement host.

Use the existing installed source and settings. Do not redownload the initial installer into an existing installation: it deliberately refuses to overwrite it. `--resume` is only for an unfinished initial install.

The following commands apply to a normal installation at `/opt/aftergrid`. Start a root shell with `sudo -i`, then paste the block as one command. It records the exact currently installed images privately, removes only the two core containers, and reinstalls them without pulling images or building source.

```bash
(
set -Eeuo pipefail
umask 077
cd /opt/aftergrid
test -z "${DOCKER_HOST:-}${DOCKER_CONTEXT:-}"
test "$(docker context show)" = default
endpoint=$(docker context inspect default --format '{{.Endpoints.docker.Host}}')
[[ $endpoint == unix:///var/run/docker.sock || $endpoint == unix:///run/docker.sock ]]
test ! -e data/core/recovery-maintenance.json
docker exec aftergrid-core-core-1 python -c 'import os; from pathlib import Path; from worker_client import call; assert not any(os.environ.get(k) == "1" for k in ("AFTERGRID_RECOVERY_CORE_ONLY", "AFTERGRID_RECOVERY_OFFLINE")), "Use the recovery workflow for this installation"; assert not Path("/data/recovery-maintenance.json").exists(); code, rows = call("/jobs"); assert code == 200 and not any(r["state"] in {"queued", "running"} for r in rows), "Wait for current activity to finish"'
core_image=$(docker inspect --format '{{.Image}}' aftergrid-core-core-1)
worker_image=$(docker inspect --format '{{.Image}}' aftergrid-core-worker-1)
[[ $core_image =~ ^sha256:[a-f0-9]{64}$ ]]
[[ $worker_image =~ ^sha256:[a-f0-9]{64}$ ]]
test ! -e .core-reinstall-images.json
test ! -L .core-reinstall-images.json
printf '{"services":{"core":{"image":"%s","pull_policy":"never"},"worker":{"image":"%s","pull_policy":"never"}}}\n' "$core_image" "$worker_image" > .core-reinstall-images.json
compose=(docker compose --project-name aftergrid-core --project-directory /opt/aftergrid --file /opt/aftergrid/compose.yaml --file /opt/aftergrid/.core-reinstall-images.json --env-file /opt/aftergrid/.env)
"${compose[@]}" config -q
"${compose[@]}" stop --timeout 30 core worker
"${compose[@]}" rm --force core worker
"${compose[@]}" up -d --no-deps --no-build --pull never --wait --wait-timeout 120 core worker
)
```

Run this only against the intended AfterGrid host and local Docker context. Leave caller-specific `DOCKER_HOST`, `DOCKER_CONTEXT`, `COMPOSE_*` and `AFTERGRID_*` overrides unset. Do not use this normal-mode block for a recovered installation or an active core-update transaction: retain its original recovery/update overrides and follow that workflow's instructions. Never run a global Compose down or a volume-pruning command as part of this procedure.

Keep `.core-reinstall-images.json` with the unchanged installed source and `.env`. It contains image identities, not a backup. An existing receipt is a reason to inspect the previous operation instead of overwriting it.

If removal completed but startup failed, correct the reported prerequisite and repeat only the startup step from a root shell:

```bash
cd /opt/aftergrid
docker compose --project-name aftergrid-core --project-directory /opt/aftergrid --file /opt/aftergrid/compose.yaml --file /opt/aftergrid/.core-reinstall-images.json --env-file /opt/aftergrid/.env up -d --no-deps --no-build --pull never --wait --wait-timeout 120 core worker
```

Keep the same source, configuration, receipt and local images. If they changed, an image is missing, or startup remains unhealthy, preserve the files and use advanced recovery rather than a fresh install over the data.

## Check the result

Open the original LAN portal URL and sign in if needed. Confirm application status and prior activity are present. Open the native apps and verify their existing records. For diagnostics, check only core/worker with `docker compose --project-name aftergrid-core --file /opt/aftergrid/compose.yaml ps`.

The live CT115 acceptance removed and recreated core/worker from exact image IDs, compared persistent-file hashes after removal, waited for both health checks, and verified unchanged IDs/start times for all four optional applications. Browser administrator session, native inventory and recipes survived. This verifies the operation; it is not a version upgrade or bare-metal installation test.
