# Phase 4 production integration — proposed sequence

Status: preparation only. This design lab is not packaged with the core. Do not deploy it as the real portal or merge runtime changes until Phase 3 closes or the operator explicitly approves deferring the remaining gates. Use the latest main baseline when integration starts; do not replace newer Phase 3 implementation with prototype code.

## Integration slices

| Slice | Scope | Acceptance gate |
|---|---|---|
| I0 — Design acceptance | Render the standalone prototype on desktop, tablet and phone; review four themes in both modes, keyboard, contrast, menu, confirmations and failure states. Resolve any CI failures and approve default theme. | Record exact commit, screenshots and test results. A screenshot is not runtime acceptance. |
| I1 — Runtime design tokens | Add only local shared CSS/token assets, safe defaults and preference handling to the existing four served pages. Retain IDs, routes and existing event handlers. Explicit Dockerfile asset list and static MIME routes; no CDN or framework. | Core starts with no WAN; existing browser and API checks pass; theme changes never modify permissions or native applications. |
| I2 — Shell and navigation | Migrate shared header, household launcher and administrator task navigation while preserving existing authenticated session logic. Keep the original working views accessible until each replacement is exercised. | Guest cannot see private inventory, credentials, logs or backup data; API guards still refuse unauthorized actions. Refresh/reload, back navigation and mobile keyboard/focus pass. |
| I3 — Application lifecycle | Replace presentation for real catalog, readiness, install, native setup, share, start/stop/restart, uninstall, progress and failure messages. Use actual module identifiers and server job records; do not translate hypothetical packages into real modules. | Existing module lifecycle and retry tests pass; preserve data by default and confirm destructive actions separately. No duplicate jobs on reconnect or repeated clicks. |
| I4 — Resource pages | Adapt existing map/route, communications, household, inventory and content management views one at a time. Keep native local MapLibre resources, map ranges, routing estimates, PACE plans, inventory ownership/storage and actual content import/export APIs. | Guest/admin boundaries, native behavior, actual offline resource visibility, independent retries and existing functional checks pass. |
| I5 — Maintenance | Migrate updates, backup, recovery and activity views without altering worker operations, admission gates or release handoff. Display linked current verification and historical job states separately. | Reviewed core update preserves independent containers; verified restore evidence is not inferred from snapshot existence. Re-run applicable regression on the designated host. |
| I6 — First run | Migrate setup and optional selection wizard last, using the existing token and local administrator creation flow. Preserve unselected default, real per-app install progress, restart/resume and native setup. | Fresh core-only and optional-app installs, failure/retry, account/session persistence and browser-first LAN onboarding pass. |
| I7 — Local theme packages | Finalize server-side manifest validation and bounded storage, admin-only install/remove/default, guest-safe selection, offline assets, reset/fallback, import/export and backup/restore. | Untrusted packages rejected, default recovery safe, exact manifests preserved across core update and restore, no arbitrary styling/execution. |
| I8 — Release acceptance | Run complete existing and new regression suites, representative phone and desktop LAN journeys, physical disconnected use, accessible rendered UI, documentation and recovery. | Record revision-specific real-machine evidence; no premature Phase 4 checklist completion. |

## API and security rules

- Keep the current API payloads and status codes in I1–I6. If a contract must change, make a separate reviewed functional PR with a migration and regression. Preserve existing server-side authorization/CSRF and worker allowlists; the UI does not grant access.
- Treat prototype workspace switching as design-only. Production guest/admin mode derives from real session state; no fixture counters, example readiness, decorative map route or simulated lifecycle actions ship.
- Use fixed operation-specific confirmation copy and retain the original operation consequences. Disable pending controls and reconcile the authoritative job ID after network failures; do not infer that a timed-out operation failed.
- Preserve focus, scroll, expanded sections and selected filters during status polling. Prefer targeted DOM updates over rebuilding whole pages. Show stale/unknown data explicitly, not as zero or healthy.
- Native account setup still uses existing supported private routes and explicit LAN sharing; never persist native passwords in browser preferences or logs.
- Existing installer, Compose worker, Kopia and core update isolation remain the implementation foundation. Do not add a daemon, external database, identity system or arbitrary execution mechanism.

## Theme persistence proposal (I7)

Use existing core configuration storage and backup mechanisms after auditing the actual export/restore paths. Prefer small validated records in the existing SQLite database if those records are demonstrably included in consistent snapshots and restored startup. No additional database, package daemon or general file-serving route. Store normalized manifest plus origin (built-in/local/reviewed in future), identity and version; enforce size and count limits on the server, unique IDs, reserved built-ins, strict schema and transaction-safe insertion/removal. Do not rely on client validation. JSON parsing must reject ambiguous duplicate keys and non-finite values; apply limits before parsing and revalidate before rendering. Keep package identity and authenticated origin separate; local metadata cannot claim reviewed status.

Browser-local selection/mode/density/reduced-motion remains independent of authentication. Admin default is an allowlisted installed theme identifier. Guests may fetch only the public safe token subset of installed themes and select locally; installation/removal/default mutations require existing admin authorization. No credentials or private metadata in preferences. On missing, invalid or incompatible themes, resolve to a safe bundled fallback without contacting the network. Deleting a default theme must atomically reset it to a bundled fallback. Validate actual text/control/focus contrast and keep semantic warnings distinguishable without color. Document schema evolution before promising stable public compatibility.

Use the same import contract for future curated marketplace themes, but no remote catalog synchronization or module admission in the v1.0 gate. Theme Studio in the design lab is a future feature experiment, not a requirement to ship the initial stable portal.

## Regression matrix

Run existing unit, installer, native lifecycle, recovery, core-update, map browser and permission tests unchanged where possible. Add focused browser tests for keyboard, focus, responsive layout, theme switching/fallback and absence of unexpected external requests; test actual server integration separately from standalone fixture behavior. Check representative long names, error text, empty states, unavailable services, stale status, multiple jobs, narrow screens and reduced motion. Verify no secrets appear in screenshots or logs. Compare resource footprint before/after on representative core-only and larger configurations.

Integrate as small focused pull requests, recording verified evidence in the roadmap. Stop when a functional slice works rather than developing speculative infrastructure.
