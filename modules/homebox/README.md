# Homebox

Install using the portal, then select **Set up Homebox account** on its application card. Supply a local sign-in email and a native password of 12–128 characters. No email delivery is required. For an existing account, use its current password to verify it. AfterGrid checks native sign-in, closes registration through the supported application setting, and checks that registration is refused. The application stays local-only until you choose **Share on LAN**.

The worker generates and retains the required API-key pepper in its private state volume. Submitted account credentials are held only in a private temporary request file until the job finishes; they are not saved in job history. Check Recent activity before retrying an uncertain response. Use the configured portal address on a trusted LAN or trusted HTTPS origin for credential entry.

Use one shared collection with locations and tags for household ownership and storage. Data lives in data/homebox; removing containers retains it. See [LAN access](../../docs/LAN_ACCESS.md) for stable URLs. Actual QR label scanning and populated household journeys remain unverified. The pinned release tag is not a digest.

Managed maintenance-stop snapshots and isolated database verification are available from the portal. The worker-generated pepper is captured separately by the managed worker-state recovery snapshot; preserve that snapshot together with the application data for complete recovery.

Browser account setup is under acceptance on this branch; it has not yet been verified on the live appliance.
