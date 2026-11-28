# AfterGrid community marketplace — post-1.0 roadmap

Status: approved direction, future implementation. No repository, catalog service or distribution infrastructure has been created by this plan. UI/theme groundwork is in [Phase 4](UI_OVERHAUL.md). Release labels below are provisional sequencing, not dates or promises. Keep core fully usable without marketplace access; no new daemon, identity provider, paid service or runtime framework by default.

## Goals and scope

A curated app-store-like catalog of optional modules, content packs and themes, with plain-language description, category, publisher, screenshots, version, license, compatibility, size, dependencies, permissions, storage estimates, installed state and available updates. Admins approve downloads, installation, updates, removal and sensitive permissions; household visitors may select installed themes locally. No marketplace account to browse/download; contributors use GitHub pull requests. Never require marketplace to boot, use local tools or recover. Do not bundle unrequested optional modules.

Proposed public repository: ramseys1990/AfterGrid-Marketplace (create only when starting the marketplace milestone). Keep official core/modules/four themes in AfterGrid; marketplace holds versioned contribution schemas, templates, manifests, catalog index, validation/publishing workflows and modest package release assets. Large licensed content points to reviewed upstream downloads, not mirrored to GitHub by default. Start with one trusted catalog. Do not introduce a marketplace backend, plugin runtime, arbitrary execution API, cloud accounts, telemetry, or arbitrary third-party repository support in the initial releases.

## Shared package/catalog contract

Freeze a small versioned schema at the foundation milestone, reuse the local theme contract and existing module definitions/content tooling. Proposed fields: namespaced package ID/type, package version, schema version, publisher, description, license and attribution, minimum/maximum supported core or package API versions, architectures where applicable, reviewed artifact URL/size/SHA-256, dependencies, permission summary, release notes, optional validated raster preview and package-specific data. Catalog includes monotonic revision, generation time, supported schema, package versions, deprecation/revocation advisories and authenticated metadata. Deterministically generate it from reviewed manifests; publish immutable versioned artifacts and authenticated index (e.g. signed catalog with pinned trust root, exact artifact digests). Define key rotation/recovery and stale/rollback/replay handling before real distribution. HTTPS and checksum alone do not authenticate a catalog against compromised publishing. Sign only reviewed outputs; protect publishing workflow and credentials; untrusted PRs cannot publish or access release secrets. Review each new/updated release, not only initial listing.

Client fetches static index on explicit refresh or opt-in periodic polling (proposed 24h, conditional ETag/Last-Modified, bounded timeouts/size/backoff, no telemetry). No network requirement at startup, no polling by default. Cache last verified catalog atomically; preserve known-good cache on failures; show last verified time, offline/stale status and errors; do not present stale advisories as fresh. Enforce compatibility and authenticated artifact identity again on install/update; stage in bounded private storage, validate type and paths, refuse traversal/symlinks/unexpected files/excessive expansion; no execution from catalog refresh. No automatic installs. Explicit approval for initial install and updates; later opt-in per-package auto-updates only after equivalent safety validation. Preserve installed packages and user data on delisting; warn/block new installs or unsafe updates per reviewed advisory policy. Rollback only where data/schema compatibility is verified. Preserve existing core and module update isolation.

Trust labels: Official (maintained by AfterGrid), Reviewed community (maintainer-approved version, not a security guarantee), Local/unreviewed (manually imported supported formats only). Local imports initially themes and supported content, never arbitrary Compose. Curated marketplace displays official/reviewed packages only. No trust escalation from author-supplied labels. Store installed versions, source, hashes and receipts locally; integrate with existing backup/recovery, and keep browser preferences separate.

## Staged milestones / master checklist

### M1 — Foundation and theme marketplace (proposed 1.1; after 1.0)
- [ ] Create public marketplace repository, CONTRIBUTING, maintainer review policy, schema/examples, licensing and reporting/delisting process.
- [ ] Define versioned catalog/package compatibility, signing/trust-root/revocation/rotation and deterministic CI validation/publishing.
- [ ] Implement bounded manual refresh, optional 24h polling, conditional requests/backoff and verified local cache; no new service.
- [ ] Build marketplace browsing/search/filter/detail, publisher/compatibility/trust labels and separate installed/update states using shared UI components.
- [ ] Reuse Phase 4 theme manifest validation for curated theme download, preview, install, select, update, reset and removal. No arbitrary CSS/JS or new external assets; use safe fallback.
- [ ] Test signed index/artifact verification, corrupt/incompatible/replayed inputs, cache behavior without WAN, failed fetch, opt-in policy, core upgrade and recovery of installed theme. Document first reviewed community submission and install end-to-end.
Exit: an ordinary administrator can discover and install a reviewed theme and use it on a disconnected LAN; invalid/untrusted artifacts are refused and no startup or guest functionality depends on marketplace.

