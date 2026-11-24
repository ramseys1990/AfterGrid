# AfterGrid

**Life beyond the grid.**

AfterGrid is an open-source, self-hosted, offline-first preparedness platform for families, homesteads and communities. It manages existing applications using Docker Compose instead of rebuilding them.

## Development status

Early development (0.2.0-dev). The core contains local setup, administrator authentication, a shared dashboard and a private Compose worker. The first Compose worker and Kiwix lifecycle are implemented; real deployment validation is pending. Other catalog entries remain planned. No optional applications are installed by default. Do not expose the development build to the public internet.

## Try the core

On a Debian or Ubuntu Linux machine (bare metal or a suitable Proxmox guest), with curl available:

```sh
curl -fsSL https://raw.githubusercontent.com/ramseys1990/AfterGrid/main/install.sh -o /tmp/aftergrid-install.sh && sudo bash /tmp/aftergrid-install.sh
```

This development installer downloads the source and builds the core locally. It installs Docker Engine and Compose on supported clean hosts when needed; existing Docker installations are not replaced. The default listener is loopback. On a remote machine, use an SSH tunnel (see installer output). To explicitly enable trusted-LAN HTTP access, set AFTERGRID_BIND to a private IPv4 address assigned to the server when invoking the installer. HTTP is not encrypted; use a tunnel or a trusted HTTPS reverse proxy for administrative access.

Follow the browser setup using the one-time token printed by the installer. Docker guest compatibility and end-to-end installation still need real-machine validation.

## Direction

Kiwix for knowledge, Homebox for QR-tagged equipment, Grocy for consumables and recipes, Kopia for backups, regional offline maps and routing, Meshtastic, MeshCore, TAK, education, media, notes, PACE planning and optional local AI.

Households organize shared resources rather than enforce tenant isolation. Administration requires a local login; applications may retain native authentication. No mandatory OIDC, Authentik or cloud accounts.

See [development rules](AGENTS.md), [architecture](docs/ARCHITECTURE.md) and [roadmap](docs/ROADMAP.md).

## First module

Sign in as administrator, choose Kiwix, and inspect installation activity. The worker runs fixed Compose commands and persists jobs. The reader starts with an empty content library; see [Kiwix setup](modules/kiwix/README.md). Refresh applications to see current Docker state. Update currently re-pulls the reviewed image digest; automatic version selection and backups are later milestones.
