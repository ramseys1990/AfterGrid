#!/bin/sh
set -eu
umask 077
# Only worker-validated private IP and optional local DNS name are supplied.
# Reject TOML metacharacters even for manually invoked Compose.
ip=$AFTERGRID_TAK_LAN_IP
host=$AFTERGRID_TAK_HOST
case "$ip" in ''|*[!0-9.]*) exit 1;; esac
case "$host" in ''|*[!a-zA-Z0-9.-]*) exit 1;; esac
cat > "$MICROTAK_CONFIG" <<EOF
bind_host = "0.0.0.0"
server_common_name = "aftergrid-tak"
ca_common_name = "AfterGrid TAK CA"
server_names = ["localhost", "127.0.0.1", "$ip", "$host", "aftergrid-tak"]
plain_tcp_enabled = false
enrollment_mode = "auto"
admin_common_name = "admin"
data_dir = "/var/lib/microtak-server/data"
backup_dir = "/var/lib/microtak-server/backup"
backup_enabled = false
datafeeds_admin_only = true
metrics_port = 9090
EOF
exec /usr/bin/tini -- /usr/local/bin/microtakd