### M2 — Content packs (proposed 1.2)
- [ ] Define typed content manifests: category, supported importer/module, file metadata/size/checksum, upstream URL, version/date, region/language, license/attribution and source provenance; distinguish collection/preset from actual verified files.
- [ ] Reuse existing Kiwix catalog/archive, maps/routing and other reviewed native import paths; enforce explicit dependency, storage/temporary space estimates and download confirmation. No new generic downloader or arbitrary install scripts.
- [ ] Stage, verify, index and safely remove/restore supported content; preserve existing libraries; support interrupted transfers via existing mechanisms.
- [ ] Curate licensed sample content packs; verify distribution rights and source quality (especially medical/safety references, clearly indicate source and date). Respect upstream terms and avoid copying massive assets to GitHub.
- [ ] Test bad checksum, unsupported format, traversal, insufficient space, interrupted download, offline reading, removal/retention and backup coverage. Document USB/local import where supported.
Exit: discover and acquire a reviewed pack, verify native use offline, preserve prior content through failure and removal.

### M3 — Reviewed community modules (proposed 1.3)
- [ ] Extend the existing reviewed module.yaml/compose.yaml contract only where needed: ID/category/upstream, dependencies, supported architectures, readiness, bounded configuration, ports, persistent storage, native auth/LAN policy, backup/restore and update constraints.
- [ ] Design admin admission and fixed worker review boundary for versioned installed definitions; review and validate fully resolved Compose configuration (including interpolation, dependencies, paths, profiles/extends/includes), not only raw YAML. Do not allow a downloaded manifest to authorize itself or alter worker guards.
- [ ] Default deny host privilege: Docker socket, privileged containers, host namespaces, arbitrary devices/capabilities, unrestricted host bind mounts, cross-app/core data, arbitrary scripts/builds, unreviewed images or dynamic command injection. Pin reviewed images by digest. Exceptional hardware permissions need explicit per-version maintainer review, bounded policy and admin consent; defer if cannot safely support. No arbitrary local Compose import.
- [ ] Contributor tests and manual review verify source provenance/license, lifecycle, genuine readiness, authenticated native access, data ownership/retention, backup/restore, offline behavior, upgrade/migration and uninstall. Supply chain review each version; reject unsupported native prerequisites rather than inventing orchestration.
- [ ] Integrate install/configure/update/uninstall with existing queue, Compose projects, port conflict protection, verified backups, no-pull recovery and isolation; no Docker socket in portal, no broad worker commands.
- [ ] Test malicious definitions and archive inputs, permissions, dependencies/ports/conflicts, failed lifecycle, no unrelated container/data changes, controlled update and backup/recovery on disposable Linux then designated real LAN host.
Exit: one reviewed community module operates through existing safe lifecycle, with actual native acceptance and documented permissions. Never certify arbitrary Docker images as safe merely because they are listed.

### M4 — Creation and portability (later; sequence based on demand)
- [ ] Theme Studio: local palette/token editor with live preview, both modes, contrast/focus checks, safe reset, validated import/export and contributor submission instructions. No custom code.
- [ ] Portable package collection: selected signed manifests/assets plus required exact Docker images and prerequisites where applicable; verified local import with no internet fallback, explicit omissions/compatibility, reuse existing recovery/image save/load tools; do not conflate install pack with complete recovery.
- [ ] Test disconnected transfer via USB/LAN to independent compatible installation, exact integrity, install, native readiness and no source mutation. Preserve custom theme/package metadata in existing backup/recovery.
- [ ] Consider additional explicitly trusted catalogs only after real demand and a trust/security design review. Not committed scope.
Exit: ordinary users can create and share valid themes; offline installations can import a verified package collection with all required local prerequisites.

## Acceptance and maintenance

Track implementation separately from actual verification in ROADMAP.md; record revision, tests, environment, failures, mitigations, and user-visible evidence. Small focused PRs, update checklists as each slice is verified. No completion claims based on mockups. No public catalog polling, download or module admission until its security gate passes. Keep current Phase 3 and 1.0 requirements independent; the marketplace must not delay the appliance release. Future modules/content mentioned in mockups (weather stations, power, local AI, home automation, etc.) are examples, not committed functionality.
