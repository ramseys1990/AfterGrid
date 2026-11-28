# AfterGrid Phase 4 design lab

Standalone, unshipped UI prototype. No API calls, live credentials, service actions or Docker dependencies. The Phase 3 portal, runtime assets, existing CI and roadmap acceptance counters are unchanged. A separate UI prototype workflow runs without Docker. The prototype is deliberately outside core/ and is not copied into the image.

## Preview

From a checkout of feature/ui-overhaul, run from the repository root:

    python -m http.server 8765 --bind 127.0.0.1 --directory prototypes/ui

Open http://127.0.0.1:8765/ in a browser. Stop the temporary server with Ctrl+C. No internet connection required once the files are local. No installation of AfterGrid is needed. GitHub source view is not an interactive hosted preview. The prototype uses a restrictive connect-src none policy; local assets are served from the same origin. Never enter real credentials or mistake the simulated workspace selector for authentication.

## Current slice

- Overwatch reference theme, Outpost, Essential and Fortress, each in light/dark/system; semantic tokens, shared CSS components, local inline SVG icons, system font, compact/comfortable density and reduced motion. Browser preference persistence, reset and invalid-ID fallback. All built-ins use the same versioned package envelope and palette validator as custom themes. Local file/paste import, browser-local persistence, duplicate/size/contrast validation, JSON copy/download, removal and fallback are implemented. Server defaults, server-side storage and backup/recovery integration remain unimplemented.
- Responsive shell and explicit household/admin preview switch, installed-tool launcher with search/favorites, overview, filterable application catalog/detail and simulated install/remove, appearance, detailed maps/route, communications/PACE, household/inventory, content, updates, backup/recovery views, five-stage core-only-default first-run simulation, and accessible native dialog pattern with cancel/Escape/focus return.
- Example-only data: no real metrics, map content, inventory, live mesh data, backups, updates, or authentication. Prototype lifecycle changes are in memory only.
- Palette validation: twelve text/accent-to-background combinations plus accent-button text checked per mode, minimum 4.5:1. Does not establish WCAG conformance of the rendered UI. No arbitrary CSS/JS imports, external assets or custom code.

- Future marketplace preview: hypothetical local catalog with search and type filtering, package details, trust/compatibility/size disclosures and simulated refresh/approval. No remote catalog or real installs.
- Application details show separate example service state, native access, update/backup status and advanced diagnostics. Start/stop/restart and install/remove are simulated in memory. Other operational buttons preview a confirmation and append example activity; they do not execute the underlying action.

## Community theme package v1 draft

See theme.schema.json and example-theme.json. The envelope has schema_version, theme_api, version, author, license and the palette manifest (theme). All four built-ins use this envelope internally. Local imports require a local.* or community.* namespaced identifier; built-in IDs cannot be replaced. Exporting a built-in creates a namespaced editable copy. Local packages are limited to 16 KiB each and 16 installed per browser. Runtime validation is authoritative and adds contrast, whitespace and metadata checks beyond JSON Schema. Hex values only; bounded radius; no arbitrary CSS, HTML, JavaScript, font upload or external resources. Metadata is escaped on display. Invalid stored packages are ignored. The exported JSON is a prototype contract and may change before 1.0; the server-side import/admission, persistence and recovery gates remain open.

## Theme Studio experiment

Appearance now includes a local visual editor based on the active palette. Choose the package name, namespaced identifier, author, license, description, corner radius and nine semantic colors in each light/dark palette. The preview has scoped tokens; changing an invalid draft never changes the active portal. Contrast diagnostics show the minimum checked pair for each mode, and saving requires the same package validator used by imports. Save creates a new local package and uses the existing browser-local storage/import path. No external assets, executable content, marketplace publishing, server persistence or editing existing packages is implied. Theme Studio remains a future feature experiment rather than a v1.0 acceptance requirement.

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

