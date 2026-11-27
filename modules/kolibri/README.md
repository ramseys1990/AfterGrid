# Offline education

Optional official Kolibri 0.19.5 image. Uses native facility setup, learner/coach/admin accounts, content channels, lessons and progress. No OIDC, separate database service or custom education engine.

Install from AfterGrid, then select **Set up native account**. Both native ports stay local-only during setup: main web application 8086 and the separate zip-content origin 8087 used by interactive activities. Create the device administrator in the private browser form. This provisions one AfterGrid learning facility with guest reading, password-required learners and self-registration disabled. Automatic, learner-requested and metered-connection downloads are disabled; administrators import content explicitly. Save the native credentials before sharing. After an interrupted attempt, choose Verify existing account with the same credentials; the form never resets an unknown password.

Setup uses the pinned version's native provisioning/session APIs and CSRF cookies. Kolibri temporarily stores the credential in its native provisioning task. AfterGrid verifies administrator login, clears only the completed provisioning queue associated with that account/facility, checks that cleanup finished, and logs out its temporary session. Unknown or active setup tasks keep setup unsuccessful and the app private. AfterGrid does not store the password or place it in its own worker jobs or logs. These native APIs outside the public namespace are version-specific; upgrades require lifecycle acceptance against the new pinned image.

After successful setup, explicitly select **Share on LAN** in AfterGrid. Use native accounts for learner progress and administration; guests can read imported content without creating an account. Review permissions in Kolibri. Never expose these HTTP ports to the internet. If LAN DNS is configured, add the local Kolibri DNS record as instructed in the portal.

Import content in Kolibri's native device/content manager. Download selected channels when online or import from a USB/local export or another supported local Kolibri server. No initial content bundle is assumed or downloaded automatically. Statistics pingback is disabled; content acquisition and optional sync remain explicit native workflows.

Content, facility database, progress, settings and persistent node ID live under data/kolibri. Uninstall preserves this bind mount; include it in a quiesced Kopia backup. The official image performs its own ownership setup. Do not change permissions on unrelated directories. Native HTTP setup, both port bindings, lifecycle and managed restore are covered by the disposable smoke test; the earlier browser-setup revision passed the full native lifecycle run. The additional explicit-download default is covered by focused tests; its full native lifecycle rerun is pending. Imported lessons, interactive zip-content playback and physical offline operation remain unverified.

Native documentation: https://kolibri.readthedocs.io/

