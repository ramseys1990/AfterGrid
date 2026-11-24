#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
die(){ echo "AfterGrid: $*" >&2; exit 1; }
[[ $EUID == 0 ]] || die "Run with sudo."
[[ -r /etc/os-release ]] || die "Unsupported Linux host."
. /etc/os-release
[[ $ID == debian || $ID == ubuntu ]] || die "Use Debian or Ubuntu."
[[ ! -d /etc/pve ]] && ! command -v pveversion >/dev/null || die "Install inside a Linux guest, not the Proxmox hypervisor."
for cmd in curl tar od tr ip; do command -v "$cmd" >/dev/null || die "Missing prerequisite: $cmd"; done
ROOT=/opt/aftergrid
BIND=${AFTERGRID_BIND:-}
LAN_DOMAIN=${AFTERGRID_LAN_DOMAIN:-}
# Prefer the assigned source address of the default route. Never use wildcard
# or a public address. A machine without an unambiguous private route can
# explicitly supply AFTERGRID_BIND; loopback remains a safe fallback.
private_ipv4(){ [[ $1 =~ ^(10\.[0-9]+\.[0-9]+\.[0-9]+|192\.168\.[0-9]+\.[0-9]+|172\.(1[6-9]|2[0-9]|3[01])\.[0-9]+\.[0-9]+)$ ]]; }
if [[ -z $BIND ]]; then
  candidate=$(ip -4 route get 192.0.2.1 2>/dev/null | awk '{for(i=1;i<NF;i++)if($i=="src"){print $(i+1);exit}}' || true)
  if [[ -n $candidate ]] && private_ipv4 "$candidate"; then BIND=$candidate; else BIND=127.0.0.1; fi
