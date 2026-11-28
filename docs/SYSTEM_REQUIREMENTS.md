# System sizing and acceptance

Do not present a core-only idle reading as a minimum for all modules. Phase 3 has real evidence of a 2-core, 1 GiB Proxmox guest running the selected recovered deployment with small datasets. The previous 1,030-request read exercise passed; it did not establish capacity for large datasets, routing, media playback or simultaneous backups. Bare-metal acceptance is deferred.

For a disposable or explicitly authorized appliance, use the optional standard-library probe from the source checkout:

```sh
python3 tests/resource_probe.py 192.168.1.4 --rounds 100 --kiwix
```

Replace the example address with the test appliance address; omit --kiwix if not installed. The probe requests only public portal health/page and optional Kiwix root; no credentials, downloads, redirects, writes, extra services or Docker access. It reports success counts, bytes and p95 response latency. The memory readings refer to the machine running the probe; run inside the test guest if collecting its memory. This is a bounded small-page check, not a load-capacity claim.

## Remaining sizing matrix (not yet executed)

| Configuration | Exercise | Evidence |
|---|---|---|
| Core only, 1 GiB / 2 cores | first boot, setup, sustained reads, restart | available memory, swap, CPU, latency, OOM/restarts |
| Core plus Kiwix/Homebox/Grocy/Kopia | representative populated library/inventory; concurrent reading and backup | same metrics plus disk capacity and backup success |
| Maps/routing | declared regional extract size and graph build, route queries during reads | peak RAM/disk, build time, failures, retained data |
| Kolibri/Jellyfin | declared imported lesson/media sizes, interactive activity and direct-play | peak RAM/CPU, storage, playback stalls; transcoding separate |
| All supported selected apps | controlled concurrent read workload and one backup or download | saturation, swap pressure, optional app availability |

Repeat one configuration at a time and record exact release, module versions, CPU architecture, memory/swap, disk and dataset sizes. Compare before/during/after and confirm no unexpected restarts or OOM events. Do not run graph generation, backup, or download load on unrelated workloads. A failed test establishes a limit, not an instruction to increase RAM indiscriminately. Do not publish universal recommendations until representative workloads have been measured.
