# Local network access (development)

AfterGrid starts loopback-only unless the operator explicitly chooses a private server IPv4. The core can be reached through an SSH tunnel for setup; no mandatory identity provider or public DNS service is needed.

## Configure once

Give the server a DHCP reservation or static address, e.g. 192.168.10.4. In the router or local DNS server, add these records pointing to that address:

| Name | Port |
|---|---|
| homebox.aftergrid.home.arpa | 8082 |
| grocy.aftergrid.home.arpa | 8083 |

These are examples, not automatically created DNS records. Use your local resolver on phones and computers. Choose a different base name under home.arpa if desired, using AFTERGRID_LAN_DOMAIN in /opt/aftergrid/.env. Keep the hostname unchanged after printing labels.

If the installer was run with AFTERGRID_BIND set to the private server IP, the worker uses that address. To keep the portal loopback-only while allowing inventory sharing, a root operator may set AFTERGRID_LAN_BIND to the assigned private server IP in /opt/aftergrid/.env and recreate only the worker. From /opt/aftergrid:

```sh
sudo docker compose up -d --no-deps worker
```

Do not set a public address or forward these ports on the router. This initial development mode uses HTTP, so credentials and inventory are not encrypted in transit. Use a trusted LAN or a locally trusted HTTPS reverse proxy. Do not reuse the portal's hostname for other applications; cookies are not isolated by port. Use SSH for the administrator portal when possible. This is not hardened for hostile local networks.

## Share Homebox and Grocy

1. Install and open locally (SSH forward the app port for a remote host).
2. Create the Homebox native account, and change Grocy's default admin/admin credentials.
3. Add the local DNS records. Confirm **Share on LAN** on the application card.
4. The worker recreates the selected Compose project with the private bind. Homebox registration is closed and its upstream hostname option is set to the LAN URL.
5. Open the link on a family device and sign in with native credentials. Generate QR labels only after verifying the final URL.

AfterGrid does not verify that native account setup was completed; the administrator explicitly confirms it. The app URL is persisted through the worker configuration. Return to local-only recreates and starts the application on loopback without reopening Homebox registration. Uninstall preserves data and sharing preferences. Kopia remains loopback-only. Kiwix uses the existing core bind behavior. QR scan, native credential changes, actual LAN/DNS and trusted HTTPS are still unverified. Recovery must preserve the worker state, server DNS and app data.

The disposable hosted CI test exercises binding changes using a private IPv4 assigned to the runner loopback interface. It inspects Docker's published addresses and Homebox environment. This is not a physical LAN, DNS, login or QR scanning acceptance test.
