"""Small, privileged Compose worker. Only reviewed manifests and fixed actions."""
import http.server
import http.cookiejar
import base64
import ipaddress
import json
import os
import re
import secrets
import socketserver
import sqlite3
import subprocess
import threading
import time
import tempfile
import urllib.request
import urllib.error
from contextlib import contextmanager
from pathlib import Path

MODULES = Path("/modules")
STATE = Path("/worker-state")
SOCKET = Path("/run/aftergrid/worker.sock")
ROUTING_ACTIONS = {"prepare-graph", "activate-graph", "rollback-graph", "archive-original", "archive-replacement"}
ACTIONS = {"install", "start", "stop", "restart", "update", "uninstall", "share", "unshare", "initialize-repository", "snapshot", "verify-snapshot"} | ROUTING_ACTIONS
ROOT = os.environ.get("AFTERGRID_ROOT", "/opt/aftergrid")
BIND = os.environ.get("AFTERGRID_BIND", "127.0.0.1")
LAN_BIND = os.environ.get("AFTERGRID_LAN_BIND") or BIND
LAN_DOMAIN = os.environ.get("AFTERGRID_LAN_DOMAIN", "")
MAX_LOG = 24000
SECRET_LOCK = threading.Lock()
REGISTRY_LOCK = threading.Lock()

def catalog():
    result = {}
    for path in sorted(MODULES.glob("*/module.yaml")):
        # JSON is valid YAML; keep the initial manifest parser dependency-free.
        item = json.loads(path.read_text())
        ident = item["id"]
        if (not re.fullmatch(r"[a-z][a-z0-9-]{0,39}", ident)
                or path.parent.name != ident or not (path.parent / "compose.yaml").is_file()):
            raise ValueError("Invalid reviewed module manifest")
        result[ident] = item
    return result

def public_module(ident, manifest):
    shared, closed = share_settings(ident) if manifest.get("lan_shareable") else (False,False)
    available = bool(manifest.get("lan_shareable") and lan_available())
    return {**manifest, "status": state(ident), "share_available": available, "shared": shared,
            "lan_url": lan_url(ident,manifest) if available else "", "registration_closed": closed, "lan_dns": bool(LAN_DOMAIN)}

def command(ident, *args):
    if ident not in catalog():
        raise ValueError("Unknown module")
    directory = MODULES / ident
    return ["docker", "compose", "--project-name", "aftergrid-" + ident,
            "--project-directory", str(directory), "--file", str(directory / "compose.yaml"), *args]