No dependency installation. The committed source was read back, JavaScript syntax compiled and eight committed assertion bodies passed in an isolated JS runtime adapter (not the actual Node runner). A standalone browser_test.py runs a temporary loopback static server and exercises eight palettes across desktop/tablet/phone widths, system switching, preferences/reload, local package import/export/rejection/removal, metadata escaping, visual editor scoped preview and invalid contrast rejection, save/reload, workspace navigation, search/favorites, catalog detail and simulated lifecycle, confirmation cancel/Escape, core-only setup, marketplace filters, and off-origin request refusal. Run with the existing project Playwright version 1.51.0 and Chromium installed: python prototypes/ui/browser_test.py from the root. A dedicated UI prototype checks workflow runs the Node harness and browser test without Docker; its result must be collected before claiming browser acceptance. Existing browser acceptance tests remain separate. Check actual contrast, touch targets, native dialog focus and responsive screenshots. No checklist completion or production acceptance claimed.

Next: collect the dedicated CI results and fix failures; review actual rendered desktop/mobile layouts and accessibility beyond the initial checks; finalize the pre-release theme contract and server storage/backup design. Follow [the production integration sequence](INTEGRATION.md) one real view at a time after Phase 3 closure or approved deferral. Keep marketplace implementation post-1.0; its preview is not a release requirement.


## CI repair and operational UX follow-up

The previous UI workflow (46098332797, revision 2eb12b7) passed all eight Node tests, but its Chromium dependency step failed because ubuntu-latest resolved to Ubuntu 26.04, unsupported by the pinned Playwright 1.51.0 release. The standalone workflow now explicitly uses ubuntu-24.04. Core checks (46098332851) separately failed during pytest collection because the standalone browser script imported Playwright at module import time. That dependency is now imported inside main(), keeping core pytest collection independent of the optional browser package. Existing core workflow and runtime files are unchanged. Re-run both workflows; do not claim browser acceptance from the Node result.

The prototype overview now distinguishes preview availability, appliance LAN reachability, internet reachability and physical offline verification. The administrator-only preview notification shortcut and inbox show example notices, action-related events, unread count, read/unread controls, attention filtering and a related-page shortcut. These are session-memory fixtures, not durable server job records; the production implementation must derive notifications from actual authorized job events, persist history appropriately and preserve state on refresh. Household preview hides administrative notifications. New browser assertions exercise these controls. No live network probing or external service was introduced.


## Rendered UI evidence and visual refinement

The notification-enabled revision 23e70ec completed the standalone browser workflow (46104006269) successfully. The earlier repaired revision 07ca6e4 passed all eight native Node tests and Chromium regression (46103935272). These are isolated fixture tests, not live service or physical WAN acceptance.

The next browser run exercises mobile menu focus on open, Escape dismissal and focus restoration. Theme motifs now differ: Overwatch has a subtle grid and top-accent metrics, Outpost retains contours, Essential removes the decorative pattern, and Fortress uses diagonal lines and left-accent metrics. Narrow-screen headers and cards have bounded wrapping. No new theme package capabilities or external assets are required.

Set AFTERGRID_UI_SCREENSHOTS to a local output directory when running browser_test.py to capture 16 desktop/phone overview images (all four themes in both modes) and 20 representative screen images in Overwatch dark. CI uploads the PNGs as the aftergrid-ui-screenshots artifact with 14-day retention. Captures use only fixture data. The artifact and new regression results must be reviewed before claiming visual acceptance; no screenshots were manually reviewed in this change. Keep full accessibility assessment, physical LAN verification, native-module branding and actual production integration open.


## Second visual iteration

The first rendered review used the successful UI and core workflows at 55f45e4 (UI run 46104204983, screenshot artifact 15247617572). This revision addresses the most important review findings: operations/resources/system navigation groups; a smaller administration heading and higher connection indicators; four compact metrics and six management shortcuts; a two-column mobile household launcher with installed-resource-aware bottom navigation; independent example Grocy/Homebox catalog entries with category filtering; separate removal controls; and a collapsed advanced Theme Studio. Household supplies remain grouped for ease of use. The prototype retains its synthetic IDs and does not represent a production module registry. Existing native apps are not themed or modified.

