# Phase 4 — UI overhaul and theme extensibility

Status: approved planning direction, not implemented. Begin implementation after Phase 3 functional closeout (or explicit operator-approved deferral of remaining gates). Target 0.9, before 1.0. See [marketplace roadmap](MARKETPLACE.md). Keep Phase 3 evidence and acceptance separate.

## Product direction

One AfterGrid portal, two experiences: a welcoming household launcher organized by tasks, and an authenticated operations/administration workspace. Use a shared shell, components, icons and consistent AfterGrid wordmark/tagline (Life beyond the grid). The tactical operations-center concept is the reference for the first visual implementation, not a mandate for a military-looking default. Support all four built-in themes, each in light and dark plus system-following mode. Theme and density change presentation, not permissions, data or functionality. No new service, frontend framework or identity provider is assumed; start from the existing bundled HTML/CSS/JS and FastAPI endpoints. Keep native app UIs and security intact. No public exposure or mandatory accounts for existing shared LAN resources.

| Theme | Design direction | Starter palette (subject to contrast testing) |
|---|---|---|
| Outpost | Modern outdoors/preparedness; topographic texture, warm surfaces, rounded cards | Pine #263F34, sage #829477, sandstone #D5BF97, canvas #F2EFE6 |
| Essential | Minimal consumer technology; generous spacing, restrained accents | Ink #222936, blue #3978EF, pale gray #F8F9FB |
| Fortress | Industrial/rugged; graphite, steel, amber, sharper corners | Graphite #15181B, steel #30353A, amber #ECAA39 |
| Overwatch | Tactical operations center; charcoal, olive, green, subtle grid/topographic patterns | Near-black #101713, olive #233829, green #9ECB85, slate #35483A |

Final default theme to be selected after prototypes and accessibility testing; all four available without download. Shared logo across themes. No invented telemetry: mockup readiness percentage, battery/power, mesh connectivity and inventory counts are illustrative, not acceptance claims. Show observed state, source, timestamp, unavailable/not configured/not installed distinctly; distinguish internet reachability, LAN access, app readiness and offline content presence. Do not expose private inventory, backup metadata or diagnostics to anonymous LAN visitors.

## Information architecture

- Household home: installed/accessible tools, favorites (local), search app names/tasks, clear offline availability; knowledge, maps/navigation, communications/PACE, supplies/recipes, education, notes/media. Hide absent optional tools or explain them without exposing administration; core-only empty state links to admin setup. Do not imply searching third-party content globally.
- Administration: overview and actual health; installed applications and catalog/detail views; content and regional maps/downloads; households and inventory; updates; backup/recovery; settings/appearance; activity/jobs and advanced diagnostics. Accessible desktop sidebar and responsive mobile navigation. Native setup stays browser-first with explicit LAN sharing, native credentials, private access warnings and safe retry.
- First run: welcome/local administrator; optional app selection (nothing selected by default); review prerequisites/storage; real persistent job progress and independent retry; ready/next native setup actions. Skip to core-only. Do not reimplement Compose progress or change installer protocol.
- Application details: human-readable purpose plus upstream name, readiness, native login and LAN sharing, storage and data retention, lifecycle actions, backup/verification, approved updates and logs. Separate uninstall from destructive deletion; no silent installation.
- Map/routing, communications, PACE, inventory, content and recovery pages: reuse working APIs and native views. Preserve map keyboard/touch interactions and native app data. Keep advanced actions behind appropriate admin authorization, not simply hidden by CSS.

## Versioned theme contract (v1 target)

Use semantic CSS custom properties generated from a small validated declarative JSON manifest. Built-ins and local imports use the same schema and renderer; no arbitrary CSS/JS, HTML, remote URLs, templates, scripts or executable hooks. Proposed manifest fields: schema_version, id (namespaced, unique, bounded), name, version, author, description, license, theme_api compatibility, light/dark token maps, bounded style enums (radius, supported bundled fonts, approved patterns). Include foreground/background/surface/muted/border/accent/on-accent/focus/disabled and semantic status tokens or safe derived defaults; enforce accessible contrast for meaningful text, controls and focus. Semantic warnings and confirmation controls cannot be suppressed or recolored to misleading states; state is never color-only. Density and reduced motion are independent preferences, with accessible minimum target sizes. Start with bundled assets and predefined patterns; future package artwork restricted to bounded, validated local raster formats (no arbitrary SVG/HTML/fonts in v1 imports). Treat text metadata as data and escape it. No network fetch on theme activation.