def module_secrets(ident, create=False):
    manifest = catalog()[ident]
    names = manifest.get("generated_secrets", [])
    if not names:
        return {}
    if not all(re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", name) for name in names):
        raise ValueError("Invalid reviewed secret name")
    directory = STATE / "secrets"
    path = directory / (ident + ".json")
    with SECRET_LOCK:
        if path.exists():
            values = json.loads(path.read_text())
            if set(values) != set(names) or not all(isinstance(v,str) and len(v)>=32 for v in values.values()):
                raise ValueError("Invalid persistent module secrets; repair from backup")
            return values
        if not create:
            # Compose needs nonempty interpolation values even for read-only ps.
            return dict.fromkeys(names, "not-configured-read-only-placeholder")
        directory.mkdir(mode=0o700, exist_ok=True)
        values = {name: secrets.token_hex(32) for name in names}
        tmp = directory / (ident + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(values, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
        return values

def lan_available():
    try:
        addr = ipaddress.IPv4Address(LAN_BIND)
    except ValueError:
        return False
    private = any(addr in ipaddress.IPv4Network(n) for n in ("10.0.0.0/8","172.16.0.0/12","192.168.0.0/16"))
    if not LAN_DOMAIN:
        return private
    labels = LAN_DOMAIN.split(".")
    valid = len(labels) >= 3 and labels[-2:] == ["home","arpa"] and len(LAN_DOMAIN) <= 200
    valid = valid and all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels)
    return private and valid

def share_settings(ident):
    with db() as conn:
        row = conn.execute("SELECT shared,registration_closed FROM sharing WHERE module=?", (ident,)).fetchone()
    return (bool(row["shared"]),bool(row["registration_closed"])) if row else (False,False)

def set_sharing(ident, enabled):
    with db() as conn:
        conn.execute("""INSERT INTO sharing(module,shared,registration_closed) VALUES (?,?,?)
            ON CONFLICT(module) DO UPDATE SET shared=excluded.shared,
            registration_closed=max(sharing.registration_closed,excluded.registration_closed)""",
            (ident,int(enabled),int(enabled and ident=="homebox")))

def lan_url(ident, manifest):
    host = f"{ident}.{LAN_DOMAIN}" if LAN_DOMAIN else LAN_BIND
    scheme="https" if ident=="tak" else "http"
    return f"{scheme}://{host}:{manifest['port']}"

def sharing_env(ident):
    manifest = catalog()[ident]
    if not manifest.get("lan_shareable"):
        return {}
    shared, closed = share_settings(ident)
    enabled = shared and lan_available()
    return {
        "AFTERGRID_MODULE_BIND": LAN_BIND if enabled else "127.0.0.1",
        "AFTERGRID_HOMEBOX_REGISTRATION": "false" if closed or enabled else "true",
        "AFTERGRID_MODULE_URL": lan_url(ident,manifest) if enabled else "",
        **({"AFTERGRID_TAK_LAN_IP":LAN_BIND if lan_available() else "127.0.0.1",
            "AFTERGRID_TAK_HOST":f"tak.{LAN_DOMAIN}" if lan_available() and LAN_DOMAIN else LAN_BIND if lan_available() else "localhost"} if ident=="tak" else {}),
        **({"AFTERGRID_MESHMONITOR_ORIGINS":",".join(["http://localhost:8085","http://127.0.0.1:8085"]+([lan_url(ident,manifest)] if enabled else []))} if ident=="meshmonitor" else {}),
    }

def compose_env(ident, create=False):
    return {**module_secrets(ident, create),**sharing_env(ident),"PATH": os.environ["PATH"], "HOME": "/root",
            "DOCKER_HOST": "unix:///var/run/docker.sock",
            "AFTERGRID_ROOT": ROOT, "AFTERGRID_BIND": BIND,
            "COMPOSE_PROGRESS": "plain", "NO_COLOR": "1"}

@contextmanager
def db():
    conn = sqlite3.connect(STATE / "jobs.sqlite3", timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            yield conn
    finally:
        conn.close()

def init():
    STATE.mkdir(parents=True, exist_ok=True)
    with db() as conn:
        conn.executescript("""
          CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, module TEXT NOT NULL,
            action TEXT NOT NULL, state TEXT NOT NULL, stage TEXT NOT NULL,
            completed INTEGER NOT NULL DEFAULT 0, total INTEGER NOT NULL DEFAULT 0,
            log TEXT NOT NULL DEFAULT '', created INTEGER NOT NULL);
          CREATE TABLE IF NOT EXISTS sharing (
            module TEXT PRIMARY KEY, shared INTEGER NOT NULL, registration_closed INTEGER NOT NULL);
          CREATE TABLE IF NOT EXISTS batches (
            token TEXT PRIMARY KEY, selection TEXT NOT NULL, job_ids TEXT NOT NULL);
          CREATE UNIQUE INDEX IF NOT EXISTS one_pending_per_module
            ON jobs(module) WHERE state IN ('queued','running');
        """)
        conn.execute("UPDATE jobs SET state='interrupted',stage='Worker restarted; inspect service and retry' WHERE state='running'")

def enqueue(ident, action, backup_confirmed=False):
    manifest = catalog().get(ident)
    if not manifest or action not in ACTIONS:
        raise ValueError("Unsupported module or action")
    if action in ("snapshot","verify-snapshot") and ident not in SNAPSHOT_SOURCES:
        raise ValueError("Application snapshot not yet supported")
    if action == "initialize-repository" and ident!="kopia":
        raise ValueError("Kopia-only action")
    if action == "update" and (backup_confirmed is not True or ident == "routing"):
        raise ValueError("Update requires backup confirmation and a supported module")
    if action in ROUTING_ACTIONS and ident != "routing":
        raise ValueError("Routing-only action")
    if action in {"share","unshare"} and not manifest.get("lan_shareable"):
        raise ValueError("Module does not support LAN sharing")
    if action == "share" and not lan_available():
        raise ValueError("Configure a private LAN bind (local DNS is optional)")
    with db() as conn:
        cursor = conn.execute("INSERT INTO jobs(module,action,state,stage,created) VALUES (?,?,'queued','Queued',?)",
                              (ident, action, int(time.time())))
        return cursor.lastrowid

def enqueue_batch(token, selection):
    manifests = catalog()
    if (not isinstance(token,str) or not re.fullmatch(r"[a-f0-9]{48}",token)
            or not isinstance(selection,list) or not 1 <= len(selection) <= 12
            or not all(isinstance(i,str) and i in manifests for i in selection)
            or len(set(selection)) != len(selection)):
        raise ValueError("Invalid module selection")
    # Shared module dependencies are not implemented yet. Fail closed rather
    # than silently start a future dependent module out of order.
    if any(manifests[i].get("dependencies") for i in selection):
        raise ValueError("Selected module requires dependency support")
    canonical = json.dumps(sorted(selection))
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        previous = conn.execute("SELECT selection,job_ids FROM batches WHERE token=?", (token,)).fetchone()
        if previous:
            if previous["selection"] != canonical:
                raise sqlite3.IntegrityError("Batch selection changed")
            return json.loads(previous["job_ids"])
        ids = []
        for ident in selection:
            cursor = conn.execute("INSERT INTO jobs(module,action,state,stage,created) VALUES (?,'install','queued','Queued',?)",
                                  (ident, int(time.time())))
            ids.append(cursor.lastrowid)
        conn.execute("INSERT INTO batches VALUES (?,?,?)", (token,canonical,json.dumps(ids)))
        return ids

def jobs():
    with db() as conn:
        return [dict(x) for x in conn.execute("SELECT * FROM jobs ORDER BY id DESC LIMIT 30")]

def change(job, **values):
    allowed = {"state", "stage", "completed", "total"}
    if not values or not values.keys() <= allowed:
        raise ValueError("Invalid job fields")
    with db() as conn:
        conn.execute("UPDATE jobs SET " + ",".join(k+"=?" for k in values) + " WHERE id=?",
                     (*values.values(), job))

def log(job, line):
    with db() as conn:
        conn.execute("UPDATE jobs SET log=substr(log || ?, -?) WHERE id=?",
                     (line[:4096], MAX_LOG, job))

def run(job, ident, *args):
    # Fixed argv, no shell, no arbitrary parameters from the browser.
    proc = subprocess.Popen(command(ident, *args), env=compose_env(ident, create=True),
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, errors="replace", bufsize=1)
    private_values = module_secrets(ident)
    timer = threading.Timer(1800, proc.kill)
    timer.start()
    try:
        for line in proc.stdout:
            for value in private_values.values():
                line = line.replace(value, '[redacted]')
            log(job, line)
        code = proc.wait()
        if code:
            raise RuntimeError("Compose exited with code " + str(code))
    finally:
        timer.cancel()
        proc.stdout.close()
        if proc.poll() is None:
            proc.kill()
            proc.wait()

def state(ident):
    try:
        output = subprocess.run(command(ident, "ps", "--all", "--format", "json"),
                                env=compose_env(ident), capture_output=True, text=True, timeout=8, check=True).stdout.strip()
        rows = json.loads(output) if output.startswith("[") else [json.loads(s) for s in output.splitlines() if s]
        if not rows:
            return "not installed"
        states = [r.get("State", "").lower() for r in rows]
        if all(s == "running" for s in states):
            return "running" if ready(ident) else "starting or unhealthy"
        if all(s in {"exited", "created", "dead"} for s in states):
            return "stopped"
        return "degraded"
    except (OSError, subprocess.SubprocessError, ValueError, TypeError):
        return "unavailable"

class KopiaNoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        return None

class KopiaClient:
    """Fixed native UI calls, with a private session and no forwarded error bodies."""
    def __init__(self):
        if not (STATE/"secrets"/"kopia.json").is_file():
            raise RuntimeError("Install Kopia first")
        self.secrets=module_secrets("kopia")
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),KopiaNoRedirect())
        self.headers={"Authorization":"Basic "+base64.b64encode(("aftergrid:"+self.secrets["KOPIA_UI_PASSWORD"]).encode()).decode()}
        try:
            html=self.read("/")
            match=re.search(rb'<meta name="kopia-csrf-token" content="([a-f0-9]{64})"\s*/?>',html)
            if not match:raise ValueError("Missing native session")
            self.headers["X-Kopia-Csrf-Token"]=match.group(1).decode()
        except (OSError,ValueError):
            raise RuntimeError("Native Kopia session unavailable") from None

    def read(self,path,body=None):
        if path not in ("/","/api/v1/repo/status","/api/v1/repo/create"):
            raise ValueError("Unsupported native request")
        headers={**self.headers,"Accept":"application/json"}
        if body is not None:headers["Content-Type"]="application/json"
        req=urllib.request.Request("http://aftergrid-kopia:51515"+path,
            data=None if body is None else json.dumps(body).encode(),headers=headers)
        with self.opener.open(req,timeout=25 if body is not None else 5) as response:
            data=response.read(1024*1024+1)
            if len(data)>1024*1024:raise ValueError("Oversized native response")
            return data

    def status(self):
        try:
            value=json.loads(self.read("/api/v1/repo/status"))
            if not isinstance(value,dict) or type(value.get("connected")) is not bool:
                raise ValueError("Unexpected native status")
            connected=value["connected"]
            storage=value.get("storage")
            return {"connection":"connected" if connected else "initializing" if value.get("initTaskID") else "not connected",
                    "storage_type":storage if connected and isinstance(storage,str) and re.fullmatch(r"[a-zA-Z0-9_-]{1,40}",storage) else None,
                    "snapshot_verified":False}
        except (OSError,ValueError):
            raise RuntimeError("Native Kopia repository status unavailable") from None

    def create_local(self):
        try:
            self.read("/api/v1/repo/create",{"storage":{"type":"filesystem","config":{"path":"/repository"}},
                      "password":self.secrets["KOPIA_PASSWORD"],"options":{}})
        except (OSError,ValueError):
            raise RuntimeError("Native creation failed or timed out; inspect Kopia before retrying") from None

def kopia_status():
    try:
        return KopiaClient().status()
    except (RuntimeError,ValueError,OSError):
        return {"connection":"unavailable","storage_type":None,"snapshot_verified":False}

def initialize_repository(job):
    change(job,state="running",total=3,completed=0,stage="Check native repository status")
    client=KopiaClient()
    if client.status()["connection"]!="not connected":
        raise RuntimeError("Repository is connected or initializing; refusing creation")
    change(job,completed=1,stage="Require empty repository directory")
    # Fixed command in the reviewed Kopia container. Never accept a host path.
    try:
        subprocess.run(command("kopia","exec","-T","kopia","/bin/sh","-c",
            'test -d /repository && test ! -L /repository && first=$(find /repository -mindepth 1 -maxdepth 1 -print -quit) && test -z "$first"'),
            env=compose_env("kopia"),capture_output=True,text=True,timeout=8,check=True)
    except (OSError,subprocess.SubprocessError,ValueError):
        raise RuntimeError("Repository directory is not empty or could not be checked; connect existing storage in Kopia") from None
    if client.status()["connection"]!="not connected":
        raise RuntimeError("Repository state changed; refusing creation")
    change(job,completed=2,stage="Create encrypted repository using native Kopia")
    client.create_local()
    result=client.status()
    if result["connection"]!="connected" or result["storage_type"]!="filesystem":
        raise RuntimeError("Creation outcome unconfirmed; inspect native Kopia before retrying")
    change(job,completed=3,state="succeeded",stage="Repository connected; snapshots not verified")

# Initial reviewed application with one persistent data directory.
SNAPSHOT_SOURCES={"grocy":"/source/data/grocy"}

def cleanly_stopped(ident):
    try:
        output=subprocess.run(command(ident,"ps","--all","--format","json"),env=compose_env(ident),
                              capture_output=True,text=True,timeout=8,check=True).stdout.strip()
        rows=json.loads(output) if output.startswith("[") else [json.loads(line) for line in output.splitlines() if line]
        return bool(rows) and all(r.get("State","").lower()=="exited" and type(r.get("ExitCode")) is int and r["ExitCode"]==0 for r in rows)
    except (OSError,subprocess.SubprocessError,ValueError,TypeError):
        return False

def native_snapshot(ident):
    source=SNAPSHOT_SOURCES[ident]
    try:
        subprocess.run(command("kopia","exec","-T","kopia","/bin/sh","-c",
            'test -d "$1" && test ! -L "$1"',"check-source",source),
            env=compose_env("kopia"),capture_output=True,text=True,timeout=8,check=True)
        raw=subprocess.run(command("kopia","exec","-T","kopia","timeout","--kill-after=10s","300s",
            "/bin/kopia","snapshot","create","--json","--fail-fast","--force-disable-actions","--no-send-snapshot-report",source),
            env=compose_env("kopia"),capture_output=True,text=True,timeout=330,check=True).stdout
        if len(raw)>1024*1024:raise ValueError("Oversized snapshot response")
        value=json.loads(raw)
        stats=value["stats"]
        if (value.get("incomplete") or value["source"]["path"]!=source
                or not re.fullmatch(r"[a-f0-9]{32,64}",value["id"])
                or not value["rootEntry"].get("obj")
                or any(type(stats.get(k)) is not int or stats[k]!=0 for k in
                       ("errorCount","ignoredErrorCount","excludedFileCount","excludedDirCount"))
                or type(stats.get("fileCount")) is not int or stats["fileCount"]<1):
            raise ValueError("Incomplete, excluded or empty snapshot")
        return value["id"]
    except (OSError,subprocess.SubprocessError,ValueError,KeyError,TypeError):
        raise RuntimeError("Snapshot not confirmed complete; inspect native Kopia (partial snapshots may remain)") from None

def snapshot_application(job,ident):
    if ident not in SNAPSHOT_SOURCES:raise ValueError("Unsupported snapshot application")
    change(job,state="running",total=4,completed=0,stage="Check repository and application")
    if kopia_status()["connection"]!="connected":raise RuntimeError("Connect Kopia repository first")
    original=state(ident)
    if original not in ("running","stopped"):raise RuntimeError("Application must be installed and healthy or stopped")
    change(job,completed=1,stage="Quiesce application")
    restart=original=="running"
    try:
        if restart:run(job,ident,"stop","--timeout","60")
        if not cleanly_stopped(ident):raise RuntimeError("Clean application shutdown not confirmed; snapshot refused")
        change(job,completed=2,stage="Create native Kopia snapshot")
        snapshot_id=native_snapshot(ident)
        if not cleanly_stopped(ident):raise RuntimeError("Application state changed during snapshot; consistency unconfirmed")
        log(job,"\nNative snapshot reported complete: "+snapshot_id+"; restore not verified.\n")
        change(job,completed=3)
    finally:
        if restart:
            change(job,stage="Restore prior running state")
            try:
                run(job,ident,"start")
                wait_ready(ident)
                log(job,"\nApplication running again.\n")
            except Exception:
                raise RuntimeError("Application restart not confirmed; inspect and start manually") from None
    change(job,completed=4,state="succeeded",stage="Snapshot reported complete; restore not verified")

def latest_managed_snapshot(ident):
    with db() as conn:
        row=conn.execute("SELECT id,log FROM jobs WHERE module=? AND action='snapshot' AND state='succeeded' ORDER BY id DESC LIMIT 1",(ident,)).fetchone()
    if not row:raise RuntimeError("No successful managed snapshot recorded")
    match=re.search(r"Native snapshot reported complete: ([a-f0-9]{32,64});",row["log"])
    if not match:raise RuntimeError("Managed snapshot ID unavailable")
    return match.group(1)

def restore_manifest(ident,snapshot_id):
    source=SNAPSHOT_SOURCES[ident]
    try:
        raw=subprocess.run(command("kopia","exec","-T","kopia","timeout","30s","/bin/kopia",
            "snapshot","list","--json","--manifest-id","--max-results=50",source),
            env=compose_env("kopia"),capture_output=True,text=True,timeout=40,check=True).stdout
        if len(raw)>4*1024*1024:raise ValueError("Oversized snapshot list")
        rows=json.loads(raw)
        matches=[row for row in rows if row.get("id")==snapshot_id and row.get("source",{}).get("path")==source]
        if len(matches)!=1:raise ValueError("Snapshot missing or ambiguous")
        row=matches[0]
        stats=row["stats"]
        root=row["rootEntry"]["obj"]
        if (row.get("incomplete") or not re.fullmatch(r"[IZD]{0,8}[a-z]?[a-f0-9]{32,128}",root)
                or any(type(stats.get(k)) is not int or stats[k]!=0 for k in
                       ("errorCount","ignoredErrorCount","excludedFileCount","excludedDirCount"))
                or type(stats.get("totalSize")) is not int or not 0<stats["totalSize"]<=512*1024*1024):
            raise ValueError("Snapshot incomplete or exceeds 512 MiB verification limit")
        return root
    except (OSError,subprocess.SubprocessError,ValueError,KeyError,TypeError):
        raise RuntimeError("Managed snapshot missing, invalid or exceeds isolated restore limit") from None

def check_restored_grocy(data):
    if not isinstance(data,bytes) or not 0<len(data)<=64*1024*1024 or not data.startswith(b"SQLite format 3\x00"):
        raise RuntimeError("Restored database missing, invalid or exceeds verification limit")
    try:
        with tempfile.TemporaryDirectory(prefix="aftergrid-db-check-") as tmp:
            path=Path(tmp)/"grocy.db"
            path.write_bytes(data)
            deadline=time.monotonic()+15
            conn=sqlite3.connect(path.as_uri()+"?mode=ro&immutable=1",uri=True)
            try:
                conn.execute("PRAGMA trusted_schema=OFF")
                conn.set_progress_handler(lambda: int(time.monotonic()>deadline),10000)
                if conn.execute("PRAGMA integrity_check").fetchmany(2)!=[("ok",)]:
                    raise RuntimeError("Restored database integrity check failed")
                tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('products','users')")}
                if tables!={"products","users"}:
                    raise RuntimeError("Expected Grocy schema missing")
            finally:conn.close()
    except (OSError,sqlite3.Error):
        raise RuntimeError("Restored database integrity check unavailable") from None

def verify_snapshot(job,ident):
    if ident!="grocy":raise ValueError("Unsupported restore verification")
    change(job,state="running",total=4,completed=0,stage="Locate latest managed snapshot")
    if kopia_status()["connection"]!="connected":raise RuntimeError("Connect Kopia repository first")
    snapshot_id=latest_managed_snapshot(ident)
    root=restore_manifest(ident,snapshot_id)
    # Each verification gets a new private directory, never a live data mount.
    target="/restore/aftergrid-grocy-"+str(job)+"-"+secrets.token_hex(8)
    env=compose_env("kopia")
    def execute(*args,timeout=20):
        return subprocess.run(command("kopia","exec","-T","kopia",*args),env=env,
                              capture_output=True,timeout=timeout,check=True).stdout
    change(job,completed=1,stage="Prepare private restore directory")
    try:
        execute("/bin/sh","-c",'test -d /restore && test ! -L /restore && umask 077 && mkdir "$1"',"restore-target",target)
        log(job,"\nIsolated restore directory: "+target+"\n")
        change(job,completed=2,stage="Restore managed snapshot into isolated storage")
        execute("timeout","--kill-after=10s","300s","/bin/kopia","restore","--no-overwrite-files",
                "--no-overwrite-symlinks","--no-ignore-permission-errors",root,target+"/data",timeout=330)
        change(job,completed=3,stage="Verify restored Grocy SQLite database")
        # Reject symlink traversal, active journals and oversized databases.
        data=execute("/bin/sh","-c",
            'p="$1/data/data"; f="$p/grocy.db"; test -d "$1" && test ! -L "$1" && test -d "$1/data" && test ! -L "$1/data" && test -d "$p" && test ! -L "$p" && test -f "$f" && test ! -L "$f" && test ! -e "$f-wal" && test ! -L "$f-wal" && test ! -e "$f-journal" && test ! -L "$f-journal" && size=$(stat -c %s "$f") && test "$size" -le 67108864 && cat "$f"',
            "check-database",target,timeout=30)
        check_restored_grocy(data)
    except (OSError,subprocess.SubprocessError,ValueError):
        raise RuntimeError("Isolated restore or database read failed; inspect private restore directory") from None
    log(job,"\nSnapshot "+snapshot_id+" restored; SQLite integrity and expected schema passed. Native application startup not tested.\n")
    change(job,completed=4,state="succeeded",stage="Isolated restore and SQLite check passed")

def backup_sources(config, root):
    """Classify normalized Compose mounts; no host directory traversal."""
    result=[]
    root=Path(root)
    for service,definition in sorted(config["services"].items()):
        for mount in definition.get("volumes",[]):
            if not isinstance(mount,dict):
                raise ValueError("Expected normalized Compose mounts")
            kind=mount.get("type")
            source=mount.get("source")
            target=mount.get("target","")
            relative=None
            if kind=="bind" and isinstance(source,str):
                path=Path(source)
                if path.is_absolute() and ".." not in path.parts and path.is_relative_to(root):
                    relative=path.relative_to(root)
            kopia_path=None
            if relative and relative.parts[0] in ("data","content","modules") and len(relative.parts)>1:
                if relative.parts[:2]==("data","kopia"):
                    role="excluded"
                elif relative.parts[:3]==("data","media","cache"):
                    role="regenerable cache"
                elif relative.parts[0]=="modules":
                    role="reviewed configuration"
                else:
                    role="application data" if relative.parts[0]=="data" else "offline content"
                if role not in ("excluded","regenerable cache"):
                    kopia_path="/source/"+relative.as_posix()
            else:
                role="outside backup source mounts"
            result.append({"service":service,"container_path":target,"role":role,"kopia_path":kopia_path,
                           "read_only":bool(mount.get("read_only",False))})
    return result

BACKUP_GUIDANCE={
    "homebox":"Stop Homebox or use a validated native database export; preserve its worker-generated API-key pepper.",
    "grocy":"Stop Grocy before snapshotting its database and configuration.",
    "kiwix":"Finish core downloads, index changes and removals before snapshotting archives and the library index.",
    "maps":"Finish regional downloads and file changes before snapshotting map content.",
    "routing":"Finish downloads, graph builds, switches and archives; stop routing before snapshotting the complete routing directory.",
    "meshmonitor":"Stop MeshMonitor before snapshotting data; preserve its worker-generated credentials and session secret.",
    "tak":"Stop MicroTAK before capturing database, backups and CA/private-key material; protect the encrypted repository.",
    "kolibri":"Stop Kolibri and finish imports before capturing facility databases and learning content.",
    "media":"Stop Jellyfin before snapshotting configuration; finish media imports; cache is regenerable.",
    "notes":"Stop DokuWiki or prevent all edits before snapshotting documents, ACLs and accounts.",
    "kopia":"Do not snapshot the active repository or Kopia's working directories into itself; retain repository credentials and independent repository recovery instructions."
}

def backup_plan(ident):
    manifest=catalog().get(ident)
    if not manifest:raise ValueError("Unknown module")
    try:
        raw=subprocess.run(command(ident,"config","--format","json"),env=compose_env(ident),
                           capture_output=True,text=True,timeout=8,check=True).stdout
        sources=backup_sources(json.loads(raw),ROOT)
    except (OSError,subprocess.SubprocessError,ValueError,KeyError,TypeError):
        raise RuntimeError("Reviewed backup sources unavailable") from None
    if ident=="kopia":
        # Repository, restore destinations and working directories are not
        # backup sources, even if a future mount is added below /source.
        sources=[{**source,"role":"excluded from self-backup","kopia_path":None} for source in sources]
    return {"module":ident,"sources":sources,"guidance":BACKUP_GUIDANCE.get(ident,"Establish an application-consistent backup procedure before scheduling."),
            "worker_secrets_required":bool(manifest.get("generated_secrets")),
            "coverage":"planned only","snapshot_verified":False}

def version_report(ident):
    """Local Docker evidence only: no registry lookup, secrets or environment returned."""
    if ident not in catalog():
        raise ValueError("Unknown module")
    env=compose_env(ident)
    def read(argv):
        return subprocess.run(argv,env=env,capture_output=True,text=True,timeout=4,check=True).stdout.strip()
    try:
        config=json.loads(read(command(ident,"config","--format","json")))
        services=config["services"]
        output=read(command(ident,"ps","--all","--format","json"))
        rows=json.loads(output) if output.startswith("[") else [json.loads(line) for line in output.splitlines() if line]
        result=[]
        for service,definition in sorted(services.items()):
            target=definition.get("image")
            if not isinstance(target,str) or not target:
                raise ValueError("Expected reviewed image reference")
            # Container IDs originate from this module's Compose project, not the request.
            selected=[r for r in rows if r.get("Service")==service and str(r.get("OneOff",False)).lower()!="true"]
            ids=[r["ID"] for r in selected]
            if any(not re.fullmatch(r"[a-f0-9]{12,64}",i) for i in ids):
                raise ValueError("Invalid container ID")
            installed=[]
            if ids:
                lines=read(["docker","container","inspect","--format","{{json .Image}}",*ids]).splitlines()
                installed=sorted(set(json.loads(line) for line in lines))
                if not installed or any(not re.fullmatch(r"sha256:[a-f0-9]{64}",i) for i in installed):
                    raise ValueError("Unexpected installed image ID")
            try:
                local=json.loads(read(["docker","image","inspect","--format","{{json .Id}}",target]))
                if not re.fullmatch(r"sha256:[a-f0-9]{64}",local):raise ValueError("Unexpected local image ID")
            except subprocess.CalledProcessError:
                local=None
            status=("not installed" if not installed else "target not present locally" if local is None
                    else "matches local target" if installed==[local] else "differs from local target")
            result.append({"service":service,"configured_image":target,"installed_image_ids":installed,
                           "local_target_image_id":local,"comparison":status})
    except (OSError,subprocess.SubprocessError,ValueError,KeyError,TypeError):
        raise RuntimeError("Local Docker image information unavailable") from None
    with db() as conn:
        history=[dict(r) for r in conn.execute("SELECT id,state,stage,created FROM jobs WHERE module=? AND action='update' ORDER BY id DESC LIMIT 10",(ident,))]
    return {"module":ident,"services":result,"registry_checked":False,"manual_update_supported":ident!="routing","history":history}

def registry_config_digest(target, platform, read):
    """Resolve a reviewed reference to one image config, never a layer pull."""
    digest_pattern=r"sha256:[a-f0-9]{64}"
    def manifest(ref):
        raw=read(["docker","buildx","imagetools","inspect","--raw",ref])
        if len(raw)>2_000_000:
            raise ValueError("Oversized registry manifest")
        value=json.loads(raw)
        if not isinstance(value,dict) or value.get("schemaVersion")!=2:
            raise ValueError("Unsupported registry manifest")
        return value
    value=manifest(target)
    selected=None
    if "manifests" in value:
        if not isinstance(value["manifests"],list) or len(value["manifests"])>1000:
            raise ValueError("Unsupported registry index")
        os_name,arch=platform.split("/")
        candidates={entry["digest"] for entry in value["manifests"]
                    if isinstance(entry,dict) and isinstance(entry.get("platform"),dict)
                    and entry["platform"].get("os")==os_name
                    and entry["platform"].get("architecture")==arch
                    and isinstance(entry.get("digest"),str) and re.fullmatch(digest_pattern,entry["digest"])}
        if len(candidates)!=1:
            raise ValueError("Registry platform is missing or ambiguous")
        selected=candidates.pop()
        # Remove the tag/digest, retaining any registry hostname and port.
        repository=target.split("@",1)[0]
        if ":" in repository.rsplit("/",1)[-1]:
            repository=repository.rsplit(":",1)[0]
        value=manifest(repository+"@"+selected)
    config=value.get("config")
    if not isinstance(config,dict) or not isinstance(config.get("digest"),str) or not re.fullmatch(digest_pattern,config["digest"]):
        raise ValueError("Registry image config digest unavailable")
    if config.get("mediaType") not in ("application/vnd.oci.image.config.v1+json","application/vnd.docker.container.image.v1+json"):
        raise ValueError("Registry manifest is not a runnable image")
    return config["digest"],selected

def registry_report(ident):
    if not REGISTRY_LOCK.acquire(blocking=False):
        raise RuntimeError("Another registry check is running; try again later")
    try:
        local=version_report(ident)
        if len(local["services"])!=1:
            raise RuntimeError("Registry check currently supports single-service modules")
        service=local["services"][0]
        target=service["configured_image"]
        result={"module":ident,"configured_image":target,"digest_pinned":"@" in target,
                "checked_at":int(time.time()),"registry_config_digest":None,
                "platform_manifest_digest":None,"platform":None,
                "installed_image_ids":service["installed_image_ids"],"comparison":"unavailable"}
        env=compose_env(ident)
        def read(argv):
            return subprocess.run(argv,env=env,capture_output=True,text=True,timeout=6,check=True).stdout.strip()
        try:
            platform=read(["docker","version","--format","{{.Server.Os}}/{{.Server.Arch}}"])
            if not re.fullmatch(r"[a-z0-9]+/[a-z0-9_]+",platform):
                raise ValueError("Unsupported Docker platform")
            result["platform"]=platform
            digest,selected=registry_config_digest(target,platform,read)
            result["registry_config_digest"]=digest
            result["platform_manifest_digest"]=selected
            installed=result["installed_image_ids"]
            result["comparison"]=("not installed" if not installed else "matches configured registry image" if installed==[digest]
                                  else "differs from configured registry image")
        except (OSError,subprocess.SubprocessError,ValueError,KeyError,TypeError):
            result["detail"]="Registry metadata unavailable, unsupported or ambiguous; no update conclusion"
        return result
    finally:
        REGISTRY_LOCK.release()

def ready(ident):
    url = catalog()[ident].get("readiness_url")
    if not url:
        return True
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            return 200 <= response.status < 400
    except urllib.error.HTTPError as exc:
        return exc.code in catalog()[ident].get('readiness_statuses', [])
    except (OSError, ValueError):
        return False

def wait_ready(ident):
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        if state(ident) == "running":
            return
        time.sleep(2)
    raise RuntimeError("Application did not become ready; inspect logs and retry")

def stages(action):
    validate = ("Validate Compose", ("config", "-q"))
    pull = ("Download images", ("pull",))
    up = ("Start containers", ("up", "-d", "--wait", "--wait-timeout", "90", "--pull", "never"))
    probe = ("Check application readiness", None)
    return {
        "install": [validate, pull, up, probe],
        "update": [validate, pull, up, probe],
        "start": [validate, up, probe],
        "restart": [validate, ("Restart containers", ("restart",)), probe],
        "stop": [validate, ("Stop containers", ("stop",))],
        "uninstall": [validate, ("Remove containers (retain data)", ("down",))],
        "share": [validate, up, probe],
        "unshare": [validate, up, probe],
    }[action]

def routing_command(script,*args):
    return ("run","--rm","--no-deps","-T","--pull","never","--entrypoint","/bin/sh","routing","/aftergrid/"+script,*args)

def routing_steps(action):
    validate=("Validate Compose",("config","-q"))
    if action=="prepare-graph":
        return [validate,("Build separate replacement graph",routing_command("build.sh","candidate"))]
    if action in {"archive-original","archive-replacement"}:
        target="tiles" if action=="archive-original" else "tiles-next"
        return [validate,("Archive inactive graph and source",routing_command("archive.sh",target))]
    target="tiles-next" if action=="activate-graph" else "tiles"
    return [validate,("Check both graph slots",routing_command("switch.sh","check",target)),
            ("Stop routing",("stop",)),("Select prepared graph",routing_command("switch.sh","select",target)),
            ("Start selected graph",("up","-d","--wait","--wait-timeout","90","--pull","never")),
            ("Check routing readiness",None)]

def execute(row):
    job, ident, action = row["id"], row["module"], row["action"]
    switch_attempted=False
    try:
        if ident not in catalog() or action not in ACTIONS or (action in ROUTING_ACTIONS and ident!="routing"):
            raise ValueError("Unsupported job")
        if action=="snapshot":
            snapshot_application(job,ident)
            return
        if action=="verify-snapshot":
            verify_snapshot(job,ident)
            return
        if action=="initialize-repository":
            if ident!="kopia":raise ValueError("Kopia-only action")
            initialize_repository(job)
            return
        if action=="update" and (ident=="routing" or state(ident)!="running"):
            raise ValueError("Manual update requires a running supported module; routing upgrades need a separate graph migration")
        if action in {"activate-graph","rollback-graph","archive-original","archive-replacement"} and state(ident)!="running":
            raise ValueError("Start the currently selected routing graph before switching")
        steps = routing_steps(action) if action in ROUTING_ACTIONS else stages(action)
        if ident == "routing" and action in {"install","update"}:
            steps.insert(2, ("Prepare regional routing graph", ("run", "--rm", "--no-deps", "-T", "--entrypoint", "/bin/sh", "routing", "/aftergrid/build.sh")))
        change(job, state="running", total=len(steps), completed=0)
        if action in {"share","unshare"}:
            if not catalog()[ident].get("lan_shareable"):
                raise ValueError("Module does not support LAN sharing")
            if action == "share" and (not lan_available() or state(ident) != "running"):
                raise RuntimeError("Start the module and complete native account setup before sharing")
            if action == "unshare" and state(ident) in {"not installed","unavailable"}:
                raise RuntimeError("Module is not installed or Docker state unavailable")
            set_sharing(ident, action=="share")
        for index, (title, argv) in enumerate(steps):
            change(job, stage=title)
            log(job, "\n--- " + title + " ---\n")
            if title=="Stop routing" and action in {"activate-graph","rollback-graph"}:
                switch_attempted=True
            if argv is None:
                wait_ready(ident)
            else:
                run(job, ident, *argv)
            change(job, completed=index+1)
        change(job, state="succeeded", stage="Complete")
    except Exception as exc:
        if switch_attempted and action in {"activate-graph","rollback-graph"}:
            previous="tiles" if action=="activate-graph" else "tiles-next"
            try:
                log(job,"\nGraph switch failed; restoring previous selection.\n")
                run(job,ident,"stop")
                run(job,ident,*routing_command("switch.sh","select",previous))
                run(job,ident,"up","-d","--wait","--wait-timeout","90","--pull","never")
                wait_ready(ident)
                log(job,"Previous graph ready again. Both graphs retained.\n")
            except Exception as recovery:
                log(job,"Automatic restoration failed; both graph slots retained. Inspect selector and restart manually: "+str(recovery)+"\n")
        if action in {"share","unshare"}:
            set_sharing(ident,False)
            try:
                run(job,ident,"stop")
                log(job,"\nLAN change failed; containers stopped. Start locally to retry.\n")
            except Exception:
                log(job,"\nCould not confirm containers stopped; inspect Docker immediately.\n")
        log(job, "\n" + str(exc) + "\n")
        change(job, state="failed", stage="Failed; see output")

def process():
    while True:
        with db() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE state='queued' ORDER BY id LIMIT 1").fetchone()
        if row:
            execute(row)
        else:
            time.sleep(0.5)

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def send_json(self, status, value):
        body = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            return self.send_json(200, {"ok": True})
        if self.path == "/modules":
            return self.send_json(200, [public_module(i,m) for i,m in catalog().items()])
        if self.path == "/jobs":
            return self.send_json(200, jobs())
        if self.path=="/kopia/status":
            return self.send_json(200,kopia_status())
        if self.path.startswith("/backup-plan/"):
            ident=self.path.removeprefix("/backup-plan/")
            if ident not in catalog():return self.send_json(404,{"detail":"Unknown module"})
            try:return self.send_json(200,backup_plan(ident))
            except RuntimeError:return self.send_json(503,{"detail":"Reviewed backup sources unavailable"})
        if self.path.startswith("/versions/"):
            ident=self.path.removeprefix("/versions/")
            if ident not in catalog():return self.send_json(404,{"detail":"Unknown module"})
            try:return self.send_json(200,version_report(ident))
            except RuntimeError:return self.send_json(503,{"detail":"Local Docker image information unavailable"})
        if self.path == "/credentials/meshmonitor" and "meshmonitor" in catalog():
            if not (STATE / "secrets" / "meshmonitor.json").is_file():
                return self.send_json(404, {"detail":"Install MeshMonitor first"})
            values=module_secrets("meshmonitor")
            return self.send_json(200,{"username":"admin","initial_password":values["MESHMONITOR_ADMIN_PASSWORD"]})
        if self.path == "/credentials/kopia" and "kopia" in catalog():
            if not (STATE / "secrets" / "kopia.json").is_file():
                return self.send_json(404, {"detail": "Install Kopia first"})
            values = module_secrets("kopia")
            return self.send_json(200, {"username": "aftergrid", "ui_password": values["KOPIA_UI_PASSWORD"], "repository_password": values["KOPIA_PASSWORD"]})
        self.send_json(404, {"detail": "Unknown endpoint"})

    def do_POST(self):
        if self.path not in {"/jobs", "/jobs/batch", "/registry-check"}:
            return self.send_json(404, {"detail": "Unknown endpoint"})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 2048:
                raise ValueError("Invalid request length")
            body = json.loads(self.rfile.read(size))
            if self.path == "/registry-check":
                if not isinstance(body,dict) or set(body)!={"module"} or not isinstance(body["module"],str) or body["module"] not in catalog():
                    raise ValueError("Unsupported module")
                try:return self.send_json(200,registry_report(body["module"]))
                except RuntimeError as exc:return self.send_json(503,{"detail":str(exc)})
            if self.path == "/jobs/batch":
                if not isinstance(body,dict) or set(body) != {"token","modules"}:
                    raise ValueError("Invalid batch")
                return self.send_json(202, {"ids": enqueue_batch(body["token"],body["modules"])})
            if not isinstance(body,dict) or not isinstance(body.get("module"),str) or not isinstance(body.get("action"),str):
                raise ValueError("Invalid request")
            if body["action"]=="update":
                if set(body)!={"module","action","backup_confirmed"} or body["backup_confirmed"] is not True:
                    raise ValueError("Explicit backup confirmation required")
            elif set(body)!={"module","action"}:
                raise ValueError("Invalid request")
            job = enqueue(body["module"],body["action"],body.get("backup_confirmed",False))
            self.send_json(202, {"id": job})
        except sqlite3.IntegrityError:
            self.send_json(409, {"detail": "A job is already pending for this module"})
        except (ValueError, TypeError):
            self.send_json(400, {"detail": "Unsupported module or action"})

class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True

if __name__ == "__main__":
    init()
    SOCKET.parent.mkdir(exist_ok=True)
    os.chown(SOCKET.parent, 0, 10001)
    os.chmod(SOCKET.parent, 0o750)
    SOCKET.unlink(missing_ok=True)
    with Server(str(SOCKET), Handler) as server:
        os.chown(SOCKET, 0, 10001)
        os.chmod(SOCKET, 0o660)
        threading.Thread(target=process, daemon=True).start()
        server.serve_forever()
