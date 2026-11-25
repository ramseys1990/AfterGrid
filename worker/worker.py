"""Small, privileged Compose worker. Only reviewed manifests and fixed actions."""
import http.server
import http.cookiejar
import base64
import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import shutil
import tarfile
import socketserver
import sqlite3
import stat
import subprocess
import threading
import time
import tempfile
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from pathlib import Path

MODULES = Path("/modules")
STATE = Path("/worker-state")
SOCKET = Path("/run/aftergrid/worker.sock")
ROUTING_ACTIONS = {"prepare-graph", "activate-graph", "rollback-graph", "archive-original", "archive-replacement"}
ACTIONS = {"install", "start", "stop", "restart", "update", "uninstall", "share", "unshare", "initialize-repository", "snapshot", "verify-snapshot", "core-snapshot", "core-verify-snapshot", "worker-snapshot", "worker-verify-snapshot", "content-snapshot", "content-verify", "recovery-manifest"} | ROUTING_ACTIONS
ROOT = os.environ.get("AFTERGRID_ROOT", "/opt/aftergrid")
BIND = os.environ.get("AFTERGRID_BIND", "127.0.0.1")
LAN_BIND = os.environ.get("AFTERGRID_LAN_BIND") or BIND
LAN_DOMAIN = os.environ.get("AFTERGRID_LAN_DOMAIN", "")
RECOVERY_CORE_ONLY = os.environ.get("AFTERGRID_RECOVERY_CORE_ONLY") == "1"
RECOVERY_OFFLINE = os.environ.get("AFTERGRID_RECOVERY_OFFLINE") == "1"
OFFLINE_ACTIONS={"start","stop","restart","uninstall","share","unshare"}
OFFLINE_BACKUP_ACTIONS={"snapshot","verify-snapshot","content-snapshot","content-verify","core-snapshot","core-verify-snapshot","worker-snapshot","worker-verify-snapshot","recovery-manifest"}
MAX_LOG = 24000
RECOVERY_PIN = "aftergrid-recovery"
RETENTION_FLAGS={"keepLatest":"--keep-latest","keepHourly":"--keep-hourly","keepDaily":"--keep-daily",
                 "keepWeekly":"--keep-weekly","keepMonthly":"--keep-monthly","keepAnnual":"--keep-annual"}
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

def offline_mapping(ident):
    """Accept only the fixed, host-prepared service mapping, never arbitrary Compose."""
    if ident not in catalog():raise ValueError("Unknown module")
    folder=STATE/"offline-images"
    if not stat.S_ISDIR(folder.lstat().st_mode):raise ValueError("Offline image policy unavailable")
    path=folder/"mapping.json"
    if not stat.S_ISREG(path.lstat().st_mode) or not 0<path.stat().st_size<=65536:
        raise ValueError("Offline image policy invalid")
    mapping=json.loads(path.read_text())
    row=mapping.get(ident)
    if not isinstance(row,dict) or set(row)!={"image_id","recovery_tag"}:
        raise ValueError("Module is not available in offline recovery")
    image_id=row["image_id"]
    if not isinstance(image_id,str) or not re.fullmatch(r"sha256:[a-f0-9]{64}",image_id):
        raise ValueError("Invalid offline image ID")
    tag="aftergrid-recovery/aftergrid-"+ident+"-"+ident+":"+image_id.removeprefix("sha256:")
    if row["recovery_tag"]!=tag:raise ValueError("Invalid offline image tag")
    override=folder/(ident+".json")
    if not stat.S_ISREG(override.lstat().st_mode) or not 0<override.stat().st_size<=4096:
        raise ValueError("Offline Compose override invalid")
    if json.loads(override.read_text())!={"services":{ident:{"image":tag,"pull_policy":"never"}}}:
        raise ValueError("Unexpected offline Compose override")
    return row,override

def offline_admission(ident,action):
    if action not in OFFLINE_ACTIONS|OFFLINE_BACKUP_ACTIONS:raise ValueError("Action unavailable in offline recovery")
    try:
        row,_=offline_mapping(ident)
        if action in OFFLINE_BACKUP_ACTIONS:
            marker=STATE/"offline-kopia-writable.json"
            if not stat.S_ISREG(marker.lstat().st_mode) or marker.stat().st_size>4096 or json.loads(marker.read_text())!={"format":1,"repository":"/repository"}:
                raise ValueError("Writable backup opt-in required")
            kopia,_=offline_mapping("kopia")
            raw=subprocess.run(["docker","image","inspect","--format","{{json .Id}}",kopia["recovery_tag"]],
                               env=compose_env("kopia"),capture_output=True,text=True,timeout=8,check=True).stdout
            if json.loads(raw)!=kopia["image_id"]:raise ValueError("Offline Kopia image changed")
            raw=subprocess.run(command("kopia","exec","-T","kopia","/bin/kopia","repository","status","--json"),
                               env=compose_env("kopia"),capture_output=True,text=True,timeout=15,check=True).stdout
            status=json.loads(raw)
            if status["clientOptions"].get("readonly",False) is not False or status["storage"]["type"]!="filesystem" or status["storage"].get("config",{}).get("path")!="/repository":
                raise ValueError("Native writable repository not confirmed")
        if catalog()[ident].get("generated_secrets"):
            path=STATE/"secrets"/(ident+".json")
            if not stat.S_ISREG(path.lstat().st_mode):raise ValueError("Recovered credentials missing")
            module_secrets(ident)
        raw=subprocess.run(["docker","image","inspect","--format","{{json .Id}}",row["recovery_tag"]],
                           env=compose_env(ident),capture_output=True,text=True,timeout=8,check=True).stdout
        if json.loads(raw)!=row["image_id"]:raise ValueError("Offline image changed")
    except (OSError,subprocess.SubprocessError,ValueError,TypeError,AttributeError,KeyError):
        raise ValueError("Offline image, writable repository or recovered credentials unavailable") from None

def rollback_tag(image_id):
    if not isinstance(image_id,str) or not re.fullmatch(r"sha256:[a-f0-9]{64}",image_id):
        raise ValueError("Invalid rollback image ID")
    return "aftergrid-recovery/kiwix:"+image_id.split(":")[1]


def kiwix_rollback_override():
    """Only the fixed, private, exact-ID reader override is accepted."""
    path=STATE/"kiwix-rollback.json"
    if not path.exists() and not path.is_symlink():return None
    info=path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_mode&0o077 or not 0<info.st_size<=4096:
        raise ValueError("Invalid Kiwix rollback override")
    value=json.loads(path.read_text())
    try:tag=value["services"]["kiwix"]["image"]
    except (KeyError,TypeError):raise ValueError("Invalid Kiwix rollback override") from None
    if (not isinstance(tag,str) or not re.fullmatch(r"aftergrid-recovery/kiwix:[a-f0-9]{64}",tag)
        or value!={"services":{"kiwix":{"image":tag,"pull_policy":"never"}}}):
        raise ValueError("Invalid Kiwix rollback override")
    return path,"sha256:"+tag.rsplit(":",1)[1],tag


def exact_local_image(ref,image_id):
    try:
        raw=subprocess.run(["docker","image","inspect","--format","{{json .Id}}",ref],
                           capture_output=True,text=True,timeout=8,check=True).stdout
        if json.loads(raw)!=image_id:raise ValueError("Image identity mismatch")
    except (OSError,ValueError,TypeError,subprocess.SubprocessError):
        raise RuntimeError("Exact local image identity unavailable") from None


