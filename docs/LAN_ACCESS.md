# Local network access

AfterGrid is a LAN-first appliance. The installer detects the private IPv4 source address of the default route and prints the portal URL. If it cannot detect one, it falls back to loopback; use AFTERGRID_BIND to choose the correct private address. No wildcard/public bind, router changes, public DNS or external identity provider is required.

## Configure once

Reserve the server address in your router, e.g. 192.168.10.4. Open http://192.168.10.4:8080 from any device on your LAN. Kiwix is available on port 8081 when installed. Homebox, Grocy and Kopia can all be explicitly shared from the admin dashboard, following native setup. No optional apps are installed automatically.

For stable DNS names, choose a local domain during installation, e.g. AFTERGRID_LAN_DOMAIN=aftergrid.home.arpa, and point these local DNS records to the reserved server IP:

| Name | Port |
|---|---|
| aftergrid.home.arpa | 8080 |
| homebox.aftergrid.home.arpa | 8082 |
| grocy.aftergrid.home.arpa | 8083 |
| kopia.aftergrid.home.arpa | 51515 |
| notes.aftergrid.home.arpa | 8097 |

DNS records are not created automatically. If no domain is supplied, shared application URLs use the private IP directly. Reserve that IP before generating QR labels. A separate DNS name for each application is recommended: cookies are not isolated by port. Without separate DNS names, sign out of the portal before opening applications, especially untrusted content. Use a trusted HTTPS reverse proxy for administrative and backup credentials. HTTP mode is for a trusted private LAN only; never forward ports to the internet.

## Initial access and sharing

- Homebox: sign in to AfterGrid as administrator and choose Set up native account on its card. Create one native account for the shared collection, or verify an existing account. Save its local login email and password. Then return to the card and Share on LAN; registration closes and its native hostname option is set to the chosen stable URL.
- Grocy: choose Set up native account and replace the default admin/admin password, or verify an existing native administrator account. The bounded native API flow verifies the chosen login and refuses success unless the default password is rejected. It never resets an unknown existing password. Then return to the card and Share on LAN.
- Kopia: generated native UI credentials; authenticated administrator can reveal them on the configured portal origin after acknowledging HTTP risk. Share on LAN explicitly to enable the native UI; no default passwords. The portal only hides the link for family users; Kopia itself enforces its own credentials.
- DokuWiki: open /install.php locally, enable ACLs and Closed Wiki, disable registration and popularity reporting, verify anonymous access is denied, then share. Native permissions remain the application's responsibility.
- Return to local-only recreates the selected Compose project while retaining data. Homebox registration remains closed. Kopia may always be left local-only.

A root operator on an existing development installation can set AFTERGRID_BIND to the assigned private IPv4, AFTERGRID_ORIGIN to its full portal URL, and optionally AFTERGRID_LAN_DOMAIN in /opt/aftergrid/.env, then recreate core and worker with sudo docker compose up -d. Reapply any existing shared module configuration using its Start/Share action if changing the bind/domain. Do not change the address or name after printing labels without preserving the old URL.

Native setup keeps Homebox and Grocy loopback-only until the separate Share on LAN action. The AfterGrid administrator form sends credentials only to the fixed bundled application, with no proxy, SSH tunnel or external identity service. Credentials and native session tokens are transient and never enter worker jobs, activity output or portal storage. Native sessions used for verification are logged out on completion where the application is reachable. Use HTTP only on a trusted private LAN and acknowledge its unencrypted transport in the form. Native account setup is disabled in restricted recovery mode. If a change was submitted but verification fails, use Verify existing account with the same details before retrying creation or changing a password.

## Testing

Hosted CI tests Docker bindings with a disposable private address, not real Wi-Fi clients. Physical LAN, local DNS, QR scans, HTTPS trust and native account changes still require real-host testing.
