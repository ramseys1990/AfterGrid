"""Small, privileged Compose worker. Only reviewed manifests and fixed actions."""
import http.server
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
import urllib.request
import urllib.error
from contextlib import contextmanager
from pathlib import Path

MODULES = Path("/modules")
STATE = Path("/worker-state")
SOCKET = Path("/run/aftergrid/worker.sock")
ACTIONS = {"install", "start", "stop", "restart", "update", "uninstall", "share", "unshare"}
ROOT = os.environ.get("AFTERGRID_ROOT", "/opt/aftergrid")
BIND = os.environ.get("AFTERGRID_BIND", "127.0.0.1")
LAN_BIND = os.environ.get("AFTERGRID_LAN_BIND") or BIND
LAN_DOMAIN = os.environ.get("AFTERGRID_LAN_DOMAIN", "")
MAX_LOG = 24000
SECRET_LOCK = threading.Lock()

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
    return f"http://{host}:{manifest['port']}"

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

def enqueue(ident, action):
    manifest = catalog().get(ident)
    if not manifest or action not in ACTIONS:
        raise ValueError("Unsupported module or action")
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

def execute(row):
    job, ident, action = row["id"], row["module"], row["action"]
    try:
        if ident not in catalog() or action not in ACTIONS:
            raise ValueError("Unsupported job")
        steps = stages(action)
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
            if argv is None:
                wait_ready(ident)
            else:
                run(job, ident, *argv)
            change(job, completed=index+1)
        change(job, state="succeeded", stage="Complete")
    except Exception as exc:
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
        if self.path == "/credentials/kopia" and "kopia" in catalog():
            if not (STATE / "secrets" / "kopia.json").is_file():
                return self.send_json(404, {"detail": "Install Kopia first"})
            values = module_secrets("kopia")
            return self.send_json(200, {"username": "aftergrid", "ui_password": values["KOPIA_UI_PASSWORD"], "repository_password": values["KOPIA_PASSWORD"]})
        self.send_json(404, {"detail": "Unknown endpoint"})

    def do_POST(self):
        if self.path not in {"/jobs", "/jobs/batch"}:
            return self.send_json(404, {"detail": "Unknown endpoint"})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 2048:
                raise ValueError("Invalid request length")
            body = json.loads(self.rfile.read(size))
            if self.path == "/jobs/batch":
                if not isinstance(body,dict) or set(body) != {"token","modules"}:
                    raise ValueError("Invalid batch")
                return self.send_json(202, {"ids": enqueue_batch(body["token"],body["modules"])})
            if not isinstance(body, dict) or set(body) != {"module", "action"} or not all(isinstance(v,str) for v in body.values()):
                raise ValueError("Invalid request")
            job = enqueue(body["module"], body["action"])
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
