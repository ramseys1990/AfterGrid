# AfterGrid development rules

AfterGrid is an offline-first, modular preparedness appliance for ordinary users.

## Appliance-first acceptance

The target operator is a household member with no Docker, Linux, networking or identity-management experience. Optimize for the number of decisions, commands and accounts required to get a working appliance, not the sophistication of its architecture.

- One initial install command, a printed LAN URL, and browser setup. Routine administration must not require SSH, a terminal, custom DNS, a reverse proxy, or a separate identity service.
- The default dashboard offers only actions a normal operator can use: install, open, configure, update, back up, and remove an application. Show progress and a plain-language next step on failure. Put diagnostics and exceptional recovery in advanced documentation.
- Keep native read-only resources accessible without needless accounts on the trusted LAN. Keep authentication for administration and private or editable data. Use supported upstream setup and permissions; do not bypass security.
- Reuse Docker Compose for lifecycle and Kopia for backups. No new daemon, proxy, orchestrator, database, or framework merely to automate an existing command. Add complexity only for a demonstrated user need or concrete safety requirement.
- Prefer one straightforward, manually approved release update before background or automatic update policies. Only core/worker may restart during a core update; independent applications keep running. Never expose arbitrary host commands to the portal.
- Each milestone must define a simple user journey, test that journey, and stop adding scope when it works. Defer speculative features and rare failure automation if a safe, documented recovery path exists. Never represent a disposable test as a released feature.

## Non-negotiable design
- Compose first: each optional module is a standard, independently named Docker Compose project. Use upstream maintained images and documented settings. Prefer configuration to custom deployment logic.
- Install only the core by default. The initial CLI bootstraps Docker and core, then hands off to a browser wizard.
- Let Compose pull, start, stop, restart, inspect and remove containers. Stream its real output; do not implement a second orchestrator, downloader or fake progress estimates.
- Module prerequisites: ordinary intra-stack dependencies belong in Compose; shared module dependencies use a simple list. Only add special hooks for demonstrated needs.
- Local administrator authentication, trusted-LAN shared resources, optional family profiles. Households are organizational groups; ownership and physical location are distinct. No mandatory OIDC, Authentik, SSO, identity service or external database.
- Native app authentication is acceptable; never bypass an app's security. Sensitive modules retain their own access controls. Admin operations are authenticated and CSRF protected.
- One shared Homebox for durable assets/QR labels and one shared Grocy for consumables/recipes. Avoid duplicating inventory. Use stable local hostnames for labels.
- Kopia handles backups, encryption, retention and scheduling. Use application-consistent snapshots or database exports; use Docker image save/load for offline recovery. Initial installation can be online. Do not claim full offline recovery until tested.
- Debian/Ubuntu, bare metal, Docker hosts and suitable Proxmox guests; no fixed VM/CT IDs, dev branches or lab-specific configuration. Never change unrelated Docker projects or install Docker on the Proxmox hypervisor.
- No cloud dependencies or telemetry by default. No public exposure by default. Offline functionality must be tested, not assumed.
- Docker access is privileged: portal does not expose arbitrary shell, Compose, volume or Docker commands. Use a narrow separate worker with reviewed module definitions and fixed actions; keep secrets out of logs.
- Keep data on persistent storage; stop/uninstall preserves data by default; deletion requires distinct confirmation.
- Pin reviewed application versions for releases. Auto-updates opt-in per module; preserve data and account for schema changes.
- Do not add dependencies or abstractions for hypothetical future features. Keep core resource footprint small.

## Workflow
Build vertical slices, use small focused changes and practical tests. A module is complete only when install, real readiness, start/stop, configuration where needed, data preservation, offline behavior where applicable, backup/restore and uninstall have been exercised. Record untested behavior honestly. CI supports development, not a substitute for runtime validation. Never make unrelated changes, publish personal data or secrets, or claim unrun tests passed.
