# Offline media

Optional Jellyfin 12.4 official container, using its native local web interface, library scanning, playback and user permissions. Store legally obtained instructional videos, audio and household media in content/media. No automatic downloads, cloud media accounts, hardware acceleration or transcoding devices are configured. PDFs/manuals belong in the separate shared document workflow, not Jellyfin.

On existing development installs create the module directories once, without changing existing file ownership:
```sh
sudo install -d -m 0700 -o 10001 -g 10001 /opt/aftergrid/data/media/config /opt/aftergrid/data/media/cache
sudo install -d -m 0755 -o 10001 -g 10001 /opt/aftergrid/content/media
```
Copy media files into content/media, with directories traversable and files readable by UID 10001. The native app sees /media as read-only. It cannot modify original media through that mount. Data/config and cache are writable; uninstall retains both and the source media.

Install from AfterGrid. The initial setup is loopback-only on port 8096. Forward that port over SSH if necessary. Finish Jellyfin's native setup wizard, set a strong administrator password, disable remote access and configure ordinary local users and their library access. Add folders under /media as native libraries. Disable online metadata/image providers, automatic plugin downloads and internet-dependent features where appropriate; local filenames and embedded/local metadata remain usable. AfterGrid does not enforce a server egress firewall, so do not treat the settings as proof of fully disconnected operation. Select Share on LAN only after setup. HTTP is unencrypted; do not port-forward to the public internet. Native clients can use the configured LAN host and port 8096.

Prefer direct-play compatible encodings on limited hardware; software transcoding may consume considerable CPU and cache storage. No GPU or privileged container is required. Back up configuration and selected original media separately; exclude regenerable cache if desired. Native media authentication, setup, read-only mount, sharing and persistence smoke tests are added. Actual playback, content scanning, transcoding and disconnected physical LAN acceptance remain pending.

Upstream: https://jellyfin.org/docs/general/installation/container/
