# Shared notes and emergency documents

Optional official DokuWiki 2026-07-14c image. One container, no external database or identity service. Pages, revisions, media attachments, accounts, permissions and native settings persist under data/notes. PACE planning remains in the core communications page; do not duplicate its structured records.

For an existing development install, create the directory once (do not recursively change ownership of existing files):
```sh
sudo install -d -m 0700 -o 10001 -g 10001 /opt/aftergrid/data/notes
```

Install Notes from the portal, then open http://127.0.0.1:8097/install.php locally (or SSH-forward port 8097). Enable ACLs, choose Closed Wiki, create a unique administrator password, disable public registration, and uncheck popularity reporting. Choose an appropriate license for your own content. Create native accounts for household users and verify anonymous access is denied before selecting Share on LAN. The portal asks for confirmation; it does not independently enforce the native ACL configuration. The installer rejects reconfiguration after native setup. Do not expose unconfigured services on the LAN or public internet. Other containers on the shared application network are not a security boundary.

Use native wiki pages, namespaces, revision history, search and media manager for emergency procedures, appliance manuals, evacuation checklists and household instructions. Upload PDFs and other supported files only as needed. Use native namespace/page/media permissions; family profiles in AfterGrid are not DokuWiki accounts. Do not put passwords, private medical details or other sensitive records into a broadly shared namespace. No plugins, cloud accounts, SMTP service, external assets or automatic imports are configured by AfterGrid. Disable optional online features and avoid remote embeds. Use a trusted HTTPS reverse proxy or SSH tunnel for credentials; never port-forward to the internet.

Kopia should back up data/notes, including config and attachments, with the app quiesced for a consistent snapshot. Cache can be regenerated. Stop/uninstall retains the entire directory. Native setup, access control, editing, LAN bindings and persistence smoke coverage is included; full backup restoration and physical disconnected operation remain pending.

Upstream: https://github.com/dokuwiki/docker
