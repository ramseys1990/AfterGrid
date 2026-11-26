#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
die(){ echo "AfterGrid: $*" >&2; exit 1; }
check_port(){
  local port=$1 listeners
  listeners=$(ss -H -ltn "sport = :$port") || die "Cannot inspect local TCP listeners."
  [[ -z $listeners ]] || die "TCP port $port already has a listener. Choose AFTERGRID_PORT."
}
check_docker_environment(){
  [[ -z ${DOCKER_HOST:-} && -z ${DOCKER_CONTEXT:-} ]] || die "Unset DOCKER_HOST and DOCKER_CONTEXT; use local Docker."
}
check_local_docker(){
  local endpoint context projects networks volumes ports
  check_docker_environment
  context=$(docker context show) || die "Cannot inspect Docker context."
  [[ $context == default ]] || die "Switch to the local default Docker context."
  endpoint=$(docker context inspect default --format '{{.Endpoints.docker.Host}}') || die "Cannot inspect Docker endpoint."
  [[ $endpoint == unix:///var/run/docker.sock || $endpoint == unix:///run/docker.sock ]] || die "Default Docker endpoint must be the local system socket."
  docker info >/dev/null || die "Docker is not running or guest does not support it."
  docker compose version >/dev/null || die "Docker Compose v2 is required; install its plugin."
  if [[ ${2:-fresh} == resume ]]; then return; fi
  projects=$(docker ps -a --format '{{.Label "com.docker.compose.project"}}') || die "Cannot inspect Docker containers."
  networks=$(docker network ls --format '{{.Name}}') || die "Cannot inspect Docker networks."
  volumes=$(docker volume ls --format '{{.Name}}') || die "Cannot inspect Docker volumes."
  if printf '%s\n' "$projects" "$networks" "$volumes" | grep -Eq '^aftergrid([-_]|$)'; then
    die "Existing AfterGrid Docker resources detected; nothing was removed."
  fi
  ports=$(docker ps --format '{{.Ports}}') || die "Cannot inspect published Docker ports."
  if grep -Eq ":$1->" <<<"$ports"; then die "Docker already publishes host port $1. Choose AFTERGRID_PORT."; fi
}
# A fresh install publishes this root-owned marker before any Compose
# startup. Resume never downloads, extracts, initializes or rewrites data.
validate_pending_install(){
  local root=$1
  [[ -d $root && ! -L $root && -O $root ]] || die "Invalid installation root."
  [[ -f $root/.install-pending && ! -L $root/.install-pending && -O $root/.install-pending ]] || die "No unfinished initial installation marker."
  [[ $(stat -c '%a' "$root/.install-pending") == 600 ]] || die "Invalid installation marker permissions."
  for file in .env compose.yaml; do
    [[ -f $root/$file && ! -L $root/$file && -O $root/$file ]] || die "Invalid staged configuration."
  done
  local actual expected
  actual=$(cd "$root" && sha256sum .env compose.yaml)
  expected=$(cat "$root/.install-pending")
  [[ $actual == "$expected" ]] || die "Staged configuration changed; inspect manually."
  [[ -f $root/data/core/setup-token && ! -L $root/data/core/setup-token ]] || die "Setup token is no longer present; use normal Compose management."
  [[ $(stat -c '%a' "$root/data/core/setup-token") == 600 ]] || die "Invalid setup token permissions."
  [[ $(cat "$root/data/core/setup-token") =~ ^[a-f0-9]{64}$ ]] || die "Invalid setup token."
}
resume_resources(){
  local root=$1 port=$2 rows project service folder config cid core_found=false
  rows=$(docker ps -a --format '{{.ID}}|{{.Label "com.docker.compose.project"}}|{{.Label "com.docker.compose.service"}}|{{.Label "com.docker.compose.project.working_dir"}}|{{.Label "com.docker.compose.project.config_files"}}') || die "Cannot inspect containers."
  while IFS='|' read -r cid project service folder config; do
    [[ $project == aftergrid || $project == aftergrid-* || $project == aftergrid_* ]] || continue
    [[ $project == aftergrid-core && $folder == "$root" && $config == "$root/compose.yaml" && ( $service == core || $service == worker ) ]] || die "Unexpected AfterGrid container; inspect manually."
    if [[ $service == core ]]; then core_found=true; fi
  done <<<"$rows"
  local ports publications
  # docker ps does not support a negative label filter. Read each running
  # container's project and ports, then exclude only the validated core project.
  ports=$(docker ps --format '{{.Label "com.docker.compose.project"}}|{{.Ports}}') || die "Cannot inspect Docker ports."
  while IFS='|' read -r project publications; do
    [[ $project == aftergrid-core ]] && continue
    if grep -Eq ":$port->" <<<"$publications"; then die "Another Docker workload publishes portal port $port."; fi
  done <<<"$ports"
  # Existing core may already own the listener; Compose remains the final
  # binding authority. Never stop a conflicting unrelated process.
  if ! $core_found; then check_port "$port"; fi
}
start_core(){
  local root=$1
  cd "$root"
  export AFTERGRID_ROOT="$root"
  # Avoid caller-specific settings overriding the preserved installation.
  unset AFTERGRID_BIND AFTERGRID_PORT AFTERGRID_ORIGIN AFTERGRID_SECURE_COOKIE AFTERGRID_LAN_DOMAIN AFTERGRID_LAN_BIND
  local -a compose=(docker compose --project-name aftergrid-core --project-directory "$root" --file "$root/compose.yaml" --env-file "$root/.env")
  echo "[3/4] Building and starting core only"
  "${compose[@]}" config -q
  if ! "${compose[@]}" up -d --build --wait --wait-timeout 120; then
    echo "Core start failed. Inspect: sudo docker compose --project-name aftergrid-core --file $root/compose.yaml --env-file $root/.env logs" >&2
    echo "After correcting the problem, run sudo bash $root/install.sh --resume. Existing setup token and data are preserved." >&2
    exit 1
  fi
  rm -- "$root/.install-pending"
  echo "[4/4] Core is healthy"
}
resume_install(){
  local root=/opt/aftergrid port origin
  [[ $EUID == 0 ]] || die "Run with sudo."
  [[ ! -d /etc/pve ]] && ! command -v pveversion >/dev/null || die "Install inside a Linux guest, not the Proxmox hypervisor."
  exec 9>/run/lock/aftergrid-install.lock
  flock -n 9 || die "Another AfterGrid installer is running."
  validate_pending_install "$root"
  port=$(sed -n 's/^AFTERGRID_PORT=//p' "$root/.env")
  origin=$(sed -n 's/^AFTERGRID_ORIGIN=//p' "$root/.env")
  [[ $port =~ ^[0-9]{4,5}$ ]] && (( 10#$port >= 1024 && 10#$port <= 65535 )) || die "Invalid preserved port."
  [[ $origin =~ ^http://[a-z0-9.-]+:[0-9]+$ ]] || die "Invalid preserved origin."
  check_local_docker "$port" resume
  resume_resources "$root" "$port"
  start_core "$root"
  echo "Open $origin"
  echo "Retrieve your original one-time setup token with: sudo cat $root/data/core/setup-token"
}

main(){
local check_only=false
(( $# <= 1 )) || die "Usage: install.sh [--check|--resume]"
case ${1:-} in
  "") ;;
  --check) check_only=true ;;
  --resume) resume_install; return ;;
  *) die "Usage: install.sh [--check|--resume]" ;;
esac
[[ $EUID == 0 ]] || die "Run with sudo."
[[ -r /etc/os-release ]] || die "Unsupported Linux host."
. /etc/os-release
[[ $ID == debian || $ID == ubuntu ]] || die "Use Debian or Ubuntu."
[[ ! -d /etc/pve ]] && ! command -v pveversion >/dev/null || die "Install inside a Linux guest, not the Proxmox hypervisor."
for cmd in curl tar od tr ip ss awk grep flock sha256sum stat sed; do command -v "$cmd" >/dev/null || die "Missing prerequisite: $cmd"; done
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
[[ ! -e $ROOT && ! -L $ROOT ]] || die "$ROOT already exists; refusing to overwrite. Use existing Compose project to manage it."
PORT=$((10#$PORT))
check_docker_environment
check_port "$PORT"
if $check_only; then
  if command -v docker >/dev/null; then
    check_local_docker "$PORT"
    echo "Preflight passed: existing local Docker; no AfterGrid resource or portal port conflict detected."
  else
    [[ ! -e /var/lib/docker && ! -e /etc/docker && ! -e /etc/apt/keyrings/docker.asc && ! -e /etc/apt/sources.list.d/docker.sources ]] || die "Existing Docker state or repository configuration; inspect manually."
    echo "Preflight passed: Docker not installed; initial installation requires internet and package installation."
  fi
  echo "Selected bind: $BIND:$PORT. No installation changes made."
  return
fi
exec 9>/run/lock/aftergrid-install.lock
flock -n 9 || die "Another AfterGrid installer is running."
[[ ! -e $ROOT && ! -L $ROOT ]] || die "Installation root already exists."
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
check_local_docker "$PORT"
check_port "$PORT"
echo "[2/4] Downloading core source"
tmp=$(mktemp -d /opt/.aftergrid-stage.XXXXXXXX)
trap 'rm -rf -- "$tmp"' EXIT
curl -fsSL "https://github.com/ramseys1990/AfterGrid/archive/${REF}.tar.gz" -o "$tmp/source.tar.gz"
mkdir "$tmp/source"
tar --no-same-owner -xzf "$tmp/source.tar.gz" --strip-components=1 -C "$tmp/source"
[[ -f "$tmp/source/compose.yaml" && -f "$tmp/source/core/Dockerfile" ]] || die "Incomplete source archive."
destination=$ROOT
ROOT="$tmp/source"
chmod 0755 "$ROOT"
install -d -m 0700 -o 10001 -g 10001 "$ROOT/data/core"
install -d -m 0700 -o 10001 -g 10001 "$ROOT/data/tak/data" "$ROOT/data/tak/backup"
install -d -m 0755 -o 10001 -g 10001 "$ROOT/content/kiwix"
install -d -m 0755 -o 10001 -g 10001 "$ROOT/content/maps"
install -d -m 0755 -o 10001 -g 10001 "$ROOT/content/routing"
install -d -m 0700 -o 10001 -g 10001 "$ROOT/data/media/config" "$ROOT/data/media/cache"
install -d -m 0755 -o 10001 -g 10001 "$ROOT/content/media"
install -d -m 0700 -o 10001 -g 10001 "$ROOT/data/notes"
install -m 0644 -o 10001 -g 10001 "$ROOT/modules/kiwix/library.xml" "$ROOT/content/kiwix/library.xml"
token=$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')
printf '%s\n' "$token" > "$ROOT/data/core/setup-token"
chown 10001:10001 "$ROOT/data/core/setup-token"
chmod 0600 "$ROOT/data/core/setup-token"
PORT=$((10#$PORT))
PORTAL_HOST=$BIND
if [[ -n $LAN_DOMAIN && $BIND != 127.0.0.1 ]]; then PORTAL_HOST=$LAN_DOMAIN; fi
printf 'AFTERGRID_BIND=%s\nAFTERGRID_PORT=%s\nAFTERGRID_ORIGIN=http://%s:%s\nAFTERGRID_SECURE_COOKIE=false\nAFTERGRID_LAN_DOMAIN=%s\n' "$BIND" "$PORT" "$PORTAL_HOST" "$PORT" "$LAN_DOMAIN" > "$ROOT/.env"
(cd "$ROOT" && sha256sum .env compose.yaml > .install-pending)
chmod 0600 "$ROOT/.install-pending"
# Publish only a fully staged tree, including existing setup token and env.
# The rename is on the same filesystem and refuses an existing destination.
mv -T --no-clobber "$ROOT" "$destination"
[[ ! -e $ROOT ]] || die "Installation root appeared during staging; refusing overwrite."
ROOT=$destination
start_core "$ROOT"
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

}
if [[ ${BASH_SOURCE[0]} == "$0" ]]; then main "$@"; fi