def command(ident, *args):
    if ident not in catalog():
        raise ValueError("Unknown module")
    directory = MODULES / ident
    cmd=["docker", "compose", "--project-name", "aftergrid-" + ident,
            "--project-directory", str(directory), "--file", str(directory / "compose.yaml")]
    if RECOVERY_OFFLINE:
        try:_,override=offline_mapping(ident)
        except (OSError,ValueError,TypeError,AttributeError):raise ValueError("Offline module image unavailable") from None
        cmd.extend(("--file",str(override)))
        if args and args[0] in {"pull","build"}:raise ValueError("Offline recovery forbids image downloads and builds")
        if args and args[0]=="up":args=(*args,"--no-build")
    elif ident=="kiwix":
        hold=kiwix_rollback_override()
        if hold:
            override,image_id,tag=hold
            cmd.extend(("--file",str(override)))
            if args and args[0] in {"pull","build","restart"}:
                raise ValueError("Reader rollback hold; use Start to recover the exact local reader")
            if args and args[0]=="up":
                exact_local_image(tag,image_id)
                if "--pull" not in args or args[args.index("--pull")+1]!="never":
                    raise ValueError("Rollback hold requires no pull")
                if "--no-build" not in args:args=(*args,"--no-build")
    return [*cmd,*args]

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
          CREATE TABLE IF NOT EXISTS protected_snapshots (job INTEGER PRIMARY KEY);
          CREATE TABLE IF NOT EXISTS update_preparations (job INTEGER PRIMARY KEY, request TEXT NOT NULL, evidence TEXT);
          CREATE TABLE IF NOT EXISTS retention_requests (job INTEGER PRIMARY KEY, request TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS exact_verifications (
            job INTEGER PRIMARY KEY, source_job INTEGER NOT NULL);
          CREATE UNIQUE INDEX IF NOT EXISTS one_pending_per_module
            ON jobs(module) WHERE state IN ('queued','running');
        """)
        conn.execute("UPDATE jobs SET state='interrupted',stage='Worker restarted; inspect service and retry' WHERE state='running'")

def unresolved_guarded_update(conn,exclude=0):
    row=conn.execute("SELECT j.id,j.state,p.evidence FROM jobs j LEFT JOIN update_preparations p ON p.job=j.id WHERE j.module='kiwix' AND j.action='guarded-update' AND j.id!=? ORDER BY j.id DESC LIMIT 1",(exclude,)).fetchone()
    if not row or row["state"] not in {"failed","interrupted"}:return False
    try:
        evidence=json.loads(row["evidence"] or "{}")
        resolution=evidence.get("resolution_job")
        if type(resolution) is not int or resolution<=row["id"]:return True
        resolved=conn.execute("SELECT j.state,p.request FROM jobs j JOIN update_preparations p ON p.job=j.id WHERE j.id=? AND j.module='kiwix' AND j.action='resolve-rollback'",(resolution,)).fetchone()
        return not (resolved and resolved["state"]=="succeeded" and json.loads(resolved["request"])=={"failed_job":row["id"],"image_id":evidence["previous_image_id"]})
    except (ValueError,TypeError,KeyError,AttributeError):return True


def kiwix_lifecycle_admission(ident,action):
    if ident!="kiwix" or RECOVERY_OFFLINE or action not in {"install","update","start","restart"}:return
    hold=kiwix_rollback_override()
    if hold and action!="start":raise ValueError("Reader rollback hold; inspect recovery evidence")
    if hold:return
    with db() as conn:
        blocked=unresolved_guarded_update(conn)
    if blocked:
        raise ValueError("Unresolved guarded reader update; inspect recovery evidence before lifecycle changes")


def enqueue(ident, action, backup_confirmed=False, source_job=None, protect=False):
    if RECOVERY_CORE_ONLY:raise ValueError("Core-only recovery disables module actions")
    if RECOVERY_OFFLINE:offline_admission(ident,action)
    kiwix_lifecycle_admission(ident,action)
    manifest = catalog().get(ident)
    if not manifest or action not in ACTIONS:
        raise ValueError("Unsupported module or action")
    if action in ("content-snapshot","content-verify") and ident not in CONTENT_SOURCES:
        raise ValueError("Unsupported content snapshot source")
    if action in ("snapshot","verify-snapshot") and ident not in SNAPSHOT_SOURCES:
        raise ValueError("Application snapshot not yet supported")
    if action in ("initialize-repository","core-snapshot","core-verify-snapshot","worker-snapshot","worker-verify-snapshot","recovery-manifest") and ident!="kopia":
        raise ValueError("Kopia-only action")
    if action == "update" and (backup_confirmed is not True or ident == "routing"):
        raise ValueError("Update requires backup confirmation and a supported module")
    if action in ROUTING_ACTIONS and ident != "routing":
        raise ValueError("Routing-only action")
    if action in {"share","unshare"} and not manifest.get("lan_shareable"):
        raise ValueError("Module does not support LAN sharing")
    if action == "share" and not lan_available():
        raise ValueError("Configure a private LAN bind (local DNS is optional)")
    if type(protect) is not bool or (protect and (RECOVERY_OFFLINE or ident=="tak" or source_job is not None
            or action not in {"snapshot","core-snapshot","worker-snapshot","content-snapshot"})):
        raise ValueError("Unsupported protected snapshot")
    with db() as conn:
        if source_job is not None:
            source_action={"verify-snapshot":"snapshot","core-verify-snapshot":"core-snapshot",
                           "worker-verify-snapshot":"worker-snapshot","content-verify":"content-snapshot"}.get(action)
            if type(source_job) is not int or source_job<=0 or not source_action or ident=="tak" or RECOVERY_OFFLINE:
                raise ValueError("Unsupported exact verification")
            # Claim and validate within the same database transaction as enqueue.
            conn.execute("BEGIN IMMEDIATE")
            source=conn.execute("SELECT module,action,state FROM jobs WHERE id=?",(source_job,)).fetchone()
            if not source or (source["module"],source["action"],source["state"])!=(ident,source_action,"succeeded"):
                raise ValueError("Exact successful source job required")
        cursor = conn.execute("INSERT INTO jobs(module,action,state,stage,created) VALUES (?,?,'queued','Queued',?)",
                              (ident, action, int(time.time())))
        if source_job is not None:
            conn.execute("INSERT INTO exact_verifications(job,source_job) VALUES (?,?)",(cursor.lastrowid,source_job))
        if protect:conn.execute("INSERT INTO protected_snapshots(job) VALUES (?)",(cursor.lastrowid,))
        return cursor.lastrowid

def enqueue_batch(token, selection):
    if RECOVERY_OFFLINE:raise ValueError("Offline recovery disables new installations")
    if RECOVERY_CORE_ONLY:raise ValueError("Core-only recovery disables module actions")
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
    for ident in selection:kiwix_lifecycle_admission(ident,"install")
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
    proc = subprocess.Popen(command(ident, *args), env=compose_env(ident, create=not RECOVERY_OFFLINE),
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
SNAPSHOT_SOURCES={"grocy":"/source/data/grocy","homebox":"/source/data/homebox","notes":"/source/data/notes","meshmonitor":"/source/data/meshmonitor","tak":"/source/data/tak","kolibri":"/source/data/kolibri","media":"/source/data/media/config"}

def cleanly_stopped(ident):
    try:
        output=subprocess.run(command(ident,"ps","--all","--format","json"),env=compose_env(ident),
                              capture_output=True,text=True,timeout=8,check=True).stdout.strip()
        rows=json.loads(output) if output.startswith("[") else [json.loads(line) for line in output.splitlines() if line]
        return bool(rows) and all(r.get("State","").lower()=="exited" and type(r.get("ExitCode")) is int and r["ExitCode"]==0 for r in rows)
    except (OSError,subprocess.SubprocessError,ValueError,TypeError):
        return False

def log_shutdown_evidence(job,ident):
    """Report only bounded exit states; never dump native configuration or logs."""
    try:
        raw=subprocess.run(command(ident,"ps","--all","--format","json"),env=compose_env(ident),
                           capture_output=True,text=True,timeout=8,check=True).stdout.strip()
        rows=json.loads(raw) if raw.startswith("[") else [json.loads(line) for line in raw.splitlines() if line]
        if not isinstance(rows,list) or not 0<len(rows)<=16:raise ValueError("Invalid shutdown evidence")
        for row in rows:
            state=row.get("State")
            code=row.get("ExitCode")
            if state not in {"running","exited","created","dead","restarting","paused","removing"} or type(code) is not int or not 0<=code<=255:
                raise ValueError("Invalid shutdown state")
            log(job,"\nShutdown evidence: "+state+", exit code "+str(code)+".\n")
    except (OSError,subprocess.SubprocessError,ValueError,TypeError,AttributeError):
        log(job,"\nShutdown evidence unavailable.\n")

def snapshot_statistics(value,source):
    """Require verbose native evidence; never infer missing counters are zero."""
    if not isinstance(value,dict) or not isinstance(value.get("stats"),dict):
        raise RuntimeError("Kopia manifest omitted required snapshot statistics")
    if value.get("incomplete"):
        raise RuntimeError("Kopia reported an incomplete snapshot")
    if not isinstance(value.get("source"),dict) or value["source"].get("path")!=source:
        raise RuntimeError("Kopia snapshot source did not match")
    if not isinstance(value.get("id"),str) or not re.fullmatch(r"[a-f0-9]{32,64}",value["id"]):
        raise RuntimeError("Kopia snapshot ID missing or invalid")
    if not isinstance(value.get("rootEntry"),dict) or not value["rootEntry"].get("obj"):
        raise RuntimeError("Kopia snapshot root missing")
    stats=value["stats"]
    for key in ("errorCount","ignoredErrorCount","excludedFileCount","excludedDirCount"):
        count=stats.get(key)
        if type(count) is not int or count<0:
            raise RuntimeError("Kopia snapshot counter unavailable: "+key)
        if count:
            raise RuntimeError("Kopia snapshot reports "+key+"="+str(count)+"; completeness not confirmed")
    # Kopia 0.23.1 generation stats count newly processed files separately
    # from cached entries. The root directory summary is the logical snapshot
    # inventory and the basis of native verify's expectedTotalFileCount.
    if type(stats.get("fileCount")) is not int or stats["fileCount"]<0:
        raise RuntimeError("Kopia snapshot generation file count unavailable")
    summary=value["rootEntry"].get("summ")
    if not isinstance(summary,dict):
        raise RuntimeError("Kopia snapshot directory summary unavailable")
    if summary.get("incomplete"):
        raise RuntimeError("Kopia reported an incomplete directory summary")
    for key,count in (("numFailed",summary.get("numFailed")),
                      ("numIgnoredErrors",summary.get("numIgnoredErrors",0))):
        # numIgnoredErrors is omitted by Kopia when zero; numFailed is mandatory.
        if type(count) is not int or count!=0:
            raise RuntimeError("Kopia directory summary error counter invalid: "+key)
    count,size=summary.get("files"),summary.get("size")
    if type(count) is not int or count<1 or type(size) is not int or size<0:
        raise RuntimeError("Kopia snapshot is empty or directory summary unavailable")
    if stats["fileCount"]>count:
        raise RuntimeError("Kopia snapshot generation count exceeds directory summary")
    return {**stats,"fileCount":count,"totalSize":size}

def native_snapshot(ident,protect=False):
    return native_snapshot_source(SNAPSHOT_SOURCES[ident],**({"protect":True} if protect else {}))

def native_snapshot_source(source,seconds=300,protect=False):
    if type(protect) is not bool:raise ValueError("Invalid protection request")
    if protect and source not in {v for k,v in backup_policy_sources().items() if k!="global"}:
        raise ValueError("Unsupported protected source")
    try:
        subprocess.run(command("kopia","exec","-T","kopia","/bin/sh","-c",
            'test -d "$1" && test ! -L "$1"',"check-source",source),
            env=compose_env("kopia"),capture_output=True,text=True,timeout=8,check=True)
    except (OSError,subprocess.SubprocessError,ValueError):
        raise RuntimeError("Reviewed source directory unavailable in Kopia") from None
    try:
        raw=subprocess.run(command("kopia","exec","-T","kopia","timeout","--kill-after=10s",str(seconds)+"s",
            "/bin/kopia","snapshot","create","--json","--json-verbose","--fail-fast","--force-disable-actions","--no-send-snapshot-report",*(("--pin",RECOVERY_PIN) if protect else ()),source),
            env=compose_env("kopia"),capture_output=True,text=True,timeout=seconds+30,check=True).stdout
    except subprocess.TimeoutExpired:
        raise RuntimeError("Native Kopia snapshot timed out; inspect native tasks before retrying") from None
    except subprocess.CalledProcessError as exc:
        raise RuntimeError("Native Kopia snapshot exited with code "+str(exc.returncode)+"; inspect native logs") from None
    except OSError:
        raise RuntimeError("Native Kopia snapshot command unavailable") from None
    try:
        if len(raw)>1024*1024:raise ValueError("Oversized response")
        value=json.loads(raw)
    except (ValueError,TypeError):
        raise RuntimeError("Native Kopia snapshot JSON missing or invalid") from None
    snapshot_statistics(value,source)
    if protect:
        # Never pin an old manifest after capture: Kopia may change its ID.
        # Require both creation output and an independent native readback.
        if RECOVERY_PIN not in (value.get("pins") or []):raise RuntimeError("Native protected snapshot not confirmed")
        _,stats=read_snapshot_manifest(source,value["id"])
        if stats.get("aftergrid_pinned") is not True:raise RuntimeError("Native snapshot protection not confirmed")
    return value["id"]

def snapshot_application(job,ident,protect=False):
    if ident not in SNAPSHOT_SOURCES:raise ValueError("Unsupported snapshot application")
    change(job,state="running",total=4,completed=0,stage="Check repository and application")
    if kopia_status()["connection"]!="connected":raise RuntimeError("Connect Kopia repository first")
    original=state(ident)
    if original not in ("running","stopped"):raise RuntimeError("Application must be installed and healthy or stopped")
    change(job,completed=1,stage="Quiesce application")
    restart=original=="running"
    try:
        if restart:run(job,ident,"stop","--timeout","60")
        if not cleanly_stopped(ident):
            log_shutdown_evidence(job,ident)
            raise RuntimeError("Clean application shutdown not confirmed; snapshot refused")
        change(job,completed=2,stage="Create native Kopia snapshot")
        snapshot_id=native_snapshot(ident,**({"protect":True} if protect else {}))
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

CONTENT_SOURCES={"kiwix":"/source/content/kiwix","maps":"/source/content/maps",
                 "routing":"/source/content/routing","media":"/source/content/media"}
CONTENT_TIMEOUT=6*60*60

def content_guard(action,job):
    try:
        subprocess.run(["docker","exec","--user","10001:10001",core_container(),"python","/app/content_backup_guard.py",action,str(job)],
                       capture_output=True,timeout=20,check=True)
    except (OSError,subprocess.SubprocessError):
        raise RuntimeError("Content maintenance guard refused; finish downloads or inspect interrupted maintenance") from None

def content_snapshot(job,ident,protect=False):
    if ident not in CONTENT_SOURCES:raise ValueError("Unsupported content source")
    change(job,state="running",total=3,completed=0,stage="Check repository and content maintenance")
    if kopia_status()["connection"]!="connected":raise RuntimeError("Connect Kopia repository first")
    content_guard("begin",job)
    try:
        change(job,completed=1,stage="Create native content snapshot")
        snapshot_id=native_snapshot_source(CONTENT_SOURCES[ident],seconds=CONTENT_TIMEOUT,**({"protect":True} if protect else {}))
        log(job,"\nNative content snapshot: "+snapshot_id+"; restore not verified.\n")
        change(job,completed=2)
    finally:
        change(job,stage="Release content maintenance guard")
        content_guard("end",job)
    change(job,completed=3,state="succeeded",stage="Content snapshot complete; repository verification pending")

def latest_content_snapshot(ident,source_job=None):
    with db() as conn:
        if source_job is None:
            row=conn.execute("SELECT log FROM jobs WHERE module=? AND action='content-snapshot' AND state='succeeded' ORDER BY id DESC LIMIT 1",(ident,)).fetchone()
        else:
            row=conn.execute("SELECT log FROM jobs WHERE module=? AND action='content-snapshot' AND state='succeeded' AND id=?",(ident,source_job)).fetchone()
    match=re.search(r"Native content snapshot: ([a-f0-9]{32,64});",row["log"]) if row else None
    if not match:raise RuntimeError("No successful managed content snapshot recorded")
    return match.group(1)

def verify_content(job,ident,source_job=None):
    if ident not in CONTENT_SOURCES:raise ValueError("Unsupported content source")
    change(job,state="running",total=2,completed=0,stage="Locate exact content snapshot")
    if kopia_status()["connection"]!="connected":raise RuntimeError("Connect Kopia repository first")
    snapshot_id=latest_content_snapshot(ident) if source_job is None else latest_content_snapshot(ident,source_job)
    _,stats=read_snapshot_manifest(CONTENT_SOURCES[ident],snapshot_id)
    change(job,completed=1,stage="Read every file in native snapshot")
    verify_content_manifest(job,snapshot_id,stats)
    change(job,completed=2,state="succeeded",stage="Native content read verification passed; restore not tested")


def verify_content_manifest(job,snapshot_id,stats):
    """Shared exact-manifest full read; never changes parent job state."""
    if not isinstance(snapshot_id,str) or not re.fullmatch(r"[a-f0-9]{32,64}",snapshot_id):
        raise ValueError("Invalid native snapshot ID")
    try:
        raw=subprocess.run(command("kopia","exec","-T","kopia","timeout","--kill-after=10s",str(CONTENT_TIMEOUT)+"s",
            "/bin/kopia","snapshot","verify","--json","--verify-files-percent=100","--parallel=2","--file-parallelism=2",snapshot_id),
            env=compose_env("kopia"),capture_output=True,text=True,timeout=CONTENT_TIMEOUT+30,check=True).stdout
        if len(raw)>1024*1024:raise ValueError("Oversized verification output")
        value=json.loads(raw)
        result=value["stats"]
        # Kopia walks each distinct object once, not each pathname.
        if (type(value["errorCount"]) is not int or value["errorCount"]!=0
                or type(result["readFileCount"]) is not int or result["readFileCount"]<1
                or type(result["processedObjectCount"]) is not int or result["processedObjectCount"]<result["readFileCount"]
                or type(result["expectedTotalFileCount"]) is not int or result["expectedTotalFileCount"]!=stats["fileCount"]):
            raise ValueError("Verification incomplete")
    except (OSError,ValueError,TypeError,KeyError,subprocess.SubprocessError):
        raise RuntimeError("Native content verification failed or incomplete; inspect Kopia") from None
    log(job,"\nContent snapshot "+snapshot_id+" verified: "+str(result["readFileCount"])+" distinct file objects read; zero reported errors. No files restored.\n")
    return result["readFileCount"]

def recovery_sources():
    sources=[
        ("core","kopia","core-snapshot","core-verify-snapshot",CORE_SNAPSHOT_SOURCE,r"Core database export snapshot: ([a-f0-9]{32,64});","isolated"),
        ("worker","kopia","worker-snapshot","worker-verify-snapshot",WORKER_EXPORT_SOURCE,r"Worker state export snapshot: ([a-f0-9]{32,64});","isolated"),
    ]
    sources.extend(("application/"+ident,ident,"snapshot","verify-snapshot",source,r"Native snapshot reported complete: ([a-f0-9]{32,64});","isolated") for ident,source in sorted(SNAPSHOT_SOURCES.items()))
    sources.extend(("content/"+ident,ident,"content-snapshot","content-verify",source,r"Native content snapshot: ([a-f0-9]{32,64});","read-only") for ident,source in sorted(CONTENT_SOURCES.items()))
    return sources

def backup_policy_sources():
    # No arbitrary native policy target, no repository self-backup, and no
    # MicroTAK coverage. Global is read-only context, not a managed source.
    return {"global":None,**{key:source for key,_,_,_,source,_,_ in recovery_sources()
                            if key!="application/tak"}}


def summarize_native_policy(value):
    if not isinstance(value,dict):raise ValueError("Invalid native policy")
    schedule=value.get("scheduling",{})
    retention=value.get("retention",{})
    if not isinstance(schedule,dict) or not isinstance(retention,dict):raise ValueError("Invalid native policy")
    manual=schedule.get("manual",False)
    interval=schedule.get("intervalSeconds",0)
    times=schedule.get("timeOfDay",[]) or []
    cron=schedule.get("cron",[]) or []
    missed=schedule.get("runMissed")
    if (type(manual) is not bool or type(interval) is not int or not 0<=interval<2**63
        or not isinstance(times,list) or len(times)>1440 or not isinstance(cron,list) or len(cron)>1440
        or any(not isinstance(x,str) or not x or len(x)>4096 for x in cron)
        or (missed is not None and type(missed) is not bool)):
        raise ValueError("Invalid native schedule")
    tod=[]
    for t in times:
        if (not isinstance(t,dict) or type(t.get("hour")) is not int or not 0<=t["hour"]<=23
            or type(t.get("min")) is not int or not 0<=t["min"]<=59):
            raise ValueError("Invalid native schedule time")
        tod.append(f"{t['hour']:02d}:{t['min']:02d}")
    counts={}
    for k in ("keepLatest","keepHourly","keepDaily","keepWeekly","keepMonthly","keepAnnual"):
        n=retention.get(k)
        if n is not None and (type(n) is not int or not 0<=n<=2147483647):raise ValueError("Invalid native retention")
        counts[k]=n
    identical=retention.get("ignoreIdenticalSnapshots")
    if identical is not None and type(identical) is not bool:raise ValueError("Invalid native retention")
    configured=bool(interval or times or cron)
    return {"schedule":{"manual":manual,"configured":configured,"interval_seconds":interval,
                        "times_utc":tod,"cron_count":len(cron),"run_missed":missed,
                        "automatic_policy":configured and not manual},
            "retention":counts,"ignore_identical":identical}


def native_policy_summary(key):
    sources=backup_policy_sources()
    if key not in sources:raise ValueError("Unknown reviewed policy source")
    if RECOVERY_CORE_ONLY:raise RuntimeError("Policy inspection unavailable in core-only recovery")
    if kopia_status()["connection"]!="connected":raise RuntimeError("Connect Kopia repository first")
    source=sources[key]
    try:
        raw=subprocess.run(command("kopia","exec","-T","kopia","/bin/kopia","policy","show","--json",
                          source if source is not None else "--global"),
                           env=compose_env("kopia"),capture_output=True,text=True,timeout=8,check=True).stdout
        if len(raw)>1024*1024:raise ValueError("Oversized native response")
        result=summarize_native_policy(json.loads(raw))
    except (OSError,ValueError,TypeError,KeyError,subprocess.SubprocessError):
        raise RuntimeError("Native effective policy unavailable") from None
    return {"key":key,"source":source,"policy":result,
            "managed_scheduling_enabled":False,"consistency":"managed snapshot operations required",
            "retention_changes_enabled":key!="global" and not (RECOVERY_CORE_ONLY or RECOVERY_OFFLINE)}


def validate_retention_request(value):
    if (not isinstance(value,dict) or set(value)!={"key","expected","counts"}
        or not isinstance(value["key"],str) or value["key"]=="global"
        or value["key"] not in backup_policy_sources()):
        raise ValueError("Unsupported retention source")
    for name in ("expected","counts"):
        counts=value[name]
        if (not isinstance(counts,dict) or set(counts)!=set(RETENTION_FLAGS)
            or any(type(n) is not int or not 0<=n<=2147483647 for n in counts.values())):
            raise ValueError("Invalid retention counts")
    if value["counts"]["keepLatest"]<3 or any(n>3650 for n in value["counts"].values()):
        raise ValueError("Retain at least three latest snapshots; maximum 3650 per tier")
    return value


def enqueue_retention(value):
    if RECOVERY_CORE_ONLY or RECOVERY_OFFLINE or "kopia" not in catalog():
        raise ValueError("Retention changes unavailable")
    value=validate_retention_request(value)
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute("SELECT 1 FROM jobs WHERE state IN ('queued','running') LIMIT 1").fetchone():
            raise sqlite3.IntegrityError("Worker busy")
        cursor=conn.execute("INSERT INTO jobs(module,action,state,stage,created) VALUES ('kopia','set-retention','queued','Queued',?)",
                            (int(time.time()),))
        conn.execute("INSERT INTO retention_requests(job,request) VALUES (?,?)",
                     (cursor.lastrowid,json.dumps(value,sort_keys=True)))
        return cursor.lastrowid


def apply_retention(job):
    if RECOVERY_CORE_ONLY or RECOVERY_OFFLINE:raise ValueError("Retention changes unavailable")
    with db() as conn:
        row=conn.execute("SELECT request FROM retention_requests WHERE job=?",(job,)).fetchone()
    if not row:raise ValueError("Reviewed retention request missing")
    request=validate_retention_request(json.loads(row["request"]))
    key=request["key"]
    source=backup_policy_sources()[key]
    change(job,state="running",total=4,completed=0,stage="Check current native policy and recovery point")
    before=native_policy_summary(key)["policy"]
    if before["retention"]!=request["expected"]:
        raise RuntimeError("Native retention changed; reload policy before retrying")
    if before["schedule"]["automatic_policy"] or before["ignore_identical"] is not False:
        raise RuntimeError("Review native automatic scheduling and identical-snapshot settings first")
    # Require the latest managed source to be a verified, explicitly protected
    # capture, not merely an older or unrelated pinned manifest.
    record=next(r for r in recovery_manifest_records() if r["key"]==key)
    sid=record["snapshot_id"]
    source_job=record["snapshot_job"]
    expected_kind="read-only" if key.startswith("content/") else "isolated"
    if (not isinstance(sid,str) or not re.fullmatch(r"[a-f0-9]{32,64}",sid)
        or record["verification"]!=expected_kind or not record["verification_job"]
        or not protected_snapshot_requested(source_job)):
        raise RuntimeError("Create and verify a fresh protected snapshot of this source first")
    _,stats=read_snapshot_manifest(source,sid)
    if stats.get("aftergrid_pinned") is not True:
        raise RuntimeError("Native recovery pin no longer confirmed")
    change(job,completed=1,stage="Apply only reviewed native retention counts")
    args=[flag+"="+str(request["counts"][key]) for key,flag in RETENTION_FLAGS.items()]
    try:
        subprocess.run(command("kopia","exec","-T","kopia","/bin/kopia","policy","set",*args,source),
                       env=compose_env("kopia"),capture_output=True,text=True,timeout=30,check=True)
    except (OSError,ValueError,subprocess.SubprocessError):
        raise RuntimeError("Native policy change unconfirmed; inspect effective policy before retrying") from None
    change(job,completed=2,stage="Read back native policy")
    after=native_policy_summary(key)["policy"]
    if (after["retention"]!=request["counts"] or after["schedule"]!=before["schedule"]
        or after["ignore_identical"]!=before["ignore_identical"]):
        raise RuntimeError("Native policy readback differs; inspect before retrying")
    change(job,completed=3,stage="Recheck exact protected recovery manifest")
    _,stats=read_snapshot_manifest(source,sid)
    if stats.get("aftergrid_pinned") is not True:
        raise RuntimeError("Policy applied but protected snapshot readback failed; inspect repository")
    log(job,"\\nNative retention policy readback confirmed for "+key+"; verified protected manifest "+sid+" remains pinned. Other unpinned snapshots may expire under native retention. No explicit expiration run.\\n".replace("\\n","\n"))
    change(job,completed=4,state="succeeded",stage="Native retention and recovery pin confirmed")


def recovery_manifest_records():
    records=[]
    with db() as conn:
        for key,module,action,verify,source,pattern,kind in recovery_sources():
            record={"key":key,"module":module,"source":source,"snapshot_id":None,"snapshot_job":None,
                    "captured_at":None,"verification":"not recorded","verification_job":None,
                    "repository_status":"not checked","bytes":None,"file_count":None,"aftergrid_pinned":None}
            row=conn.execute("SELECT id,log,created FROM jobs WHERE module=? AND action=? AND state='succeeded' ORDER BY id DESC LIMIT 1",(module,action)).fetchone()
            if row:
                match=re.search(pattern,row["log"])
                if match:
                    sid=match.group(1)
                    record.update(snapshot_id=sid,snapshot_job=row["id"],captured_at=row["created"])
                    if key=="core":
                        record["content_metadata_included"]="Core export includes content metadata format 1." in row["log"]
                    if key=="worker":
                        digest=re.search(r"Worker recovery envelope SHA-256: ([a-f0-9]{64})",row["log"])
                        record["envelope_sha256"]=digest.group(1) if digest else None
                    # Require successful verification of this exact snapshot, never a newer failed job.
                    phrase=("Content snapshot "+sid+" verified:" if kind=="read-only" else "Snapshot "+sid+" restored;")
                    v=conn.execute("SELECT id,log FROM jobs WHERE module=? AND action=? AND state='succeeded' AND id>? AND instr(log,?)>0 ORDER BY id DESC LIMIT 1",(module,verify,row["id"],phrase)).fetchone()
                    if v:record.update(verification=kind,verification_job=v["id"])
            if key=="application/tak":
                record["recovery_blocked_reason"]="MicroTAK 0.18.1 application-consistent capture and native restore not accepted"
            records.append(record)
    return records

def backup_health():
    """Sanitized recorded history, not a new repository verification."""
    repository=kopia_status()
    records=recovery_manifest_records()
    try:
        inventory=load_recovery_manifest()
        if type(inventory.get("created")) is not int or not isinstance(inventory.get("records"),list):
            raise ValueError("Invalid inventory")
        checked={r["key"]:r for r in inventory["records"] if isinstance(r,dict) and isinstance(r.get("key"),str)}
        checked_at=inventory["created"]
        inventory_job=inventory["manifest_job"]
    except (RuntimeError,ValueError,TypeError):
        checked={}
        checked_at=inventory_job=None
    def attempt(row):
        return {k:row[k] for k in ("id","state","created")} if row else None
    result=[]
    with db() as conn:
        for key,module,action,verify,source,pattern,kind in recovery_sources():
            record=next(r for r in records if r["key"]==key)
            latest=conn.execute("SELECT id,state,created FROM jobs WHERE module=? AND action=? ORDER BY id DESC LIMIT 1",(module,action)).fetchone()
            last_verify=conn.execute("SELECT id,state,created FROM jobs WHERE module=? AND action=? ORDER BY id DESC LIMIT 1",(module,verify)).fetchone()
            matched=conn.execute("SELECT id,state,created FROM jobs WHERE id=? AND module=? AND action=?",(record["verification_job"],module,verify)).fetchone()
            pin=conn.execute("SELECT j.id,j.log,j.created FROM jobs j JOIN protected_snapshots p ON p.job=j.id WHERE j.module=? AND j.action=? AND j.state='succeeded' ORDER BY j.id DESC LIMIT 1",(module,action)).fetchone()
            protected=None
            if pin:
                match=re.search(pattern,pin["log"])
                if match:
                    sid=match.group(1)
                    phrase=("Content snapshot "+sid+" verified:" if kind=="read-only" else "Snapshot "+sid+" restored;")
                    proof=conn.execute("SELECT id,state,created FROM jobs WHERE module=? AND action=? AND state='succeeded' AND id>? AND instr(log,?)>0 ORDER BY id DESC LIMIT 1",(module,verify,pin["id"],phrase)).fetchone()
                    protected={"job":pin["id"],"created":pin["created"],"verification":attempt(proof),
                               "pin_at_inventory":None}
                    evidence=checked.get(key,{})
                    if evidence.get("snapshot_id")==sid and evidence.get("snapshot_job")==pin["id"]:
                        protected["pin_at_inventory"]=evidence.get("aftergrid_pinned") if type(evidence.get("aftergrid_pinned")) is bool else None
            evidence=checked.get(key,{})
            availability="not checked"
            pinned=None
            if record["snapshot_id"] and evidence.get("snapshot_id")==record["snapshot_id"] and evidence.get("snapshot_job")==record["snapshot_job"]:
                if evidence.get("repository_status") in {"present","unavailable"}:
                    availability=evidence["repository_status"]
                if type(evidence.get("aftergrid_pinned")) is bool:pinned=evidence["aftergrid_pinned"]
            elif not record["snapshot_id"]:availability="no managed snapshot"
            result.append({"key":key,"module":module,"supported":key!="application/tak",
                           "snapshot_job":record["snapshot_job"],"captured_at":record["captured_at"],
                           "verification_kind":record["verification"],"verified":attempt(matched),
                           "latest_attempt":attempt(latest),"latest_verification_attempt":attempt(last_verify),
                           "repository_at_inventory":availability,"pin_at_inventory":pinned,
                           "latest_protected_capture":protected})
        retention=conn.execute("SELECT id,state,created FROM jobs WHERE action='set-retention' AND module='kopia' ORDER BY id DESC LIMIT 1").fetchone()
    return {"repository":repository,"inventory_job":inventory_job,"inventory_checked_at":checked_at,
            "sources":result,"latest_retention_attempt":attempt(retention),
            "live_manifest_verification":False}


def recovery_manifest(job):
    change(job,state="running",total=3,completed=0,stage="Collect recorded recovery snapshots")
    if kopia_status()["connection"]!="connected":raise RuntimeError("Connect Kopia repository first")
    records=recovery_manifest_records()
    change(job,completed=1,stage="Check exact native snapshot manifests")
    for item in records:
        if item["snapshot_id"]:
            try:
                _,stats=read_snapshot_manifest(item["source"],item["snapshot_id"])
                item.update(repository_status="present",bytes=stats["totalSize"],file_count=stats["fileCount"],
                            aftergrid_pinned=stats.get("aftergrid_pinned"))
            except RuntimeError:
                item["repository_status"]="unavailable"
        else:item["repository_status"]="no managed snapshot"
    # Presence is not a new read verification. No secret values, arbitrary paths or logs are exported.
    result={"format":1,"manifest_job":job,"created":int(time.time()),"atomic":False,
            "complete_system_recovery":False,"records":records,
            "missing_artifacts":["rebuildable place indexes; review core content metadata coverage","host environment and exact release",
                                 "Docker image archive","replacement installation and disconnected acceptance"],
            "guidance":"Independent capture points; retain exact snapshot IDs, worker envelope digest, repository and password separately. Missing snapshots can represent uninstalled apps. Explicit protected captures use native pin-at-creation; check pin status independently of verification."}
    change(job,completed=2,stage="Save private recovery inventory")
    target=STATE/"recovery-manifest.json"
    fd,tmp=tempfile.mkstemp(prefix=".recovery-manifest-",dir=STATE)
    try:
        with os.fdopen(fd,"w") as stream:
            json.dump(result,stream,indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp,target)
    finally:Path(tmp).unlink(missing_ok=True)
    log(job,"\nRecovery inventory saved: "+str(sum(x["repository_status"]=="present" for x in records))+" of "+str(len(records))+" reviewed sources present. Not an atomic backup or recovery package.\n")
    change(job,completed=3,state="succeeded",stage="Recovery inventory generated")

def load_recovery_manifest():
    try:
        path=STATE/"recovery-manifest.json"
        if not stat.S_ISREG(path.lstat().st_mode) or path.stat().st_size>65536:
            raise ValueError("Invalid recovery inventory")
        value=json.loads(path.read_text())
        if value.get("format")!=1 or type(value.get("manifest_job")) is not int:
            raise ValueError("Invalid recovery inventory")
        with db() as conn:
            row=conn.execute("SELECT 1 FROM jobs WHERE id=? AND module='kopia' AND action='recovery-manifest' AND state='succeeded'",(value["manifest_job"],)).fetchone()
        if not row:raise ValueError("Inventory generation not confirmed")
        return value
    except (OSError,ValueError,TypeError,sqlite3.Error):
        raise RuntimeError("No confirmed recovery inventory; generate one first") from None

def core_container():
    try:
        raw=subprocess.run(["docker","ps","--no-trunc","--filter","label=com.docker.compose.project=aftergrid-core",
                            "--filter","label=com.docker.compose.service=core","--format","{{.ID}}"],
                           capture_output=True,text=True,timeout=8,check=True).stdout.split()
        if len(raw)!=1 or not re.fullmatch(r"[a-f0-9]{64}",raw[0]):
            raise ValueError("Core container missing or ambiguous")
        return raw[0]
    except (OSError,ValueError,subprocess.SubprocessError):
        raise RuntimeError("Running AfterGrid core container unavailable") from None

def core_snapshot(job,protect=False):
    change(job,state="running",total=3,completed=0,stage="Check repository and core")
    if kopia_status()["connection"]!="connected":raise RuntimeError("Connect Kopia repository first")
    cid=core_container()
    def export(action):
        try:
            subprocess.run(["docker","exec","--user","10001:10001",cid,"python","/app/backup_export.py",action,str(job)],
                           capture_output=True,timeout=45,check=True)
        except (OSError,subprocess.SubprocessError):
            raise RuntimeError("Private core export "+action+" failed; inspect staging before retrying") from None
    change(job,completed=1,stage="Create consistent private core database export")
    export("create")
    try:
        log(job,"\nCore export includes content metadata format 1.\n")
        change(job,completed=2,stage="Snapshot core database export using Kopia")
        snapshot_id=native_snapshot_source("/source/data/core/recovery-export",**({"protect":True} if protect else {}))
        log(job,"\nCore database export snapshot: "+snapshot_id+"; restore not verified.\n")
    finally:
        change(job,stage="Remove private core export")
        export("clear")
    change(job,completed=3,state="succeeded",stage="Core database snapshot complete; restore not verified")

WORKER_EXPORT_SOURCE="/tmp/aftergrid-worker-export"
WORKER_DB_LIMIT=32*1024*1024
WORKER_EXPORT_LIMIT=48*1024*1024

def worker_recovery_payload(job):
    """Export a consistent private copy; never modify the live worker database."""
    try:
        if type(job) is not int or not 0<job<10**19:raise ValueError("Invalid export job")
        reviewed={ident:set(m.get("generated_secrets",[])) for ident,m in catalog().items() if m.get("generated_secrets")}
        recovered={}
        directory=STATE/"secrets"
        with SECRET_LOCK:
            if directory.exists() or directory.is_symlink():
                if not stat.S_ISDIR(directory.lstat().st_mode):raise ValueError("Invalid secret directory")
                for path in directory.iterdir():
                    ident=path.stem
                    info=path.lstat()
                    if path.suffix!=".json" or ident not in reviewed or not stat.S_ISREG(info.st_mode) or info.st_mode&0o077 or not 0<info.st_size<=16384:
                        raise ValueError("Unexpected worker secret file")
                    value=json.loads(path.read_text())
                    if not isinstance(value,dict) or set(value)!=reviewed[ident] or not all(isinstance(v,str) and re.fullmatch(r"[a-f0-9]{64}",v) for v in value.values()):
                        raise ValueError("Invalid reviewed secret values")
                    recovered[ident]=value
            if "kopia" not in recovered:raise ValueError("Kopia recovery secrets missing")
            source=STATE/"jobs.sqlite3"
            if not stat.S_ISREG(source.lstat().st_mode):raise ValueError("Worker database unavailable")
            with tempfile.TemporaryDirectory(prefix="aftergrid-worker-export-") as tmp:
                target=Path(tmp)/"jobs.sqlite3"
                deadline=time.monotonic()+25
                with db() as src:
                    page_size=src.execute("PRAGMA page_size").fetchone()[0]
                    if src.execute("PRAGMA page_count").fetchone()[0]*page_size>WORKER_DB_LIMIT:raise ValueError("Worker database exceeds export limit")
                    dst=sqlite3.connect(target)
                    try:
                        def progress(status,remaining,total):
                            if time.monotonic()>deadline or total*page_size>WORKER_DB_LIMIT:raise ValueError("Worker export limit exceeded")
                        src.backup(dst,pages=128,progress=progress,sleep=0.05)
                        dst.execute("PRAGMA journal_mode=DELETE")
                        dst.execute("UPDATE jobs SET state='interrupted',stage='Restored unfinished job; inspect and retry manually' WHERE state IN ('queued','running')")
                        dst.commit()
                        dst.set_progress_handler(lambda: int(time.monotonic()>deadline),10000)
                        if dst.execute("PRAGMA integrity_check").fetchmany(2)!=[("ok",)]:raise ValueError("Worker export integrity check failed")
                        if not {"jobs","sharing","batches"}<={r[0] for r in dst.execute("SELECT name FROM sqlite_master WHERE type='table'")}:raise ValueError("Worker export schema missing")
                    finally:dst.close()
                if target.stat().st_size>WORKER_DB_LIMIT:raise ValueError("Worker database exceeds export limit")
                payload=json.dumps({"format":1,"job":job,"jobs_sqlite3":base64.b64encode(target.read_bytes()).decode("ascii"),
                                    "secrets":recovered},separators=(",",":")).encode("utf-8")
        if not 0<len(payload)<=WORKER_EXPORT_LIMIT:raise ValueError("Worker export exceeds limit")
        return payload,len(recovered)
    except (OSError,ValueError,TypeError,sqlite3.Error):
        raise RuntimeError("Private worker export failed; inspect worker state and reviewed secret files") from None

def worker_snapshot(job,protect=False):
    change(job,state="running",total=3,completed=0,stage="Check repository and export worker state")
    if kopia_status()["connection"]!="connected":raise RuntimeError("Connect Kopia repository first")
    payload,count=worker_recovery_payload(job)
    checksum=hashlib.sha256(payload).hexdigest()
    env=compose_env("kopia")
    def stage(script,stdin=None):
        try:
            subprocess.run(command("kopia","exec","-T","kopia","/bin/sh","-c",script,"worker-export",WORKER_EXPORT_SOURCE,str(job)),
                           env=env,input=stdin,capture_output=True,timeout=45,check=True)
        except (OSError,subprocess.SubprocessError):
            raise RuntimeError("Private worker staging operation failed; inspect existing staging before retrying") from None
    change(job,completed=1,stage="Stage private worker recovery export")
    # Pass secrets only through stdin, never argv, environment, HTTP or logs.
    stage('test -d /tmp && test ! -L /tmp && umask 077 && mkdir "$1" && printf "%s" "$2" > "$1/job-id" && cat > "$1/worker-recovery.json" && test -s "$1/worker-recovery.json"',payload)
    del payload
    try:
        change(job,completed=2,stage="Create native encrypted worker snapshot")
        snapshot_id=native_snapshot_source(WORKER_EXPORT_SOURCE,**({"protect":True} if protect else {}))
        log(job,"\nWorker state export snapshot: "+snapshot_id+"; "+str(count)+" secret sets; restore not verified.\n")
        log(job,"Worker recovery envelope SHA-256: "+checksum+"\n")
    finally:
        change(job,stage="Remove private worker export")
        stage('test -d "$1" && test ! -L "$1" && test -f "$1/job-id" && test ! -L "$1/job-id" && test "$(cat "$1/job-id")" = "$2" && test -f "$1/worker-recovery.json" && test ! -L "$1/worker-recovery.json" && test "$(find "$1" -mindepth 1 -maxdepth 1 | wc -l)" -eq 2 && rm "$1/worker-recovery.json" "$1/job-id" && rmdir "$1"')
    change(job,completed=3,state="succeeded",stage="Worker state snapshot complete; restore not verified")

CORE_SNAPSHOT_SOURCE="/source/data/core/recovery-export"
CORE_TABLES={"admin","sessions","first_run","households","inventory_locations",
             "inventory_connections","map_waypoints","map_routes","comm_devices","comm_plans"}

def managed_snapshot_record(ident,source_job=None):
    if ident=="core":
        module,action,pattern="kopia","core-snapshot",r"Core database export snapshot: ([a-f0-9]{32,64});"
    elif ident=="worker":
        module,action,pattern="kopia","worker-snapshot",r"Worker state export snapshot: ([a-f0-9]{32,64});"
    elif ident in SNAPSHOT_SOURCES:
        module,action,pattern=ident,"snapshot",r"Native snapshot reported complete: ([a-f0-9]{32,64});"
    else:
        raise RuntimeError("Unsupported managed snapshot source")
    with db() as conn:
        if source_job is None:
            row=conn.execute("SELECT id,log FROM jobs WHERE module=? AND action=? AND state='succeeded' ORDER BY id DESC LIMIT 1",(module,action)).fetchone()
        else:
            row=conn.execute("SELECT id,log FROM jobs WHERE module=? AND action=? AND state='succeeded' AND id=?",(module,action,source_job)).fetchone()
    if not row:raise RuntimeError("No successful managed snapshot recorded")
    match=re.search(pattern,row["log"])
    if not match:raise RuntimeError("Managed snapshot ID unavailable")
    return row["id"],match.group(1)

def latest_managed_snapshot(ident):
    return managed_snapshot_record(ident)[1]

def restore_manifest(ident,snapshot_id):
    source=CORE_SNAPSHOT_SOURCE if ident=="core" else WORKER_EXPORT_SOURCE if ident=="worker" else SNAPSHOT_SOURCES[ident]
    root,stats=read_snapshot_manifest(source,snapshot_id)
    if stats["totalSize"]>512*1024*1024:
        raise RuntimeError("Snapshot exceeds 512 MiB isolated restore limit")
    return root

def read_snapshot_manifest(source,snapshot_id):
    try:
        raw=subprocess.run(command("kopia","exec","-T","kopia","timeout","30s","/bin/kopia",
            "snapshot","list","--json","--json-verbose","--manifest-id","--max-results=50",source),
            env=compose_env("kopia"),capture_output=True,text=True,timeout=40,check=True).stdout
        if len(raw)>4*1024*1024:raise ValueError("Oversized snapshot list")
        rows=json.loads(raw)
        matches=[row for row in rows if row.get("id")==snapshot_id and row.get("source",{}).get("path")==source]
        if len(matches)!=1:raise ValueError("Snapshot missing or ambiguous")
        row=matches[0]
        stats=snapshot_statistics(row,source)
        root=row["rootEntry"]["obj"]
        if (not isinstance(root,str) or not re.fullmatch(r"[IZD]{0,8}[a-z]?[a-f0-9]{32,128}",root)
                or type(stats.get("totalSize")) is not int or stats["totalSize"]<0):
            raise ValueError("Snapshot size unavailable")
        pins=row.get("pins") or []
        if not isinstance(pins,list) or any(not isinstance(p,str) for p in pins):raise ValueError("Invalid native pins")
        return root,{**stats,"aftergrid_pinned":RECOVERY_PIN in pins}
    except (OSError,subprocess.SubprocessError,ValueError,KeyError,TypeError):
        raise RuntimeError("Managed snapshot missing, invalid or exceeds isolated restore limit") from None

def check_restored_database(data,required_tables,core=False):
    if not isinstance(data,bytes) or not 0<len(data)<=64*1024*1024 or not data.startswith(b"SQLite format 3\x00"):
        raise RuntimeError("Restored database missing, invalid or exceeds verification limit")
    try:
        with tempfile.TemporaryDirectory(prefix="aftergrid-db-check-") as tmp:
            path=Path(tmp)/"database.sqlite3"
            path.write_bytes(data)
            deadline=time.monotonic()+15
            conn=sqlite3.connect(path.as_uri()+"?mode=ro&immutable=1",uri=True)
            try:
                conn.execute("PRAGMA trusted_schema=OFF")
                conn.set_progress_handler(lambda: int(time.monotonic()>deadline),10000)
                if conn.execute("PRAGMA integrity_check").fetchmany(2)!=[("ok",)]:
                    raise RuntimeError("Restored database integrity check failed")
                tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not required_tables<=tables:
                    raise RuntimeError("Expected application schema missing")
                if core:
                    if conn.execute("SELECT COUNT(*) FROM admin").fetchone()!=(1,) or conn.execute("SELECT COUNT(*) FROM admin WHERE id=1 AND length(username)>0 AND length(password_hash)=128 AND length(salt)>0 AND length(server_name)>0").fetchone()!=(1,):
                        raise RuntimeError("Restored core administrator record invalid")
                    if conn.execute("SELECT COUNT(*) FROM sessions").fetchone()!=(0,):
                        raise RuntimeError("Restored core export contains active session records")
            finally:conn.close()
    except (OSError,sqlite3.Error):
        raise RuntimeError("Restored database integrity check unavailable") from None

def check_restored_grocy(data):
    check_restored_database(data,{"products","users"})

def check_restored_homebox(data):
    check_restored_database(data,{"groups","users","attachments"})

def check_restored_core(data):
    check_restored_database(data,CORE_TABLES,core=True)

def check_restored_content_metadata(payload):
    """Decode and validate stable recovery metadata; no paths are taken from records."""
    try:
        if not isinstance(payload,bytes) or not 0<len(payload)<=12*1024*1024:raise ValueError("Metadata size")
        value=json.loads(payload)
        if not isinstance(value,dict) or set(value)!={"format","downloads_sqlite3","regional_records"} or type(value["format"]) is not int or value["format"]!=1:
            raise ValueError("Metadata format")
        records=value["regional_records"]
        if not isinstance(records,dict) or not set(records)<={"map-job.json","routing-download.json"}:
            raise ValueError("Regional record names")
        if any(not isinstance(r,dict) or r.get("state") not in {"idle","complete","failed"} or len(json.dumps(r).encode())>65536 for r in records.values()):
            raise ValueError("Regional record state")
        data=base64.b64decode(value["downloads_sqlite3"],validate=True)
        if not 0<len(data)<=8*1024*1024 or not data.startswith(b"SQLite format 3\x00"):
            raise ValueError("Download database format")
        with tempfile.TemporaryDirectory(prefix="aftergrid-download-check-") as tmp:
            path=Path(tmp)/"downloads.sqlite3"
            path.write_bytes(data)
            deadline=time.monotonic()+15
            conn=sqlite3.connect(path.as_uri()+"?mode=ro&immutable=1",uri=True)
            try:
                conn.execute("PRAGMA trusted_schema=OFF")
                conn.set_progress_handler(lambda: int(time.monotonic()>deadline),10000)
                if conn.execute("PRAGMA integrity_check").fetchmany(2)!=[("ok",)]:raise ValueError("Download database integrity")
                columns={r[1] for r in conn.execute("PRAGMA table_info(downloads)")}
                if columns!={"key","name","state","size","digest","detail","updated"}:
                    raise ValueError("Download database schema")
                if conn.execute("SELECT 1 FROM downloads WHERE state IN ('queued','downloading','verifying','indexing') LIMIT 1").fetchone():
                    raise ValueError("Active download in recovery export")
            finally:conn.close()
        return data,records
    except (OSError,ValueError,TypeError,KeyError,sqlite3.Error):
        raise RuntimeError("Restored content metadata verification failed") from None

def check_restored_worker(payload,source_job,expected_checksum):
    """Validate the captured envelope without printing or applying any secret."""
    try:
        if not isinstance(payload,bytes) or not 0<len(payload)<=WORKER_EXPORT_LIMIT:
            raise ValueError("Worker envelope size")
        if not hmac.compare_digest(hashlib.sha256(payload).hexdigest(),expected_checksum):
            raise ValueError("Worker envelope digest")
        value=json.loads(payload)
        if not isinstance(value,dict) or set(value)!={"format","job","jobs_sqlite3","secrets"} or type(value["format"]) is not int or value["format"]!=1 or type(value["job"]) is not int or value["job"]!=source_job:
            raise ValueError("Worker envelope format")
        reviewed={ident:set(m.get("generated_secrets",[])) for ident,m in catalog().items() if m.get("generated_secrets")}
        recovered=value["secrets"]
        if not isinstance(recovered,dict) or "kopia" not in recovered or not set(recovered)<=set(reviewed):
            raise ValueError("Worker secret sets")
        for ident,fields in recovered.items():
            if not isinstance(fields,dict) or set(fields)!=reviewed[ident] or not all(isinstance(v,str) and re.fullmatch(r"[a-f0-9]{64}",v) for v in fields.values()):
                raise ValueError("Worker secret fields")
        data=base64.b64decode(value["jobs_sqlite3"],validate=True)
        if not 0<len(data)<=WORKER_DB_LIMIT or not data.startswith(b"SQLite format 3\x00"):
            raise ValueError("Worker database size or format")
        with tempfile.TemporaryDirectory(prefix="aftergrid-worker-check-") as tmp:
            path=Path(tmp)/"jobs.sqlite3"
            path.write_bytes(data)
            deadline=time.monotonic()+15
            with sqlite3.connect(path.as_uri()+"?mode=ro&immutable=1",uri=True) as conn:
                conn.execute("PRAGMA trusted_schema=OFF")
                conn.set_progress_handler(lambda: int(time.monotonic()>deadline),10000)
                if conn.execute("PRAGMA integrity_check").fetchmany(2)!=[("ok",)]:raise ValueError("Worker database integrity")
                if not {"jobs","sharing","batches"}<={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}:raise ValueError("Worker database schema")
                if conn.execute("SELECT COUNT(*) FROM jobs WHERE state IN ('queued','running')").fetchone()!=(0,):raise ValueError("Unsafe pending jobs")
                if conn.execute("SELECT COUNT(*) FROM jobs WHERE id=? AND module='kopia' AND action='worker-snapshot' AND state='interrupted'",(source_job,)).fetchone()!=(1,):raise ValueError("Worker snapshot job missing")
        return len(recovered)
    except (OSError,ValueError,TypeError,KeyError,sqlite3.Error):
        raise RuntimeError("Worker recovery envelope verification failed; inspect private restored files") from None

def worker_export_checksum(source_job):
    with db() as conn:
        row=conn.execute("SELECT log FROM jobs WHERE id=? AND module='kopia' AND action='worker-snapshot' AND state='succeeded'",(source_job,)).fetchone()
    match=re.search(r"Worker recovery envelope SHA-256: ([a-f0-9]{64})",row["log"]) if row else None
    if not match:raise RuntimeError("Worker snapshot has no recorded export digest; create a new managed snapshot")
    return match.group(1)

def verify_snapshot(job,ident,exact_source_job=None):
    if ident not in {"core","worker"} and ident not in SNAPSHOT_SOURCES:raise ValueError("Unsupported restore verification")
    change(job,state="running",total=4,completed=0,stage="Locate latest managed snapshot")
    if kopia_status()["connection"]!="connected":raise RuntimeError("Connect Kopia repository first")
    source_job,snapshot_id=managed_snapshot_record(ident) if exact_source_job is None else managed_snapshot_record(ident,exact_source_job)
    expected_checksum=worker_export_checksum(source_job) if ident=="worker" else None
    root=restore_manifest(ident,snapshot_id)
    # Each verification gets a new private directory, never a live data mount.
    target="/restore/aftergrid-"+ident+"-"+str(job)+"-"+secrets.token_hex(8)
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
        change(job,completed=3,stage="Verify restored application data")
        if ident=="worker":
            marker=execute("/bin/sh","-c",
                'p="$1/data"; f="$p/job-id"; test -d "$1" && test ! -L "$1" && test -d "$p" && test ! -L "$p" && test -f "$f" && test ! -L "$f" && test "$(stat -c %s "$f")" -le 19 && cat "$f"',
                "check-worker-marker",target)
            if marker!=str(source_job).encode("ascii"):raise RuntimeError("Restored worker export job marker mismatch")
            payload=execute("/bin/sh","-c",
                'p="$1/data"; f="$p/worker-recovery.json"; test -d "$1" && test ! -L "$1" && test -d "$p" && test ! -L "$p" && test -f "$f" && test ! -L "$f" && size=$(stat -c %s "$f") && test "$size" -le 50331648 && cat "$f"',
                "check-worker-envelope",target,timeout=30)
            count=check_restored_worker(payload,source_job,expected_checksum)
            del payload
            result="Exact worker envelope digest, database integrity, interrupted jobs and "+str(count)+" reviewed secret sets verified"
        elif ident=="tak":
            # Only a certificate-presence check here. CI compares the exact public CA.
            execute("/bin/sh","-c",
                'p="$1/data/data"; f="$p/ca-cert.pem"; test -d "$1/data" && test ! -L "$1/data" && test -d "$p" && test ! -L "$p" && test -f "$f" && test ! -L "$f" && test -s "$f" && grep -q "^-----BEGIN CERTIFICATE-----" "$f"',
                "check-tak-ca",target)
            result="MicroTAK restored CA certificate presence passed"
        elif ident=="media":
            # Only native configuration is in this managed snapshot; media and cache are separate.
            execute("/bin/sh","-c",
                'p="$1/data"; test -d "$p" && test ! -L "$p" && if test -d "$p/config"; then test ! -L "$p/config" || exit 1; f="$p/config/system.xml"; else f="$p/system.xml"; fi; test -f "$f" && test ! -L "$f" && test -s "$f"',
                "check-media-config",target)
            result="Jellyfin restored system configuration presence passed; media files not included"
        elif ident=="notes":
            # Verify native setup/ACL files and at least one regular page without
            # evaluating PHP, logging account data or following symlink directories.
            execute("/bin/sh","-c",
                'p="$1/data"; test -d "$p" && test ! -L "$p" && for d in conf data data/pages; do test -d "$p/$d" && test ! -L "$p/$d" || exit 1; done && for f in local.php users.auth.php acl.auth.php; do test -f "$p/conf/$f" && test ! -L "$p/conf/$f" && test -s "$p/conf/$f" || exit 1; done && page=$(find "$p/data/pages" -type f -name "*.txt" -print -quit) && test -n "$page"',
                "check-wiki",target)
            result="DokuWiki configuration, ACL/account files and page presence passed"
        else:
            # Fixed database paths; refuse symlinks, active journals and oversize files.
            folder="data/data" if ident=="grocy" else "data"
            filename={"grocy":"grocy.db","homebox":"homebox.db","core":"core.sqlite3","meshmonitor":"meshmonitor.db","kolibri":"db.sqlite3"}[ident]
            data=execute("/bin/sh","-c",
                'p="$1/$2"; f="$p/$3"; test -d "$1" && test ! -L "$1" && test -d "$1/data" && test ! -L "$1/data" && test -d "$p" && test ! -L "$p" && test -f "$f" && test ! -L "$f" && test ! -e "$f-wal" && test ! -L "$f-wal" && test ! -e "$f-journal" && test ! -L "$f-journal" && size=$(stat -c %s "$f") && test "$size" -le 67108864 && cat "$f"',
                "check-database",target,folder,filename,timeout=30)
            if ident=="grocy":check_restored_grocy(data)
            elif ident=="homebox":check_restored_homebox(data)
            elif ident=="meshmonitor":check_restored_database(data,{"settings"})
            elif ident=="kolibri":
                check_restored_database(data,{"django_migrations"})
                execute("/bin/sh","-c",
                    'p="$1/data"; f="$p/.node_id"; test -d "$p" && test ! -L "$p" && test -f "$f" && test ! -L "$f" && test -s "$f"',
                    "check-kolibri-identity",target)
            else:
                marker=execute("/bin/sh","-c",
                    'f="$1/data/job-id"; test -f "$f" && test ! -L "$f" && test "$(stat -c %s "$f")" -le 19 && cat "$f"',
                    "check-export-marker",target)
                if marker!=str(source_job).encode("ascii"):
                    raise RuntimeError("Restored core export job marker mismatch")
                check_restored_core(data)
                with db() as conn:
                    row=conn.execute("SELECT log FROM jobs WHERE id=?",(source_job,)).fetchone()
                has_metadata=row is not None and "Core export includes content metadata format 1." in row["log"]
                if has_metadata:
                    payload=execute("/bin/sh","-c",
                        'f="$1/data/content-metadata.json"; test -f "$f" && test ! -L "$f" && test "$(stat -c %s "$f")" -le 12582912 && cat "$f"',
                        "check-content-metadata",target,timeout=30)
                    check_restored_content_metadata(payload)
            result="SQLite integrity and expected schema passed"
            if ident=="core":
                result+="; administrator present and sessions absent"
                result+="; content metadata verified" if has_metadata else "; legacy export without content metadata evidence"
    except (OSError,subprocess.SubprocessError,ValueError):
        raise RuntimeError("Isolated restore or application data check failed; inspect private restore directory") from None
    if exact_source_job is not None:
        # Only the exclusively created verification directory. Successful
        # scheduled restores must not accumulate private data indefinitely.
        # Failed verification retains its directory for inspection.
        try:
            execute("/bin/sh","-c",'test -d "$1" && test ! -L "$1" && rm -rf -- "$1"',"clear-scheduled-verification",target,timeout=60)
        except (OSError,subprocess.SubprocessError):
            raise RuntimeError("Verified restore cleanup failed; inspect private directory") from None
    log(job,"\nSnapshot "+snapshot_id+" restored; "+result+". Native application startup not tested.\n")
    if ident=="homebox":log(job,"Homebox worker API-key pepper is outside this snapshot; exact recovery not verified.\n")
    if ident=="meshmonitor":log(job,"MeshMonitor generated credentials are outside this snapshot; exact recovery not verified.\n")
    change(job,completed=4,state="succeeded",stage="Isolated restore and application data check passed")


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
    "tak":"Recovery unsupported: MicroTAK 0.18.1 has no confirmed clean shutdown or native consistent restore. Preserve CA/private-key material securely; managed snapshot is diagnostic only and refuses nonzero exit.",
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
            "coverage":"planned only","snapshot_verified":False,"managed_snapshot_supported":ident in SNAPSHOT_SOURCES}

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
    if RECOVERY_OFFLINE:raise RuntimeError("Offline recovery disables registry checks")
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

IMAGE_ID_PATTERN=r"sha256:[a-f0-9]{64}"

def approved_update_candidate(ident):
    """Repository-owned approval only; no browser-supplied image or tag."""
    if ident!="kiwix":return None
    path=MODULES/ident/"update-candidate.json"
    try:info=path.lstat()
    except FileNotFoundError:return None
    if not stat.S_ISREG(info.st_mode) or not 0<info.st_size<=8192:
        raise ValueError("Invalid approved candidate file")
    value=json.loads(path.read_text())
    if not isinstance(value,dict) or set(value)!={"format","candidate"} or type(value["format"]) is not int or value["format"]!=1:
        raise ValueError("Invalid approved candidate file")
    candidate=value["candidate"]
    if candidate is None:return None
    if (not isinstance(candidate,dict) or set(candidate)!={"image","platforms"}
        or not isinstance(candidate["image"],str)
        or not re.fullmatch(r"ghcr\.io/kiwix/kiwix-serve:[A-Za-z0-9_.-]{1,100}@"+IMAGE_ID_PATTERN,candidate["image"])
        or not isinstance(candidate["platforms"],dict) or not 1<=len(candidate["platforms"])<=2):
        raise ValueError("Invalid approved Kiwix candidate")
    for platform,entry in candidate["platforms"].items():
        if (platform not in {"linux/amd64","linux/arm64"} or not isinstance(entry,dict)
            or set(entry)!={"from","to"} or not isinstance(entry["to"],str) or not re.fullmatch(IMAGE_ID_PATTERN,entry["to"])
            or not isinstance(entry["from"],list) or not 1<=len(entry["from"])<=16
            or any(not isinstance(x,str) or not re.fullmatch(IMAGE_ID_PATTERN,x) for x in entry["from"])
            or len(set(entry["from"]))!=len(entry["from"]) or entry["to"] in entry["from"]):
            raise ValueError("Invalid candidate platform approval")
    return candidate


def update_eligibility(ident,online=False,own_job=None):
    """Advisory only: no backup, pull, Compose mutation or update admission."""
    if ident not in catalog():raise ValueError("Unknown module")
    result={"module":ident,"pilot_supported":ident=="kiwix","automatic_execution_enabled":False,
            "registry_checked":False,"status":"unsupported pilot","candidate":None,"blockers":[],
            "checked_at":int(time.time())}
    if ident!="kiwix":return result
    if RECOVERY_CORE_ONLY or RECOVERY_OFFLINE:
        result.update(status="blocked",blockers=["Recovery mode disables update checks"])
        return result
    try:
        if kiwix_rollback_override():
            result.update(status="blocked",blockers=["Previous reader rollback hold; inspect recovery evidence"])
            return result
        candidate=approved_update_candidate(ident)
    except (OSError,ValueError,TypeError):
        result.update(status="blocked",blockers=["Reviewed candidate file invalid"])
        return result
    if candidate is None:
        result["status"]="no approved update"
        return result
    result["candidate"]=candidate["image"]
    try:
        local=version_report(ident)
        services=local["services"]
        if len(services)!=1 or services[0]["service"]!=ident or services[0]["configured_image"]!=candidate["image"]:
            raise ValueError("Reviewed candidate does not match single-service Compose target")
        service=services[0]
        platform=subprocess.run(["docker","version","--format","{{.Server.Os}}/{{.Server.Arch}}"],
                                capture_output=True,text=True,timeout=4,check=True).stdout.strip()
        result.update(platform=platform,installed_image_ids=service["installed_image_ids"],
                      local_target_image_id=service["local_target_image_id"])
        approval=candidate["platforms"].get(platform)
        if approval is None:raise ValueError("Platform not approved")
        installed=service["installed_image_ids"]
        result["expected_target_image_id"]=approval["to"]
        if installed==[approval["to"]]:
            result["status"]="matches approved target"
            return result
        if len(installed)!=1 or installed[0] not in approval["from"]:
            result["blockers"].append("Installed image is not an approved starting point")
        if state(ident)!="running":result["blockers"].append("Reader must be running and ready")
        with db() as conn:
            if conn.execute("SELECT 1 FROM jobs WHERE state IN ('queued','running') AND id!=? LIMIT 1",(own_job or 0,)).fetchone():
                result["blockers"].append("Worker jobs active")
            last=conn.execute("SELECT state FROM jobs WHERE module=? AND action='update' AND id!=? ORDER BY id DESC LIMIT 1",(ident,own_job or 0)).fetchone()
            if unresolved_guarded_update(conn,own_job or 0) or (last and last["state"] in {"failed","interrupted"}):result["blockers"].append("Unresolved previous update outcome")
        if kopia_status()["connection"]!="connected":result["blockers"].append("Connect Kopia repository first")
        if result["blockers"]:
            result["status"]="blocked"
            return result
        if not online:
            result["status"]="registry check required"
            return result
        registry=registry_report(ident)
        result["registry_checked"]=True
        result["registry_config_digest"]=registry.get("registry_config_digest")
        result["platform_manifest_digest"]=registry.get("platform_manifest_digest")
        if registry.get("registry_config_digest") is None:
            result.update(status="registry unavailable",blockers=["Registry identity not confirmed"])
        elif (registry.get("configured_image")!=candidate["image"] or registry.get("platform")!=platform
              or registry.get("installed_image_ids")!=installed or registry["registry_config_digest"]!=approval["to"]
              or not registry.get("platform_manifest_digest")):
            result.update(status="blocked",blockers=["Registry or installed image identity differs from reviewed platform approval"])
        else:result["status"]="reviewed candidate confirmed"
    except (OSError,ValueError,TypeError,KeyError,RuntimeError,sqlite3.Error,subprocess.SubprocessError):
        result.update(status="blocked",blockers=["Local or registry eligibility evidence unavailable or invalid"])
    return result


def validate_update_preparation(value):
    if (not isinstance(value,dict) or set(value)!={"candidate","platform","previous_image_id","target_image_id"}
        or not isinstance(value["candidate"],str)
        or not re.fullmatch(r"ghcr\.io/kiwix/kiwix-serve:[A-Za-z0-9_.-]{1,100}@"+IMAGE_ID_PATTERN,value["candidate"])
        or value["platform"] not in {"linux/amd64","linux/arm64"}
        or any(not isinstance(value[k],str) or not re.fullmatch(IMAGE_ID_PATTERN,value[k]) for k in ("previous_image_id","target_image_id"))
        or value["previous_image_id"]==value["target_image_id"]):
        raise ValueError("Invalid reviewed transition")
    return value


def enqueue_update_preparation(value,guarded=False):
    if RECOVERY_CORE_ONLY or RECOVERY_OFFLINE or "kiwix" not in catalog():raise ValueError("Update preparation unavailable")
    value=validate_update_preparation(value)
    if kiwix_rollback_override():raise ValueError("Reader rollback hold")
    candidate=approved_update_candidate("kiwix")
    approval=candidate["platforms"].get(value["platform"]) if candidate else None
    if (not approval or candidate["image"]!=value["candidate"] or approval["to"]!=value["target_image_id"]
        or value["previous_image_id"] not in approval["from"]):
        raise ValueError("No matching approved transition")
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute("SELECT 1 FROM jobs WHERE state IN ('queued','running') LIMIT 1").fetchone():
            raise sqlite3.IntegrityError("Worker busy")
        if guarded:
            prior=conn.execute("SELECT state FROM jobs WHERE module='kiwix' AND action='update' ORDER BY id DESC LIMIT 1").fetchone()
            if unresolved_guarded_update(conn) or (prior and prior["state"] in {"failed","interrupted"}):raise ValueError("Unresolved update outcome")
        row=conn.execute("INSERT INTO jobs(module,action,state,stage,created) VALUES ('kiwix',?,'queued','Queued',?)",("guarded-update" if guarded else "prepare-update",int(time.time())))
        conn.execute("INSERT INTO update_preparations(job,request) VALUES (?,?)",(row.lastrowid,json.dumps(value,sort_keys=True)))
        return row.lastrowid


def check_preparation_identity(job,expected,online):
    result=update_eligibility("kiwix",online=online,own_job=job)
    if (result["status"]!=("reviewed candidate confirmed" if online else "registry check required")
        or result.get("candidate")!=expected["candidate"] or result.get("platform")!=expected["platform"]
        or result.get("installed_image_ids")!=[expected["previous_image_id"]]
        or result.get("expected_target_image_id")!=expected["target_image_id"]):
        raise RuntimeError("Approved update identity or admission changed; inspect eligibility")
    # Check the installed old image by ID, not a mutable tag.
    try:
        raw=subprocess.run(["docker","image","inspect","--format","{{json .Id}}",expected["previous_image_id"]],
                           capture_output=True,text=True,timeout=5,check=True).stdout
        if json.loads(raw)!=expected["previous_image_id"]:raise ValueError("Image changed")
    except (OSError,ValueError,TypeError,subprocess.SubprocessError):
        raise RuntimeError("Previous Docker image unavailable") from None
    return result


PREVIOUS_IMAGE_LIMIT=4*1024**3

def verify_previous_archive(folder,image_id):
    """Verify archive identity and saved checksum without extracting files."""
    if not isinstance(image_id,str) or not re.fullmatch(IMAGE_ID_PATTERN,image_id):
        raise ValueError("Invalid previous image ID")
    folder=Path(folder)
    if not stat.S_ISDIR(folder.lstat().st_mode) or folder.stat().st_mode&0o077:
        raise ValueError("Invalid previous image directory")
    archive=folder/"image.tar"
    metadata=folder/"image.json"
    for path,limit in ((archive,PREVIOUS_IMAGE_LIMIT),(metadata,4096)):
        info=path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_mode&0o077 or not 0<info.st_size<=limit:
            raise ValueError("Invalid private image archive")
    value=json.loads(metadata.read_text())
    if (not isinstance(value,dict) or set(value)!={"format","image_id","sha256","bytes"}
        or type(value["format"]) is not int or value["format"]!=1 or value["image_id"]!=image_id
        or type(value["bytes"]) is not int or value["bytes"]!=archive.stat().st_size
        or not isinstance(value["sha256"],str) or not re.fullmatch(r"[a-f0-9]{64}",value["sha256"])):
        raise ValueError("Previous image metadata mismatch")
    with archive.open("rb") as stream:
        if hashlib.file_digest(stream,"sha256").hexdigest()!=value["sha256"]:
            raise ValueError("Previous image archive checksum mismatch")
    with tarfile.open(archive,"r:") as bundle:
        def read_member(name,limit):
            matches=[m for m in bundle.getmembers() if m.name==name]
            if len(matches)!=1 or not matches[0].isfile() or not 0<matches[0].size<=limit:
                raise ValueError("Invalid image archive member")
            with bundle.extractfile(matches[0]) as stream:return stream.read(limit+1)
        manifest=json.loads(read_member("manifest.json",1024*1024))
        if not isinstance(manifest,list) or len(manifest)!=1 or not isinstance(manifest[0],dict):
            raise ValueError("Expected a single saved image")
        config=manifest[0].get("Config")
        if not isinstance(config,str) or not re.fullmatch(r"(?:blobs/sha256/[a-f0-9]{64}|[a-f0-9]{64}\.json)",config):
            raise ValueError("Invalid image config member")
        if "sha256:"+hashlib.sha256(read_member(config,4*1024*1024)).hexdigest()!=image_id:
            raise ValueError("Saved image config identity mismatch")
    return value


def preserve_previous_image(image_id):
    """Private native archive per exact prior Kiwix image, not an off-host backup."""
    if not isinstance(image_id,str) or not re.fullmatch(IMAGE_ID_PATTERN,image_id):
        raise ValueError("Invalid previous image ID")
    root=STATE/"previous-images"
    root.mkdir(mode=0o700,exist_ok=True)
    if not stat.S_ISDIR(root.lstat().st_mode) or root.stat().st_mode&0o077:
        raise RuntimeError("Invalid previous image storage")
    target=root/("kiwix-"+image_id.split(":")[1])
    if target.exists() or target.is_symlink():
        try:return verify_previous_archive(target,image_id)
        except (OSError,ValueError,TypeError,tarfile.TarError):
            raise RuntimeError("Existing previous image archive invalid; inspect before retry") from None
    try:
        raw=subprocess.run(["docker","image","inspect","--format","{{json .Size}}",image_id],
                           capture_output=True,text=True,timeout=5,check=True).stdout
        size=json.loads(raw)
        if type(size) is not int or not 0<size<=PREVIOUS_IMAGE_LIMIT//2:
            raise ValueError("Image size exceeds preservation limit")
        if shutil.disk_usage(root).free<2*size+512*1024**2:
            raise ValueError("Insufficient free space to preserve previous image")
        with tempfile.TemporaryDirectory(prefix=".kiwix-",dir=root) as tmp:
            stage=Path(tmp)
            archive=stage/"image.tar"
            archive.touch(mode=0o600,exist_ok=False)
            # Bound streamed output before writing it; never extract image members.
            with archive.open("wb") as out:
                with subprocess.Popen(["docker","image","save",image_id],stdout=subprocess.PIPE,
                                      stderr=subprocess.DEVNULL) as proc:
                    timer=threading.Timer(900,proc.kill)
                    timer.start()
                    try:
                        count=0
                        while chunk:=proc.stdout.read(1024*1024):
                            count+=len(chunk)
                            if count>PREVIOUS_IMAGE_LIMIT:raise ValueError("Saved image exceeds preservation limit")
                            out.write(chunk)
                        if proc.wait()!=0 or not count:raise RuntimeError("Native image save failed")
                    finally:
                        timer.cancel()
                        if proc.poll() is None:proc.kill();proc.wait()
                out.flush()
                os.fsync(out.fileno())
            with archive.open("rb") as stream:digest=hashlib.file_digest(stream,"sha256").hexdigest()
            metadata={"format":1,"image_id":image_id,"sha256":digest,"bytes":count}
            fd=os.open(stage/"image.json",os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,"w") as stream:
                json.dump(metadata,stream,sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            verify_previous_archive(stage,image_id)
            directory=os.open(stage,os.O_DIRECTORY)
            try:os.fsync(directory)
            finally:os.close(directory)
            if target.exists() or target.is_symlink():raise ValueError("Previous image archive appeared concurrently")
            os.rename(stage,target)
            directory=os.open(root,os.O_DIRECTORY)
            try:os.fsync(directory)
            finally:os.close(directory)
        return metadata
    except (OSError,ValueError,TypeError,RuntimeError,subprocess.SubprocessError,tarfile.TarError):
        raise RuntimeError("Previous image preservation failed; inspect storage and Docker before retry") from None


def kiwix_catalog_sample():
    """Bounded native reader probe; no arbitrary URLs, redirects or proxy."""
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),KopiaNoRedirect())
    try:
        with opener.open("http://aftergrid-kiwix:8080/catalog/v2/entries",timeout=10) as response:
            if response.status!=200:raise ValueError("Catalog unavailable")
            raw=response.read(2*1024*1024+1)
        if len(raw)>2*1024*1024 or b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
            raise ValueError("Invalid catalog")
        root=ET.fromstring(raw)
        ns="{http://www.w3.org/2005/Atom}"
        if root.tag!=ns+"feed":raise ValueError("Invalid reader feed")
        ids=sorted(entry.findtext(ns+"id","") for entry in root.findall(ns+"entry"))
        if not ids or len(ids)>1000 or len(set(ids))!=len(ids) or any(not s or len(s)>512 for s in ids):
            raise ValueError("Expected nonempty unique catalog sample")
        return ids
    except (OSError,ValueError,ET.ParseError):
        raise RuntimeError("Kiwix native catalog sample unavailable or empty") from None


def reader_compose_fingerprint():
    path=MODULES/"kiwix"/"compose.yaml"
    info=path.lstat()
    if not stat.S_ISREG(info.st_mode) or not 0<info.st_size<=65536:
        raise ValueError("Reviewed reader configuration unavailable")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def publish_reader_rollback(image_id):
    """Persist the old image selection before any restoration Compose up."""
    tag=rollback_tag(image_id)
    path=STATE/"kiwix-rollback.json"
    existing=kiwix_rollback_override()
    if existing:
        if existing[1]!=image_id:raise RuntimeError("Different reader rollback hold exists")
        return existing
    value={"services":{"kiwix":{"image":tag,"pull_policy":"never"}}}
    fd,tmp=tempfile.mkstemp(prefix=".kiwix-rollback-",dir=STATE)
    try:
        with os.fdopen(fd,"w") as out:
            json.dump(value,out,sort_keys=True)
            out.flush()
            os.fsync(out.fileno())
        os.link(tmp,path)  # do not overwrite another hold
        directory=os.open(STATE,os.O_DIRECTORY)
        try:os.fsync(directory)
        finally:os.close(directory)
    finally:Path(tmp).unlink(missing_ok=True)
    return kiwix_rollback_override()


def rollback_reader(job,expected,evidence):
    """Image-only rollback for the reviewed read-only Kiwix reader."""
    if RECOVERY_CORE_ONLY or RECOVERY_OFFLINE or evidence.get("recreation_attempted") is not True:
        raise ValueError("Reader rollback unavailable")
    image=expected["previous_image_id"]
    if evidence.get("compose_sha256")!=reader_compose_fingerprint():
        raise RuntimeError("Reader Compose configuration changed; automatic rollback refused")
    folder=STATE/"previous-images"/("kiwix-"+image.split(":")[1])
    metadata=verify_previous_archive(folder,image)
    if metadata!=evidence["previous_image_archive"]:
        raise RuntimeError("Previous image archive differs from preparation evidence")
    _,stats=read_snapshot_manifest(CONTENT_SOURCES["kiwix"],evidence["snapshot_id"])
    if stats.get("aftergrid_pinned") is not True:raise RuntimeError("Protected recovery snapshot unavailable")
    # Load only the verified local archive. Never pull a recovery image.
    try:exact_local_image(image,image)
    except RuntimeError:
        subprocess.run(["docker","image","load","--input",str(folder/"image.tar")],
                       capture_output=True,timeout=900,check=True)
        exact_local_image(image,image)
    tag=rollback_tag(image)
    # Reserved deterministic tag; do not overwrite an unexpected image.
    try:
        raw=subprocess.run(["docker","image","inspect","--format","{{json .Id}}",tag],
                           capture_output=True,text=True,timeout=8,check=True).stdout
        if json.loads(raw)!=image:raise RuntimeError("Unexpected existing rollback image tag")
    except subprocess.CalledProcessError:
        subprocess.run(["docker","image","tag",image,tag],capture_output=True,timeout=20,check=True)
    exact_local_image(tag,image)
    publish_reader_rollback(image)
    change(job,stage="Restore exact previous reader without pull or build")
    run(job,"kiwix","config","-q")
    run(job,"kiwix","up","-d","--wait","--wait-timeout","90","--pull","never","--no-build")
    wait_ready("kiwix")
    services=version_report("kiwix")["services"]
    if (len(services)!=1 or services[0]["service"]!="kiwix"
        or services[0]["configured_image"]!=tag or services[0]["installed_image_ids"]!=[image]):
        raise RuntimeError("Restored reader image identity not confirmed")
    sample=kiwix_catalog_sample()
    if hashlib.sha256(json.dumps(sample).encode()).hexdigest()!=evidence["catalog_sample_sha256"]:
        raise RuntimeError("Restored reader catalog differs from pre-update sample")
    evidence.update(rollback_status="restored",rollback_image_id=image,rollback_checked_at=int(time.time()))


def guarded_compose_update(job,expected,evidence):
    """Run only the reviewed Compose target under the caller's content guard."""
    sample=kiwix_catalog_sample()
    change(job,completed=5,stage="Pull reviewed digest-pinned image")
    check_preparation_identity(job,expected,True)
    run(job,"kiwix","config","-q")
    run(job,"kiwix","pull")
    result=check_preparation_identity(job,expected,False)
    if result.get("local_target_image_id")!=expected["target_image_id"]:
        raise RuntimeError("Pulled image ID does not match reviewed target; no recreation")
    # Persist verified pre-update evidence and the mutation boundary before
    # recreation. Failed/interrupted jobs retain it for operator recovery.
    evidence.update(catalog_sample_before=len(sample),catalog_sample_sha256=hashlib.sha256(json.dumps(sample).encode()).hexdigest(),
                    compose_sha256=reader_compose_fingerprint(),recreation_attempted=True)
    with db() as conn:
        conn.execute("UPDATE update_preparations SET evidence=? WHERE job=?",(json.dumps(evidence,sort_keys=True),job))
    change(job,completed=6,stage="Recreate reviewed Kiwix service")
    run(job,"kiwix","up","-d","--wait","--wait-timeout","90","--pull","never","--no-build")
    change(job,completed=7,stage="Verify target image and reader catalog")
    wait_ready("kiwix")
    local=version_report("kiwix")
    services=local["services"]
    if (len(services)!=1 or services[0]["service"]!="kiwix"
        or services[0]["configured_image"]!=expected["candidate"]
        or services[0]["installed_image_ids"]!=[expected["target_image_id"]]):
        raise RuntimeError("Updated container image identity not confirmed")
    if kiwix_catalog_sample()!=sample:
        raise RuntimeError("Updated reader catalog sample differs; inspect preserved recovery evidence")
    evidence.update(update_performed=True,result_image_id=expected["target_image_id"],catalog_sample_matched=True,
                    post_update_checked_at=int(time.time()))
    log(job,"\nReviewed target image and native catalog sample confirmed. Full article retrieval and rollback acceptance remain separate.\n")


def prepare_update(job,guarded=False):
    """Capture new recovery evidence; optionally execute one guarded reader update."""
    if RECOVERY_CORE_ONLY or RECOVERY_OFFLINE:raise ValueError("Update preparation unavailable")
    with db() as conn:
        row=conn.execute("SELECT request FROM update_preparations WHERE job=?",(job,)).fetchone()
    if not row:raise ValueError("Reviewed transition request missing")
    expected=validate_update_preparation(json.loads(row["request"]))
    change(job,state="running",total=9 if guarded else 6,completed=0,stage="Recheck approved transition and registry")
    check_preparation_identity(job,expected,True)
    source=CONTENT_SOURCES["kiwix"]
    policy=native_policy_summary("content/kiwix")["policy"]
    if policy["schedule"]["automatic_policy"] or policy["ignore_identical"] is not False:
        raise RuntimeError("Review native source scheduling and identical snapshot policy first")
    change(job,completed=1,stage="Acquire content maintenance")
    content_guard("begin",job)
    try:
        check_preparation_identity(job,expected,False)
        change(job,completed=2,stage="Capture new protected Kiwix content snapshot")
        sid=native_snapshot_source(source,seconds=CONTENT_TIMEOUT,protect=True)
        log(job,"\nPre-update protected snapshot: "+sid+"; verification pending.\n")
        _,stats=read_snapshot_manifest(source,sid)
        if stats.get("aftergrid_pinned") is not True:raise RuntimeError("Pre-update native pin not confirmed")
        change(job,completed=3,stage="Read every file from exact protected snapshot")
        count=verify_content_manifest(job,sid,stats)
        _,after=read_snapshot_manifest(source,sid)
        if after.get("aftergrid_pinned") is not True:raise RuntimeError("Pre-update pin no longer confirmed")
        check_preparation_identity(job,expected,False)
        change(job,completed=4,stage="Preserve exact previous Docker image")
        archive=preserve_previous_image(expected["previous_image_id"])
        check_preparation_identity(job,expected,False)
        evidence={**expected,"snapshot_id":sid,"file_objects_read":count,"checked_at":int(time.time()),
                  "pin_confirmed":True,"verification":"read-only","previous_image_archive":archive,
                  "update_performed":False,"reusable_authorization":False}
        if guarded:
            # Save the recovery evidence before any pull. A failed update must
            # never imply success or discard a verified prior image archive.
            evidence["recreation_attempted"]=False
            with db() as conn:
                conn.execute("UPDATE update_preparations SET evidence=? WHERE job=?",(json.dumps(evidence,sort_keys=True),job))
            try:
                guarded_compose_update(job,expected,evidence)
            except Exception:
                if evidence.get("recreation_attempted") is True:
                    evidence["rollback_status"]="attempting"
                    with db() as conn:
                        conn.execute("UPDATE update_preparations SET evidence=? WHERE job=?",(json.dumps(evidence,sort_keys=True),job))
                    try:
                        rollback_reader(job,expected,evidence)
                        log(job,"\nPrevious reader restored and catalog sample confirmed; update remains failed and paused.\n")
                    except Exception:
                        evidence["rollback_status"]="unconfirmed"
                        log(job,"\nReader rollback not confirmed; inspect local image archive, snapshot and rollback hold before further changes.\n")
                    finally:
                        with db() as conn:
                            conn.execute("UPDATE update_preparations SET evidence=? WHERE job=?",(json.dumps(evidence,sort_keys=True),job))
                raise
        change(job,completed=8 if guarded else 5,stage="Release content maintenance")
    finally:
        content_guard("end",job)
    with db() as conn:
        conn.execute("UPDATE update_preparations SET evidence=? WHERE job=?",(json.dumps(evidence,sort_keys=True),job))
    log(job,"\nPrevious image archived: "+expected["previous_image_id"]+("; guarded update verified.\n" if guarded else "; preparation only, no pull or update. Repeat backup and verification inside future guarded update.\n"))
    change(job,completed=9 if guarded else 6,state="succeeded",stage="Guarded reader update verified" if guarded else "Protected preparation and previous image archive verified; no update performed")


def latest_update_preparation():
    with db() as conn:
        row=conn.execute("SELECT j.id,j.state,j.action,j.created,p.evidence FROM jobs j JOIN update_preparations p ON p.job=j.id WHERE j.action IN ('prepare-update','guarded-update') ORDER BY j.id DESC LIMIT 1").fetchone()
    if not row:return None
    return {"job":row["id"],"state":row["state"],"action":row["action"],"created":row["created"],
            "evidence":json.loads(row["evidence"]) if row["evidence"] and (row["state"]=="succeeded" or row["action"]=="guarded-update") else None}


def reader_hold_resolution(report):
    """Local advisory only: never clear the hold or authorize another update."""
    hold=report["rollback_hold"]
    result={"status":"not applicable","failed_job":None,"base_image":None,
            "base_matches_rollback":False,"blockers":[],
            "archive_reverified":False,"pin_reverified":False,"clear_enabled":False}
    if report["recovery_mode"] or hold["status"] not in {"active","invalid"}:return result
    result["status"]="blocked"
    if hold["status"]!="active":
        result["blockers"].append("Invalid rollback override; inspect host")
        return result
    image=hold["image_id"]
    prior=report["latest_guarded_update"]
    evidence=prior.get("evidence") if prior else None
    if prior:result["failed_job"]=prior["id"]
    if (not prior or prior["state"] not in {"failed","interrupted"} or not isinstance(evidence,dict)
        or evidence.get("recreation_attempted") is not True
        or evidence.get("rollback_status")!="restored" or evidence.get("rollback_image_id")!=image
        or evidence.get("previous_image_id")!=image or evidence.get("pin_confirmed") is not True
        or not isinstance(evidence.get("snapshot_id"),str)
        or not re.fullmatch(r"[a-f0-9]{32,64}",evidence["snapshot_id"])
        or not isinstance(evidence.get("previous_image_archive"),dict)
        or evidence["previous_image_archive"].get("image_id")!=image):
        result["blockers"].append("Matching failed update and confirmed rollback evidence required")
    if report["worker_busy"]:result["blockers"].append("Worker jobs active")
    services=report["local_images"]
    if (report["reader_state"]!="running" or not isinstance(services,list) or len(services)!=1
        or services[0].get("configured_image")!=rollback_tag(image)
        or services[0].get("installed_image_ids")!=[image]):
        result["blockers"].append("Exact recovered reader must be running")
    try:
        # Inspect the base Compose definition WITHOUT the recovery override.
        # Never use this command for up, pull or build while the hold exists.
        folder=MODULES/"kiwix"
        raw=subprocess.run(["docker","compose","--project-name","aftergrid-kiwix",
                            "--project-directory",str(folder),"--file",str(folder/"compose.yaml"),
                            "config","--format","json"],env=compose_env("kiwix"),
                           capture_output=True,text=True,timeout=8,check=True).stdout
        definitions=json.loads(raw)["services"]
        target=definitions["kiwix"]["image"]
        if (set(definitions)!={"kiwix"} or not isinstance(target,str)
            or not re.fullmatch(r"ghcr\.io/kiwix/kiwix-serve:[A-Za-z0-9_.-]{1,100}@"+IMAGE_ID_PATTERN,target)):
            raise ValueError("Base Compose target invalid")
        result["base_image"]=target
        exact_local_image(target,image)
        result["base_matches_rollback"]=True
    except (OSError,ValueError,TypeError,KeyError,RuntimeError,subprocess.SubprocessError):
        result["blockers"].append("Reviewed base Compose target must resolve locally to the recovered image")
    if not result["blockers"]:
        result["status"]="local prerequisites met"
        result["clear_enabled"]=True
        result["blockers"].append("Explicit archive, pin and catalog re-verification required before removal")
    return result


def reader_update_health(own_job=0):
    """Read-only local status. No registry request, archive read or job admission."""
    report={"module":"kiwix","observed_at":int(time.time()),"registry_checked":False,
            "archive_reverified":False,"automatic_execution_enabled":False,
            "recovery_mode":RECOVERY_CORE_ONLY or RECOVERY_OFFLINE,
            "rollback_hold":{"status":"not checked"},"blockers":[]}
    if RECOVERY_CORE_ONLY or RECOVERY_OFFLINE:
        report["blockers"].append("Recovery mode disables update execution")
    else:
        try:
            hold=kiwix_rollback_override()
            report["rollback_hold"]={"status":"active","image_id":hold[1]} if hold else {"status":"none"}
            if hold:report["blockers"].append("Previous reader rollback hold; operator review required")
        except (OSError,ValueError,TypeError):
            report["rollback_hold"]={"status":"invalid"}
            report["blockers"].append("Invalid reader rollback hold; inspect host")
    try:
        candidate=approved_update_candidate("kiwix")
        report["approved_candidate"]=candidate["image"] if candidate else None
        if not candidate:report["blockers"].append("No approved update candidate")
    except (OSError,ValueError,TypeError):
        report["approved_candidate"]=None
        report["blockers"].append("Reviewed candidate file invalid")
    def attempt(row):
        if not row:return None
        result={k:row[k] for k in ("id","action","state","stage","created")}
        result["evidence"]=None
        if row["evidence"] and (row["state"]=="succeeded" or row["action"]=="guarded-update"):
            try:
                e=json.loads(row["evidence"])
                if not isinstance(e,dict):raise ValueError("Invalid evidence")
                # Explicit allowlist; no logs, paths or raw environment.
                result["evidence"]={k:e[k] for k in ("candidate","platform","previous_image_id","target_image_id",
                    "snapshot_id","pin_confirmed","verification","file_objects_read","checked_at",
                    "previous_image_archive","recreation_attempted","update_performed","result_image_id",
                    "catalog_sample_matched","rollback_status","rollback_image_id","rollback_checked_at","resolution_job","resolution_checked_at") if k in e}
                archive=result["evidence"].get("previous_image_archive")
                if isinstance(archive,dict):
                    result["evidence"]["previous_image_archive"]={k:archive[k] for k in ("image_id","sha256","bytes") if k in archive}
                elif archive is not None:result["evidence"].pop("previous_image_archive")
            except (ValueError,TypeError):
                result["evidence_invalid"]=True
        return result
    with db() as conn:
        for key,action in (("latest_preparation","prepare-update"),("latest_guarded_update","guarded-update"),("latest_manual_update","update")):
            row=conn.execute("SELECT j.id,j.action,j.state,j.stage,j.created,p.evidence FROM jobs j LEFT JOIN update_preparations p ON p.job=j.id WHERE j.module='kiwix' AND j.action=? ORDER BY j.id DESC LIMIT 1",(action,)).fetchone()
            report[key]=attempt(row)
        report["worker_busy"]=bool(conn.execute("SELECT 1 FROM jobs WHERE state IN ('queued','running') AND id!=? LIMIT 1",(own_job,)).fetchone())
        report["unresolved_guarded_update"]=unresolved_guarded_update(conn)
    guarded=report["latest_guarded_update"]
    if report["unresolved_guarded_update"]:
        report["blockers"].append("Unresolved guarded update; no automatic retry")
    manual=report["latest_manual_update"]
    if manual and manual["state"] in {"failed","interrupted"}:
        report["blockers"].append("Latest manual update requires review")
    if report["worker_busy"]:report["blockers"].append("Worker jobs active")
    report["reader_state"]="unavailable"
    report["local_images"]=None
    if not RECOVERY_CORE_ONLY:
        try:
            report["reader_state"]=state("kiwix")
            services=version_report("kiwix")["services"]
            if not isinstance(services,list) or len(services)!=1 or services[0]["service"]!="kiwix":
                raise ValueError("Expected one reviewed reader service")
            report["local_images"]=services
        except (RuntimeError,OSError,ValueError,TypeError,KeyError):pass
        if report["local_images"] is None:
            report["blockers"].append("Local reader image identity unavailable")
        elif report["reader_state"]=="running" and len(report["local_images"][0]["installed_image_ids"])!=1:
            report["blockers"].append("Running reader image identity not confirmed")
    if report["reader_state"]!="running":report["blockers"].append("Reader not confirmed running and ready")
    report["rollback_resolution"]=reader_hold_resolution(report)
    return report


def enqueue_reader_resolution(request):
    if (RECOVERY_CORE_ONLY or RECOVERY_OFFLINE or not isinstance(request,dict)
        or set(request)!={"failed_job","image_id"} or type(request["failed_job"]) is not int
        or request["failed_job"]<=0 or not isinstance(request["image_id"],str)
        or not re.fullmatch(IMAGE_ID_PATTERN,request["image_id"])):
        raise ValueError("Invalid rollback resolution request")
    hold=kiwix_rollback_override()
    if not hold or hold[1]!=request["image_id"]:raise ValueError("Matching rollback hold required")
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute("SELECT 1 FROM jobs WHERE state IN ('queued','running') LIMIT 1").fetchone():
            raise sqlite3.IntegrityError("Worker busy")
        latest=conn.execute("SELECT id,state FROM jobs WHERE module='kiwix' AND action='guarded-update' ORDER BY id DESC LIMIT 1").fetchone()
        if not latest or latest["id"]!=request["failed_job"] or latest["state"] not in {"failed","interrupted"}:
            raise ValueError("Matching failed guarded update required")
        row=conn.execute("INSERT INTO jobs(module,action,state,stage,created) VALUES ('kiwix','resolve-rollback','queued','Queued',?)",(int(time.time()),))
        conn.execute("INSERT INTO update_preparations(job,request) VALUES (?,?)",(row.lastrowid,json.dumps(request,sort_keys=True)))
        return row.lastrowid


def resolve_reader_hold(job):
    if RECOVERY_CORE_ONLY or RECOVERY_OFFLINE:raise ValueError("Rollback resolution unavailable")
    change(job,state="running",total=5,completed=0,stage="Recheck rollback resolution prerequisites")
    with db() as conn:
        request=json.loads(conn.execute("SELECT request FROM update_preparations WHERE job=?",(job,)).fetchone()["request"])
        row=conn.execute("SELECT evidence FROM update_preparations WHERE job=?",(request["failed_job"],)).fetchone()
        evidence=json.loads(row["evidence"]) if row else None
    def preflight():
        report=reader_update_health(job)
        result=report["rollback_resolution"]
        if (result["status"]!="local prerequisites met" or result["failed_job"]!=request["failed_job"]
            or report["rollback_hold"].get("image_id")!=request["image_id"]):
            raise RuntimeError("Rollback resolution prerequisites not met")
        return result["base_image"]
    base=preflight()
    image=request["image_id"]
    change(job,completed=1,stage="Acquire content maintenance")
    content_guard("begin",job)
    try:
        if preflight()!=base:raise RuntimeError("Reviewed base changed")
        fingerprint=reader_compose_fingerprint()
        folder=STATE/"previous-images"/("kiwix-"+image.split(":")[1])
        change(job,completed=2,stage="Reverify exact previous image archive")
        if verify_previous_archive(folder,image)!=evidence["previous_image_archive"]:
            raise RuntimeError("Previous image archive differs")
        sid=evidence["snapshot_id"]
        change(job,completed=3,stage="Reverify protected native snapshot and recovered catalog")
        _,stats=read_snapshot_manifest(CONTENT_SOURCES["kiwix"],sid)
        if stats.get("aftergrid_pinned") is not True:raise RuntimeError("Protected recovery snapshot unavailable")
        verify_content_manifest(job,sid,stats)
        _,after=read_snapshot_manifest(CONTENT_SOURCES["kiwix"],sid)
        if after.get("aftergrid_pinned") is not True:raise RuntimeError("Protected recovery snapshot unavailable")
        sample=kiwix_catalog_sample()
        if hashlib.sha256(json.dumps(sample).encode()).hexdigest()!=evidence["catalog_sample_sha256"]:
            raise RuntimeError("Recovered catalog differs from pre-update evidence")
        if preflight()!=base or reader_compose_fingerprint()!=fingerprint:raise RuntimeError("Reviewed base changed")
        hold=kiwix_rollback_override()
        if not hold or hold[1]!=image:raise RuntimeError("Rollback hold changed")
        # Record intent before removing the override. A crash before successful
        # job completion leaves the original failed update unresolved.
        evidence.update(resolution_job=job,resolution_checked_at=int(time.time()))
        with db() as conn:
            conn.execute("UPDATE update_preparations SET evidence=? WHERE job=?",(json.dumps(evidence,sort_keys=True),request["failed_job"]))
        change(job,completed=4,stage="Remove verified local override; no container recreation")
        hold[0].unlink()
        fd=os.open(STATE,os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
    finally:content_guard("end",job)
    change(job,completed=5,state="succeeded",stage="Rollback hold resolved; original failed update retained")


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

def exact_verification_source(job):
    with db() as conn:
        row=conn.execute("SELECT source_job FROM exact_verifications WHERE job=?",(job,)).fetchone()
    return row["source_job"] if row else None


def protected_snapshot_requested(job):
    with db() as conn:
        return conn.execute("SELECT 1 FROM protected_snapshots WHERE job=?",(job,)).fetchone() is not None

def execute(row):
    job, ident, action = row["id"], row["module"], row["action"]
    switch_attempted=False
    try:
        if action=="resolve-rollback":
            if ident!="kiwix":raise ValueError("Unsupported rollback resolution")
            resolve_reader_hold(job)
            return
        if action in {"prepare-update","guarded-update"}:
            if ident!="kiwix" or ident not in catalog():raise ValueError("Unsupported update preparation")
            prepare_update(job,guarded=action=="guarded-update")
            return
        if action=="set-retention":
            if ident!="kopia" or ident not in catalog():raise ValueError("Unsupported retention job")
            apply_retention(job)
            return
        if ident not in catalog() or action not in ACTIONS or (action in ROUTING_ACTIONS and ident!="routing"):
            raise ValueError("Unsupported job")
        if RECOVERY_OFFLINE:offline_admission(ident,action)
        kiwix_lifecycle_admission(ident,action)
        pin_args={}
        if action in {"snapshot","core-snapshot","worker-snapshot","content-snapshot"} and protected_snapshot_requested(job):
            if RECOVERY_OFFLINE or ident=="tak":raise ValueError("Protected capture unavailable")
            pin_args={"protect":True}
        exact_args=()
        if action in {"verify-snapshot","core-verify-snapshot","worker-verify-snapshot","content-verify"}:
            exact=exact_verification_source(job)
            if exact is not None:
                if RECOVERY_OFFLINE or ident=="tak":raise ValueError("Exact scheduled verification unavailable")
                exact_args=(exact,)
        if action=="recovery-manifest":
            if ident!="kopia":raise ValueError("Kopia-only action")
            recovery_manifest(job)
            return
        if action=="content-snapshot":
            content_snapshot(job,ident,**pin_args)
            return
        if action=="content-verify":
            verify_content(job,ident,*exact_args)
            return
        if action=="worker-verify-snapshot":
            if ident!="kopia":raise ValueError("Kopia-only action")
            verify_snapshot(job,"worker",*exact_args)
            return
        if action=="worker-snapshot":
            if ident!="kopia":raise ValueError("Kopia-only action")
            worker_snapshot(job,**pin_args)
            return
        if action=="core-verify-snapshot":
            if ident!="kopia":raise ValueError("Kopia-only action")
            verify_snapshot(job,"core",*exact_args)
            return
        if action=="core-snapshot":
            if ident!="kopia":raise ValueError("Kopia-only action")
            core_snapshot(job,**pin_args)
            return
        if action=="snapshot":
            snapshot_application(job,ident,**pin_args)
            return
        if action=="verify-snapshot":
            verify_snapshot(job,ident,*exact_args)
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
    if RECOVERY_CORE_ONLY:return
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
        if self.path=="/recovery-manifest":
            try:return self.send_json(200,load_recovery_manifest())
            except RuntimeError:return self.send_json(404,{"detail":"No confirmed recovery inventory; generate one first"})
        if self.path=="/kopia/status":
            return self.send_json(200,kopia_status())
        if self.path=="/backup-health":
            try:return self.send_json(200,backup_health())
            except (RuntimeError,OSError,ValueError,TypeError,KeyError,sqlite3.Error):
                return self.send_json(503,{"detail":"Recorded backup health unavailable"})
        if self.path=="/backup-policy/sources":
            return self.send_json(200,sorted(backup_policy_sources()))
        if self.path.startswith("/backup-policy/effective/"):
            key=self.path.removeprefix("/backup-policy/effective/")
            if key not in backup_policy_sources():return self.send_json(404,{"detail":"Unknown reviewed policy source"})
            try:return self.send_json(200,native_policy_summary(key))
            except RuntimeError:return self.send_json(503,{"detail":"Native effective policy unavailable; connect Kopia first"})
        if self.path.startswith("/backup-plan/"):
            ident=self.path.removeprefix("/backup-plan/")
            if ident not in catalog():return self.send_json(404,{"detail":"Unknown module"})
            try:return self.send_json(200,backup_plan(ident))
            except RuntimeError:return self.send_json(503,{"detail":"Reviewed backup sources unavailable"})
        if self.path=="/update-health/kiwix":
            try:return self.send_json(200,reader_update_health())
            except (RuntimeError,OSError,ValueError,TypeError,KeyError,sqlite3.Error):
                return self.send_json(503,{"detail":"Recorded update health unavailable"})
        if self.path=="/update-preparation/kiwix":
            return self.send_json(200,{"latest":latest_update_preparation()})
        if self.path.startswith("/update-eligibility/"):
            ident=self.path.removeprefix("/update-eligibility/")
            if ident not in catalog():return self.send_json(404,{"detail":"Unknown module"})
            return self.send_json(200,update_eligibility(ident))
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
        if RECOVERY_CORE_ONLY:
            return self.send_json(409,{"detail":"Core-only recovery disables module actions"})
        if self.path not in {"/jobs", "/jobs/batch", "/registry-check", "/backup-policy/retention", "/update-eligibility", "/update-preparation", "/guarded-update", "/resolve-rollback"}:
            return self.send_json(404, {"detail": "Unknown endpoint"})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 2048:
                raise ValueError("Invalid request length")
            body = json.loads(self.rfile.read(size))
            if self.path=="/resolve-rollback":
                return self.send_json(202,{"id":enqueue_reader_resolution(body)})
            if self.path in {"/update-preparation","/guarded-update"}:
                return self.send_json(202,{"id":enqueue_update_preparation(body,guarded=self.path=="/guarded-update")})
            if self.path=="/update-eligibility":
                if not isinstance(body,dict) or set(body)!={"module"} or body["module"]!="kiwix":
                    raise ValueError("Unsupported update pilot")
                return self.send_json(200,update_eligibility("kiwix",online=True))
            if self.path=="/backup-policy/retention":
                return self.send_json(202,{"id":enqueue_retention(body)})
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
            elif set(body)=={"module","action","protect"}:
                if body["protect"] is not True:raise ValueError("Explicit pin confirmation required")
            elif set(body)=={"module","action","source_job"}:
                if type(body["source_job"]) is not int or body["source_job"]<=0:
                    raise ValueError("Invalid source job")
            elif set(body)!={"module","action"}:
                raise ValueError("Invalid request")
            job = enqueue(body["module"],body["action"],body.get("backup_confirmed",False),body.get("source_job"),body.get("protect",False))
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
