# Homebox

Install using the portal. The worker generates and retains the required API-key pepper automatically in its private state volume. Use the native account registration page on http://127.0.0.1:8082 (SSH forward port 8082 for a remote server). Registration starts open for initial setup, so do not expose this port. Create one shared collection and use locations and tags for household ownership and storage. Close registration before enabling family LAN access; browser settings for this are planned. Stable local DNS and actual QR label scanning are not yet validated. Data lives in data/homebox. Removing containers retains it. The pinned release tag is not a digest; verify image provenance before production use.

See [LAN access](../../docs/LAN_ACCESS.md) for explicit sharing, stable DNS-based QR links and closing registration. Actual QR scans remain unverified.

Managed maintenance-stop snapshots and isolated database verification are available from the portal. The worker-generated pepper is not included; preserve it separately. Expanded CI pending.
