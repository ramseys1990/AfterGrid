# Architecture

The core is a management portal, not a replacement for Docker Compose. A minimal FastAPI and SQLite application owns local admin accounts, sessions, module selection and job metadata. Initially use a bundled HTML/CSS/JavaScript UI; evaluate React/TypeScript only when actual UI complexity warrants it. A later isolated management worker runs fixed Compose operations against reviewed manifests. Caddy or an equivalent local reverse proxy is planned for stable module URLs and HTTPS. No Docker socket in the core web container.

## Installation
A single shell command prepares Docker on supported clean Linux hosts, installs only the core, checks readiness, and prints a browser address and setup token. Existing Docker installs are reused; unrelated projects are never modified. The browser will offer module presets, dependency resolution, storage checks, configuration and persistent installation jobs. Show completed stages and actual Docker download progress separately. Closing the browser must not cancel a job. Retry failed modules independently.

## Module contract
Each module normally contains module.yaml, compose.yaml and an icon. Metadata includes id, name, category, upstream, service, interface, dependencies, supported architectures, configuration and readiness. Do not implement a generic plugin runtime. Each Compose project is named aftergrid-<id>. The worker scopes config/pull/up/start/stop/restart/ps/logs/down to those projects. Install and update succeed only when required services are ready. Never use down -v by default.

## Storage and networking
Default /opt/aftergrid installation, separate core data, per-module data, content, and backup destination. Use predictable bind mounts or declared volumes; keep secrets outside version control. Stable local URLs (home.arpa) are planned, with DNS setup and IP fallback. Do not expose admin operations to the public internet. Initial loopback mode is accessible with an SSH tunnel; explicit private LAN HTTP is for trusted networks only, and does not encrypt credentials.

## Authentication and household data
Local administrator login with salted password hashes, expiring opaque sessions, same-origin mutation checks and setup token. No mandatory identity provider. Family profiles are optional labels/preferences, not authenticated identities. Shared resources and household filtering are the default; personal/sensitive apps can use native accounts. Never claim the portal protects an app that is directly accessible.

## Modules
Kiwix, Kolibri, Jellyfin/media, notes, file library; regional MapLibre/PMTiles and Valhalla routing; Meshtastic, MeshCore, TAK, shared MQTT only if required; Homebox equipment and QR labels; Grocy consumables/recipes (Mealie optional later); PACE plans and checklists; Kopia backups; optional Home Assistant, sensors and local AI later. Hardware and native auth requirements are module-specific. Keep software updates separate from content packs, use licensed source material, checksum downloads and show storage estimates.

## Recovery
Kopia is the optional recommended backup module. Use its native scheduling, retention, encryption and restore. Coordinate SQLite/database consistency via native tools or stopped services. Full recovery includes selected images (docker image save/load), Compose files, config, data, content, compatible offline Docker prerequisites and backup tools. Validate an actual clean offline restore. Proxmox backup is optional external protection.

## 0.2 worker implementation

A separate core worker container has root-equivalent local Docker access; the web container has no daemon socket. The worker accepts fixed module/action requests over a group-restricted Unix socket, reads root-controlled module files mounted read-only, and uses SQLite for job status and bounded Docker output. It has no published port. Jobs survive browser closure, and interrupted jobs are marked for inspection rather than silently replayed. This is a privilege separation boundary, not a Docker sandbox. Kiwix is the only reviewed module in this build. The shared application network and fixed port are an initial development choice; port checks, generic dependencies, content management, HTTPS and full recovery are still planned.
