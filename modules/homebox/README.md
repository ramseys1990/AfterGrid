# Homebox

Install using the portal. The worker generates and retains the required API-key pepper automatically in its private state volume. Choose Set up native account on the Homebox card while signed in as AfterGrid administrator. Create the native account through the supported registration API, or verify an existing account. Save the local login email and password. Registration starts open on the loopback-only app for initial setup; keep its port private until setup is complete. Create one shared collection and use locations and tags for household ownership and storage. After verified setup, use Share on LAN to close registration and enable family access. Native login remains required. The setup form does not store your password or send credentials through worker jobs. Stable local DNS and actual QR label scanning are not yet validated. Data lives in data/homebox. Removing containers retains it. The pinned release tag is not a digest; verify image provenance before production use.

See [LAN access](../../docs/LAN_ACCESS.md) for explicit sharing, stable DNS-based QR links and closing registration. Actual QR scans remain unverified.

Managed maintenance-stop snapshots and isolated database verification are available from the portal. The worker-generated pepper is not included; preserve it separately. Expanded CI pending.
