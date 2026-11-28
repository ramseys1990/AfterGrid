# Local network access

AfterGrid is a LAN-first appliance. The installer detects the private IPv4 source address of the default route and prints the portal URL. If it cannot detect one, it falls back to loopback; use AFTERGRID_BIND to choose the correct private address. No wildcard/public bind, router changes, public DNS or external identity provider is required.

## Configure once

Reserve the server address in your router, e.g. 192.168.10.4. Open http://192.168.10.4:8080 from any device on your LAN. Kiwix is available on port 8081 when installed. Homebox, Grocy and Kopia can all be explicitly shared from the admin dashboard, following native setup. No optional apps are installed automatically.

For stable DNS names, choose a local domain during installation, e.g. AFTERGRID_LAN_DOMAIN=aftergrid.home.arpa, and point the applicable local DNS records to the reserved server IP. Use the exact hostnames shown by the portal for installed modules:

| Name | Port |
|---|---|
| aftergrid.home.arpa | 8080 |
| homebox.aftergrid.home.arpa | 8082 |
| grocy.aftergrid.home.arpa | 8083 |
| kopia.aftergrid.home.arpa | 51515 |
| meshmonitor.aftergrid.home.arpa | 8085 |
| kolibri.aftergrid.home.arpa | 8086, 8087 |
| media.aftergrid.home.arpa | 8096 |
| notes.aftergrid.home.arpa | 8097 |

DNS records are not created automatically. If no domain is supplied, shared application URLs use the private IP directly. Reserve that IP before generating QR labels. A separate DNS name for each application is recommended: cookies are not isolated by port. Without separate DNS names, sign out of the portal before opening applications, especially untrusted content. Use a trusted HTTPS reverse proxy for administrative and backup credentials. HTTP mode is for a trusted private LAN only; never forward ports to the internet.

## Initial access and sharing

- Homebox: sign in to AfterGrid as administrator and choose Set up native account on its card. Create one native account for the shared collection, or verify an existing account. Save its local login email and password. Then return to the card and Share on LAN; registration closes and its native hostname option is set to the chosen stable URL.
- Grocy: choose Set up native account and replace the default admin/admin password, or verify an existing native administrator account. The bounded native API flow verifies the chosen login and refuses success unless the default password is rejected. It never resets an unknown existing password. Then return to the card and Share on LAN.
- Kopia: generated native UI credentials; authenticated administrator can reveal them on the configured portal origin after acknowledging HTTP risk. Share on LAN explicitly to enable the native UI; no default passwords. The portal only hides the link for family users; Kopia itself enforces its own credentials.
- Jellyfin: choose **Set up native account** to create a native administrator (or finish interrupted setup with the existing credentials), then explicitly **Share on LAN** on port 8096. Remote access is disabled by the setup form; local playback still uses native accounts and library permissions.
- Kolibri: choose **Set up native account** to provision the learning facility and administrator, then explicitly **Share on LAN** (ports 8086 and 8087). Guests can read imported content without an account; learners need accounts for progress, and administrators manage content. Self-registration and automatic/learner-requested downloads are disabled.
- DokuWiki (Notes): choose **Set up native account** while the application remains local-only. The portal enables Closed Wiki ACLs, disables registration, reporting and online update checks, and verifies anonymous access is denied. Then explicitly **Share on LAN** on port 8097. Create household accounts and assign permissions in DokuWiki; no shell or SSH forwarding is needed for normal setup.
- MeshMonitor: reveal and save its generated native administrator credentials in AfterGrid, explicitly Share on LAN, then Open application and sign in natively. Use the current password if it was changed. Native authentication remains required; the updated shared-origin first-login test and physical LAN/radio acceptance remain pending. Do not enable anonymous access merely to simplify setup.
- Kiwix and the shared offline map/route viewers do not require separate reader accounts; editing, downloads and administration remain protected.
- Return to local-only recreates the selected Compose project while retaining data. Homebox registration remains closed. Kopia may always be left local-only.

A root operator on an existing development installation can set AFTERGRID_BIND to the assigned private IPv4, AFTERGRID_ORIGIN to its full portal URL, and optionally AFTERGRID_LAN_DOMAIN in /opt/aftergrid/.env, then recreate core and worker with sudo docker compose up -d. Reapply any existing shared module configuration using its Start/Share action if changing the bind/domain. Do not change the address or name after printing labels without preserving the old URL.

Native setup keeps Homebox, Grocy, Jellyfin, Kolibri and DokuWiki loopback-only until the separate Share on LAN action. The AfterGrid administrator form sends credentials only to the fixed bundled application, with no proxy, SSH tunnel or external identity service. Credentials and native session tokens are transient and never enter worker jobs, activity output or portal storage. Native sessions used for verification are logged out on completion where the application is reachable. Use HTTP only on a trusted private LAN and acknowledge its unencrypted transport in the form. Native account setup is disabled in restricted recovery mode. If a change was submitted but verification fails, use Verify existing account with the same details before retrying creation or changing a password.

## Testing

Hosted CI tests Docker bindings with a disposable private address, not real Wi-Fi clients. Physical LAN, local DNS, QR scans, HTTPS trust and native account changes still require real-host testing.
