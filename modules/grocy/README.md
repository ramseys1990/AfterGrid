# Grocy

Install from the portal, then select **Secure Grocy administrator** on its application card. Supply the current native administrator password (admin on a fresh installation) and a different new password of 12–128 characters. AfterGrid uses Grocy's native authenticated API, verifies the new sign-in and checks that the old password is refused. Existing accounts are not reset. The application stays local-only until you choose **Share on LAN**.

Submitted account credentials are held only in a private temporary request file until the job finishes; they are not saved in job history. Check Recent activity before retrying an uncertain response. Use the configured portal address on a trusted LAN or trusted HTTPS origin for credential entry. Keep the new password for native Grocy sign-in.

Use storage locations for each household and shared supplies, with native stock, recipes and expiration tracking. Data lives in data/grocy; removing containers preserves it. No cross-module inventory sync or household mapping is provided. See [LAN access](../../docs/LAN_ACCESS.md) for explicit sharing.

Browser account setup is under acceptance on this branch; live password change and populated stock/recipe journeys remain unverified.