Support browser-local preference per device, system mode using prefers-color-scheme, admin-defined installation default for new visitors, reset to built-in safe theme, and resilience to unknown IDs, invalid data or missing package. Store only non-sensitive preferences in browser storage; no new user identity model. Persist installed custom themes and admin default in reviewed core storage; include them in existing backup/recovery coverage and migration tests. Theme import/export restricted to appropriate admin installation and nonprivileged local selection; validate schema, size, identifiers, versions, token types/values, duplicate paths and safe storage; no overwriting built-ins or path traversal. Use plain JSON import first; defer package archives, custom font upload and theme editor until needed. Export round-trip and fallback must work without WAN. Provide documented example/schema and contributor guide before 1.0, but do not promise indefinitely stable pre-release schema. Future marketplace uses this same validated import path.

## Master checklist (0/20 initially; planning is not implementation)

### 4A — Design foundation
- [ ] Inventory existing routes, DOM components, API/security boundaries and UX evidence; map current features to the new navigation without losing functionality.
- [ ] Approve representative household/admin/first-run desktop and mobile prototypes; select default theme.
- [ ] Implement shared tokens, shell, semantic status, cards, forms, buttons, accessible dialog, navigation and error components; local fonts/icons.
- [ ] Implement versioned theme schema, renderer, four built-ins and light/dark/system preference with safe fallback.

### 4B — Household experience
- [ ] Redesign guest landing, task categories, installed-tool search, favorites and core-only empty state.
- [ ] Redesign preparedness/knowledge, maps/routing, communications/PACE, supplies and learning/notes/media entry points without inventing capabilities.
- [ ] Implement responsive navigation, touch/keyboard access and clear local/offline state.

### 4C — Administration
- [ ] Redesign overview, applications catalog and dedicated application detail/native onboarding views.
- [ ] Redesign content/download and maps/routing management, inventory/household views.
- [ ] Redesign updates, backups/recovery and activity/job views with linked current verification evidence.
- [ ] Replace native confirm/alert with accessible in-page dialogs; retain explicit consequences, server-side checks, cancel and focus return.
- [ ] Preserve expanded sections, focus, selected filters and scroll across polling; operation-specific errors and next steps; clarify backup denominators/exclusions.

### 4D — Setup and personalization
- [ ] Redesign first-run wizard, progress, independent retries and interrupted-session/resume behavior; core-only default.
- [ ] Add Appearance settings (theme, light/dark/system, comfortable/compact, reduced motion, reset); independent browser choices and admin default.
- [ ] Implement bounded admin local theme import/export, schema/example and compatibility docs; invalid import and safe fallback tests.
- [ ] Verify custom-theme storage, core updates, backup/restore and browser preference persistence without adding a new service.

### 4E — Release acceptance
- [ ] Test all eight theme/mode combinations, system switching, high contrast, keyboard/focus, reduced motion, mobile/tablet/desktop and no horizontal overflow.
- [ ] Run shared functional regression: guest/admin boundaries, setup, native LAN sharing, lifecycle, maps, content, updates, backup/restore, jobs, error/retry and destructive confirmations; no regressions to existing guards.
- [ ] Verify physical LAN phone and desktop on designated test host with WAN unavailable; no CDN/external asset requests, themes load, native tools retain access, and core-only update isolation remains intact. Distinguish disposable/browser network blocking from physical acceptance.
- [ ] Publish user screenshots/appearance docs and acceptance evidence (revision, environment, actual results, remaining exceptions); update release readiness and hand off to 1.0 gates.

Do not mark checks complete based on design images or unrun tests. Use focused PRs and keep real-machine validation separate. Existing [Phase 3 roadmap](ROADMAP.md#phase-3-master-checklist--installation-and-deployment) remains authoritative for current deployment work. Native application theme settings are optional upstream features, not part of the core theme guarantee. No marketplace polling, community module admission, content marketplace, theme editor or additional infrastructure is required to complete Phase 4 or 1.0.
