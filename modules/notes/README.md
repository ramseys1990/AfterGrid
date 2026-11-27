# Shared notes and emergency documents

Optional official DokuWiki 2026-07-14c image. One container, no external database or identity service. Pages, revisions, media attachments, accounts, permissions and native settings persist under data/notes. PACE planning remains in the core communications page; do not duplicate its structured records.

For an existing development install, create the directory once (do not recursively change ownership of existing files):
```sh
sudo install -d -m 0700 -o 10001 -g 10001 /opt/aftergrid/data/notes
```

Install Notes from the portal, then choose **Set up native account**. Create a native administrator while port 8097 stays local-only. AfterGrid submits the native installer with ACLs enabled, Closed Wiki, no public registration, no popularity reporting and no publishing license. A local placeholder email is used; no mail service is configured. It verifies administrator access, preserves native configuration while disabling online update checks, reads back the closed policy and independently checks anonymous access refusal. It never resets an unknown password or reruns an already-configured installer. Verify existing account reads its policies without changing configuration. After successful setup, explicitly select **Share on LAN**. Add household users and review native page/media permissions inside DokuWiki. If first setup was interrupted, verify the existing credentials before retrying; exceptional native repair remains an advanced recovery operation.

Use native wiki pages, namespaces, revision history, search and media manager for emergency procedures, appliance manuals, evacuation checklists and household instructions. Upload PDFs and other supported files only as needed. Use native namespace/page/media permissions; family profiles in AfterGrid are not DokuWiki accounts. Do not put passwords, private medical details or other sensitive records into a broadly shared namespace. No plugins, cloud accounts, SMTP service, external assets or automatic imports are configured by AfterGrid. Disable optional online features and avoid remote embeds. Use credentials only on a trusted private LAN; never port-forward this service to the internet.

Kopia should back up data/notes, including config and attachments, with the app quiesced for a consistent snapshot. Cache can be regenerated. Stop/uninstall retains the entire directory. The private portal setup path passed 258 Linux regression tests and the full native lifecycle in run 46080883319 on c0acce27a5ce49f2b84e4f3372805c7e90510f74. Native editing, anonymous-access refusal, managed snapshot/restore comparison, LAN sharing and retained state passed in the disposable fixture. Physical disconnected document use remains unverified.

Upstream: https://github.com/dokuwiki/docker

Managed snapshots and isolated configuration/ACL/account/page checks are available from the portal. No live files are replaced. The full lifecycle uses the portal setup endpoint before native editing and permission checks; that updated run passed. Live guest account setup, managed snapshot/isolated checks and approved LAN anonymous-access refusal also passed; authenticated live LAN editing and populated restored startup remain separate acceptance work.
