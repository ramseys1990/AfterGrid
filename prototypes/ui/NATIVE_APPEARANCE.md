# Native application appearance — U5 research baseline

2026-11-28. Research only; no native configuration changed. Image tags below were read from main Compose manifests. Current upstream documentation establishes candidates, not proof of exact pinned-image behavior.

| Native application / pinned image | Supported or candidate mechanism | Recommendation |
|---|---|---|
| MeshMonitor 4.18.0 | Upstream documents admin custom themes, JSON import/export and login logo configuration. [Themes](https://meshmonitor.org/features/custom-themes), [configuration](https://meshmonitor.org/configuration/) | First pilot. Verify exact version, schema, local raster logo support, persistence under /data and rollback. No remote assets. |
| Homebox 0.27.1 | [Upstream releases](https://github.com/sysadminsmedia/homebox/releases) describe theme styling and user preferences; [branding discussion](https://github.com/sysadminsmedia/homebox/issues/228) describes banner preference and proposed logo customization. | Use native profile themes; verify banner and logo capabilities on pinned image. Do not assume custom branding was implemented merely because the issue closed. |
| Grocy v4.7.1-ls352 | [Upstream README](https://github.com/grocy/grocy/blob/master/README.md) documents custom CSS/JS HTML hooks. | Prefer native appearance first. If needed, separately review a fixed, locally bundled CSS-only preset; HTML hooks can execute code and must never consume community packages. Verify LinuxServer /config mapping and exact release. No custom JS. |
| DokuWiki 2026-07-14c | [Upstream template source](https://github.com/dokuwiki/dokuwiki/blob/master/inc/template.php) and [styling plugin listing](https://www.dokuwiki.org/plugins?plugintag=admin) establish template style overrides. | Pilot native styling with default template; verify supported logo media paths and persistence. Keep ACLs and native login. No extra plugins required by default. |
| Jellyfin 12.4 | [Official CSS settings](https://jellyfin.org/docs/general/clients/css-customization/) and [branding guidelines](https://jellyfin.org/docs/general/contributing/branding/) document web customization. | Native themes first; optional reviewed server-side web CSS only, no claim of matching all native clients. Preserve attribution and /config backup. |
| Kiwix 3.8.2 (digest pinned) | [Upstream serve docs](https://github.com/kiwix/kiwix-tools/blob/main/docs/kiwix-serve.rst) document custom welcome page. | Prefer AfterGrid launcher; consider reviewed local welcome page only if exact release supports it. Preserve ZIM content and reader/search behavior. |
| Kolibri 0.19.5 | [Facility settings](https://kolibri.readthedocs.io/en/latest/manage/facility.html) document native facility configuration; general rebranding not established. | Retain native appearance and configure facility name only if appropriate. No fork. |
| Kopia 0.23.1 | No customization contract verified. | Keep native UI; core backup/recovery screens provide consistent experience. |
| TileServer GL Light 5.7.0 / Valhalla 3.9.3 | AfterGrid owns its map viewer; routing engine is not a household portal. | Theme core map chrome only; preserve map cartography, labels, local assets and routing behavior. |

## Small pilot sequence
1. MeshMonitor native theme and logo, exact version and configuration persistence.
2. DokuWiki native styling and local branding, then Homebox native preference guidance.
3. Jellyfin web styling and Grocy native settings; consider fixed CSS only after review.
4. Kiwix optional welcome page; leave Kolibri and Kopia native unless a supported contract is established.

Every pilot requires explicit opt-in, native access preserved, local assets, no proxy HTML rewriting, no arbitrary uploaded CSS/HTML/JS, no container image modification, no mandatory additional service. Verify original settings, change, reload, restart, snapshot/restore, update compatibility, revert and keyboard/readability. Never apply a theme by changing authentication or sharing settings. Portal preference remains separate from native application preference; shared native defaults may affect multiple users. No automatic synchronization promised. U5 research is complete for this initial candidate inventory; native implementation and exact version acceptance remain open. Do not change formal Phase 4 gates.
