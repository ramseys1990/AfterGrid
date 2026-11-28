# AfterGrid Phase 4 design lab

Standalone, unshipped UI prototype. No API calls, live credentials, service actions or Docker dependencies. The Phase 3 portal, runtime assets, CI and roadmap acceptance counters are unchanged. The prototype is deliberately outside core/ and is not copied into the image.

## Preview

From a checkout of feature/ui-overhaul, run from the repository root:

    python -m http.server 8765 --bind 127.0.0.1 --directory prototypes/ui

Open http://127.0.0.1:8765/ in a browser. Stop the temporary server with Ctrl+C. No internet connection required once the files are local. No installation of AfterGrid is needed. GitHub source view is not an interactive hosted preview. The prototype uses a restrictive connect-src none policy; local assets are served from the same origin. Never enter real credentials or mistake the simulated workspace selector for authentication.

## Current slice

- Overwatch reference theme, Outpost, Essential and Fortress, each in light/dark/system; semantic tokens, shared CSS components, local inline SVG icons, system font, compact/comfortable density and reduced motion. Browser preference persistence, reset and invalid-ID fallback. Built-in theme format is a provisional inner palette contract, not the final package manifest; custom import/export and server defaults are not implemented.
- Responsive shell and explicit household/admin preview switch, installed-tool launcher with search/favorites, overview, filterable application catalog/detail and simulated install/remove, appearance, local resource and management view stubs, five-stage core-only-default first-run simulation, and accessible native dialog pattern with cancel/Escape/focus return.
- Example-only data: no real metrics, map content, inventory, live mesh data, backups, updates, or authentication. Prototype lifecycle changes are in memory only.
- Palette validation: twelve text/accent-to-background combinations plus accent-button text checked per mode, minimum 4.5:1. Does not establish WCAG conformance of the rendered UI. No arbitrary CSS/JS imports, external assets or custom code.

## Initial source audit and integration map

The current core has four served HTML views and explicit asset routes in core/app.py. core/Dockerfile copies an explicit list of runtime assets; prototype files are intentionally not in that list. Do not change the image/asset routes until integration is approved.

| Existing journey / files | Existing contracts to preserve | Proposed destination |
|---|---|---|
| core/index.html + app.js, setup/login/wizard | /api/status, /api/setup, /api/login, /api/logout, /api/admin/status, /api/admin/first-run; one-time token, admin session and server-side guards | First-run and authentication views |
| dashboard, catalog, renderModules, jobs, installation summary | /api/modules, /api/admin/modules/{ident}/{action}, /api/admin/jobs, /api/admin/installation-summary; fixed worker actions and persistent real progress | Applications/detail, activity |
| preparedness and household directory | /api/preparedness, /api/households, admin household and inventory endpoints; no private inventory for guests | Household launcher and admin inventory |
| content and regional downloads | /api/admin/content/*, /api/admin/maps/*, /api/admin/routing-data/*; explicit estimates, confirmation and verified downloads | Content & maps |
| update and backup panels | /api/admin/core-update/status and reviewed release workflow; /api/admin/updates/*, /api/admin/backups/*, /api/admin/kopia/*, scoped module endpoints; activation gates and data safety | Updates, backup/recovery and diagnostics |
| core/maps.html, maps.js, maps.css, region.js | local MapLibre assets, range requests, route/plan/search/import APIs; guest view/admin edits | Maps and navigation; retain actual map renderer |
| core/communications.html, communications.js | /api/communications and admin plan/device/check/delete; manual checks are not live telemetry | Communications/PACE |
| core/native-setup.html, native-setup.js | /native-setup/{ident} and /api/admin/modules/{ident}/native-setup; existing account verification, local-only setup, explicit LAN sharing, no credential storage | Application onboarding |

Existing style.css and maps.css hardcode dark colors. app.js is approximately 88 KB, manages many unrelated workflows, uses synchronous confirmations and a polling refresh. Preserve IDs and selectors used by existing browser tests until replacements are validated. First integrated slice should replace presentation without changing endpoint payloads, authentication, authorization, job semantics, operation confirmations or native app permissions. Keep unshipped prototype separate while Phase 3 validation continues. Refresh state preservation and operation-specific failures need explicit tests; do not count them complete based on prototype.

## Validation and next steps

Run pure checks with Node 22 or later:

    cd prototypes/ui
    node --test themes.test.js

No dependency installation. The initial committed source was read back, JavaScript syntax compiled in an isolated JS runtime and built-in palette validation/fallback exercised there. The Node harness and real browser rendering have not yet been run. For browser acceptance test all four themes in both modes, system switching, keyboard and focus, desktop/tablet/phone widths, workspace navigation, filtering, favorites, settings reload, core-only wizard, detail and confirmation cancel/Escape, and no off-origin requests. Existing browser acceptance tests remain separate. Check actual contrast, touch targets, native dialog focus and responsive screenshots. No checklist completion or production acceptance claimed.

Next: approve design refinements, implement final schema and shared accessibility component contracts, deepen page prototypes using explicit fixtures, add automated browser tests, then integrate one real view at a time after Phase 3 closure or approved deferral.