The regression suite now exercises the inventory category split, compact household grid, mobile navigation and advanced editor. Capture and review new rendered evidence before visual approval; earlier green runs apply only to earlier commits. Phase 3, main runtime and live appliance are unchanged.


## Operations workspace refinement

Revision b315a5d passed the UI workflow (46112590658) after the second visual iteration. Core acceptance was still running at the first check. New changes build on that baseline: map-first schematic with a larger responsive canvas, route endpoint swap and explicit unavailable route metrics; four ordered PACE cards with untested status, separate communications/device panels; a prominent restore-not-verified banner and compact catalog category/storage metadata. No actual map, radio, recovery or storage measurements are connected. Browser tests cover the new route and PACE controls, catalog metadata and unverified recovery wording. New screenshots and full regression must be reviewed against the new revision before approval.


## Content, discovery and brand refinement

The content manager now has example archive status filters, keyboard-focusable shortcuts to knowledge, regional maps and routing sections, and a distinct illustrative storage summary that does not imply measured disk capacity. The marketplace prioritizes search and package browsing, with a compact explicit unverified-cache banner and expandable trust/refresh details. The local vector brand mark is consistent on desktop and mobile; it is a candidate identity, not an approved final logo. Forced-color styling preserves selected navigation and important boundaries. The corresponding browser assertions cover the new content filters, focus shortcuts and marketplace trust wording. Manual rendered and accessibility review remains required.

Native module styling belongs to roadmap U5. The core theme must not be injected into native pages. Review supported settings and licenses for each pinned version, record configuration persistence/restore and reset behavior, and keep native permissions unchanged. Until that review is complete, all app icons are generic local functional symbols and native interfaces retain their original styling. No unsupported upstream capability is claimed.


## Rendered second-iteration review

Reviewed all 36 screenshot file dimensions and representative Overwatch desktop and phone captures from successful run 46112590658, artifact 15250711150, revision b315a5d. Against run 46104204983 at identical viewport dimensions: phone overview 2764 to 1370 px (-50.4%); household home 1915 to 1138 (-40.6%); phone appearance 3870 to 1884 (-51.3%); desktop overview 1501 to 1001 (-33.3%). Phone application catalog grew from 2098 to 2417 px with the extra independent app and detail layout from 2353 to 2531 px. Follow-up CSS reduces card padding and makes split-panel contents align at the top; the new rendering is unverified. The fixed household bar is visible in the capture; keyboard-focus obstruction is addressed by later scroll padding, pending regression. These screenshots predate the latest map, PACE, content, logo and accessibility changes. Do not treat this review as approval of those changes or production acceptance. Final gate remains a successful exact-revision regression, rendered review and operator design approval. Native module appearance research is documented in NATIVE_APPEARANCE.md.


## Mobile page sections

The operator requested shorter mobile pages with bottom tabs. On viewports up to 850 px, the household shortcuts remain and administration gains Overview, Apps, Resources, Alerts and System bottom navigation. Longer pages have a compact page-section selector, showing only the selected group: overview status/shortcuts/activity, content library/maps/routing/storage, appearance display/packages/studio, backup readiness/coverage/recovery, map/places/offline, PACE/devices, app service/maintenance/advanced, updates core/apps and household administration households/inventory/connections. All is an escape hatch. Desktop continues to display the full page. Sections reuse existing DOM nodes and preserve entered values when switching within a page; section selection is session-memory only and resets on reload. No new routes or API calls. Fixed mobile navigation reserves safe-area and keyboard-focus spacing; route changes return to the top. Extended browser regression covers selection, hidden panels, preserved input, desktop fallback and individual mobile screenshot captures. Review actual results before declaring accepted.
