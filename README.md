# AfterGrid

**Life beyond the grid.**

AfterGrid is an open-source, self-hosted, offline-first preparedness platform for families, homesteads and communities. It manages existing applications using Docker Compose instead of rebuilding them.

## Status

Early development; not production-ready. The first goal is a working core-only installer, local administrator setup and a browser-based module manager. No optional applications are installed by default.

## Planned modules

- Kiwix: offline knowledge and references
- Homebox: durable equipment, storage locations and QR inventory labels
- Grocy: consumables, expiration dates and recipes
- Kopia: scheduled, encrypted backups
- MapLibre/PMTiles and Valhalla: regional offline maps and routing
- Meshtastic, MeshCore, TAK: independent communications modules
- Kolibri, media, notes and PACE planning
- Optional local AI later

Households are organizational groups, not separate tenants. Shared access on a trusted LAN is the default for appropriate resources; administration requires a local login. Native application authentication is acceptable. No mandatory OIDC, Authentik or cloud accounts.

The original ResilienceOS is a separate reference project; AfterGrid starts clean.

See [development rules](AGENTS.md) and [roadmap](docs/ROADMAP.md) as the foundation is added.