fi
if [[ -n $LAN_DOMAIN ]]; then
  [[ $LAN_DOMAIN =~ ^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+home\.arpa$ && ${#LAN_DOMAIN} -le 200 ]] || die "Choose a lowercase local domain below home.arpa, or leave it empty."
fi
PORT=${AFTERGRID_PORT:-8080}
REF=${AFTERGRID_REF:-main}
[[ $REF =~ ^[a-zA-Z0-9._-]+$ ]] || die "Invalid source ref."
[[ $PORT =~ ^[0-9]{1,5}$ ]] && (( 10#$PORT >= 1024 && 10#$PORT <= 65535 )) || die "Invalid port."
# Explicit LAN mode accepts only a private IPv4 assigned to this machine.
if [[ $BIND != 127.0.0.1 ]]; then
  [[ $BIND =~ ^(10\.[0-9]+\.[0-9]+\.[0-9]+|192\.168\.[0-9]+\.[0-9]+|172\.(1[6-9]|2[0-9]|3[01])\.[0-9]+\.[0-9]+)$ ]] || die "Choose a private IPv4 address or loopback."
  ip -4 -o addr show | awk '{split($4,a,"/");print a[1]}' | grep -Fxq "$BIND" || die "Bind address is not assigned to this machine."
fi
[[ ! -e $ROOT ]] || die "$ROOT already exists; refusing to overwrite. Use existing Compose project to manage it."
echo "[1/4] Checking Docker"
if ! command -v docker >/dev/null; then
  # Clean hosts only; do not replace an existing engine or its configuration.
  [[ ! -e /var/lib/docker && ! -e /etc/docker ]] || die "Existing Docker state detected; install/repair Docker manually."
  apt-get update
  apt-get install -y ca-certificates curl
  install -m 0755 -d /etc/apt/keyrings
  [[ ! -e /etc/apt/keyrings/docker.asc && ! -e /etc/apt/sources.list.d/docker.sources ]] || die "Existing Docker repository configuration; install Docker manually."
  curl -fsSL "https://download.docker.com/linux/$ID/gpg" -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  printf 'Types: deb\nURIs: https://download.docker.com/linux/%s\nSuites: %s\nComponents: stable\nArchitectures: %s\nSigned-By: /etc/apt/keyrings/docker.asc\n' "$ID" "${UBUNTU_CODENAME:-${VERSION_CODENAME:?}}" "$(dpkg --print-architecture)" > /etc/apt/sources.list.d/docker.sources
  chmod 0644 /etc/apt/sources.list.d/docker.sources
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
docker compose version >/dev/null || die "Docker Compose v2 is required; install its plugin."
# Explicitly avoid remote Docker contexts before talking to the daemon.
[[ -z ${DOCKER_HOST:-} && -z ${DOCKER_CONTEXT:-} ]] || die "Unset DOCKER_HOST and DOCKER_CONTEXT; use local Docker."
[[ $(docker context show) == default ]] || die "Switch to the local default Docker context."
docker info >/dev/null || die "Docker is not running or guest does not support it."
if docker compose ls --all --format json | grep -q '"aftergrid-core"'; then die "Existing AfterGrid Compose project detected."; fi
echo "[2/4] Downloading core source"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
curl -fsSL "https://github.com/ramseys1990/AfterGrid/archive/${REF}.tar.gz" -o "$tmp/source.tar.gz"
mkdir "$tmp/source"
tar -xzf "$tmp/source.tar.gz" --strip-components=1 -C "$tmp/source"
[[ -f "$tmp/source/compose.yaml" && -f "$tmp/source/core/Dockerfile" ]] || die "Incomplete source archive."
mkdir -m 0755 "$ROOT"
cp -a "$tmp/source/." "$ROOT/"
chmod 0755 "$ROOT"
install -d -m 0700 -o 10001 -g 10001 "$ROOT/data/core"
install -d -m 0755 -o 10001 -g 10001 "$ROOT/content/kiwix"
install -d -m 0755 -o 10001 -g 10001 "$ROOT/content/maps"
install -d -m 0755 -o 10001 -g 10001 "$ROOT/content/routing"
install -m 0644 -o 10001 -g 10001 "$ROOT/modules/kiwix/library.xml" "$ROOT/content/kiwix/library.xml"
token=$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')
printf '%s\n' "$token" > "$ROOT/data/core/setup-token"
chown 10001:10001 "$ROOT/data/core/setup-token"
chmod 0600 "$ROOT/data/core/setup-token"
PORT=$((10#$PORT))
PORTAL_HOST=$BIND
if [[ -n $LAN_DOMAIN && $BIND != 127.0.0.1 ]]; then PORTAL_HOST=$LAN_DOMAIN; fi
printf 'AFTERGRID_BIND=%s\nAFTERGRID_PORT=%s\nAFTERGRID_ORIGIN=http://%s:%s\nAFTERGRID_SECURE_COOKIE=false\nAFTERGRID_LAN_DOMAIN=%s\n' "$BIND" "$PORT" "$PORTAL_HOST" "$PORT" "$LAN_DOMAIN" > "$ROOT/.env"
cd "$ROOT"
echo "[3/4] Building and starting core only"
export AFTERGRID_BIND="$BIND" AFTERGRID_PORT="$PORT" AFTERGRID_ORIGIN="http://$PORTAL_HOST:$PORT" AFTERGRID_SECURE_COOKIE=false AFTERGRID_LAN_DOMAIN="$LAN_DOMAIN"
compose=(docker compose --project-name aftergrid-core --file "$ROOT/compose.yaml" --env-file "$ROOT/.env")
"${compose[@]}" config -q
if ! "${compose[@]}" up -d --build --wait --wait-timeout 120; then
  echo "Core start failed. Inspect: sudo docker compose --project-name aftergrid-core --file $ROOT/compose.yaml --env-file $ROOT/.env logs" >&2
  echo "Setup token remains in $ROOT/data/core/setup-token (root-readable)." >&2
  exit 1
fi
echo "[4/4] Core is healthy"
echo "Open http://$PORTAL_HOST:$PORT"
if [[ $PORTAL_HOST != "$BIND" ]]; then echo "Create a local DNS record for $PORTAL_HOST pointing to $BIND before signing in."; fi
if [[ $BIND == 127.0.0.1 ]]; then
  echo "Remote browser? On your computer run: ssh -L $PORT:127.0.0.1:$PORT USER@SERVER"
  echo "Then open http://127.0.0.1:$PORT"
  echo "For Kiwix after optional installation, add: -L 8081:127.0.0.1:8081"
else
  echo "LAN access is enabled on $BIND. Reserve this address in your router."
  echo "WARNING: trusted LAN HTTP is unencrypted. Prefer a trusted HTTPS reverse proxy for credentials. Never forward these ports to the internet."
fi
echo "One-time setup token: $token"
echo "No optional modules installed. Development build; not production-ready."
