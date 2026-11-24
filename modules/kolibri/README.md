# Offline education

Optional official Kolibri 0.19.5 image. Uses the native entrypoint, first-run facility setup, local learner/coach/admin accounts, content channels, lessons and progress. No OIDC, new database service or custom education engine.

Install from AfterGrid. Initial bindings are loopback-only: main web application 8086 and separate zip-content origin 8087 (required for interactive archive-based learning activities). On a remote workstation, forward both ports over SSH and open http://127.0.0.1:8086. Complete native facility setup and create the administrator before explicitly selecting Share on LAN in AfterGrid. Use native accounts and permissions for learners. Never expose these HTTP ports to the internet. If LAN DNS is configured, add the kolibri.<local domain> DNS record as instructed in the portal.

Import content in Kolibri's native device/content management interface. Download selected channels when online or import from a USB/local content export or another supported local Kolibri server. No initial content bundle is assumed or automatically downloaded. The statistics pingback is disabled; internet-dependent content acquisition and optional sync are still explicit native workflows.

All application content, facility database, learner progress, settings and persistent node ID live under data/kolibri. AfterGrid preserves this bind mount during uninstall; include it in a quiesced Kopia backup. The official image performs its own ownership setup; don't recursively change permissions on unrelated directories. No content-import automation, full lesson acceptance or physical offline test yet. CI covers native provisioning, both port bindings and persistent node ID; results pending.

Native documentation: https://kolibri.readthedocs.io/
