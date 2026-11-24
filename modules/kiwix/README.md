# Kiwix

Official upstream image, pinned to a multi-architecture release. AfterGrid installs only the reader, with an initially empty library. No reference content is downloaded automatically. The browser content manager is a separate milestone. For now an administrator can place licensed ZIM files and a corresponding Kiwix library.xml in /opt/aftergrid/content/kiwix and restart the reader. Keep paths within /data and files readable by the container. Do not overwrite the existing library on upgrades.

Default local URL: http://127.0.0.1:8081. Remote loopback access requires an additional SSH port forward. Explicit trusted-LAN mode binds the same private IP as the portal. The reader is shared, not authenticated.

Lifecycle uses standard Compose. Uninstall removes containers, not content. Empty-library and real-ZIM runtime behavior require validation.

The portal now supports queued downloads for official catalog entries with supported HTTPS archive paths and SHA-256 Metalink metadata. Transfers use curl and indexing uses kiwix-manage. The reader is configured to monitor library.xml. Existing installations need the content directory writable by UID 10001. Live transfer, native indexing, and disconnected reading of a downloaded archive remain unverified. Do not remove a partial or archive during a running job.
