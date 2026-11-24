"""Small local portal. No Docker access or external identity dependencies."""
import hashlib
import hmac
import json
import ipaddress
import os
import re
import secrets
import sqlite3
import threading
import time
from collections import deque
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

try:
    from .worker_client import call, WorkerUnavailable
    from .content import search_catalog, local_inventory, CatalogUnavailable
    from .downloads import Downloads
except ImportError:
    from worker_client import call, WorkerUnavailable
    from content import search_catalog, local_inventory, CatalogUnavailable
    from downloads import Downloads

ROOT = Path(__file__).parent
COOKIE = "aftergrid_session"
TTL = 12 * 60 * 60
CATALOG = [
    ("kiwix", "Kiwix", "Offline knowledge", "Knowledge"),
    ("homebox", "Homebox", "Equipment, storage and QR labels", "Inventory"),
    ("grocy", "Grocy", "Consumables and recipes", "Inventory"),
    ("kopia", "Kopia", "Encrypted backups", "System"),
    ("maps", "Offline maps and routing", "Regional maps and navigation", "Navigation"),
    ("meshtastic", "Meshtastic", "LoRa communications", "Communications"),
    ("meshcore", "MeshCore", "Mesh communications", "Communications"),
    ("tak", "TAK", "Shared situational awareness", "Communications"),
    ("kolibri", "Kolibri", "Offline education", "Knowledge"),
    ("media", "Media library", "Offline videos and manuals", "Knowledge"),
    ("notes", "Notes and PACE", "Shared emergency plans", "Preparedness"),
]

class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)

class Setup(Credentials):
    token: str = Field(min_length=1, max_length=128)
    server_name: str = Field(default="AfterGrid", min_length=1, max_length=80)

class Selection(BaseModel):
    modules: list[str] = Field(default_factory=list, max_length=12)

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

def password_hash(password, salt):
    return hashlib.scrypt(password.encode(), salt=salt, n=32768, r=8, p=1, maxmem=64*1024*1024).hex()

def create_app(data_dir=None):
    data = Path(data_dir or os.environ.get("AFTERGRID_DATA", "./data/core"))
    secure_cookie = os.environ.get("AFTERGRID_SECURE_COOKIE", "false").lower() == "true"
    configured_origin = os.environ.get("AFTERGRID_ORIGIN", "").rstrip("/")
    downloads = Downloads(data, os.environ.get("AFTERGRID_KIWIX_CONTENT","/content/kiwix"))
    attempts = deque()
    lock = threading.Lock()

    @contextmanager
    def db():
        con = sqlite3.connect(data / "core.sqlite3", timeout=10)
        con.row_factory = sqlite3.Row
        try:
            with con:
                yield con
        finally:
            con.close()

    @asynccontextmanager
    async def lifespan(_):
        data.mkdir(parents=True, exist_ok=True)
        with db() as con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS admin (
                    id INTEGER PRIMARY KEY CHECK(id=1), username TEXT NOT NULL,
                    salt TEXT NOT NULL, password_hash TEXT NOT NULL, server_name TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY, expires INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS first_run (
                    id INTEGER PRIMARY KEY CHECK(id=1), token TEXT NOT NULL,
                    selection TEXT, result TEXT);
            """)
            con.execute("INSERT OR IGNORE INTO first_run(id,token) VALUES (1,?)", (secrets.token_hex(24),))
        downloads.start()
        try:
            yield
        finally:
            downloads.close()

    api = FastAPI(title="AfterGrid", version="0.3.5-dev", lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)

    @api.middleware("http")
    async def security(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        return response

    def same_origin(request):
        expected = configured_origin or f"{request.url.scheme}://{request.headers.get('host', '')}"
        if request.headers.get("origin") != expected:
            raise HTTPException(403, "Same-origin request required")

    def rate_limit():
        # Bounded global throttle for a small trusted-LAN appliance.
        now = time.monotonic()
        with lock:
            while attempts and attempts[0] <= now - 60:
                attempts.popleft()
            if len(attempts) >= 8:
                raise HTTPException(429, "Too many attempts; try again in a minute")
            attempts.append(now)

    def admin_session(request):
        token = request.cookies.get(COOKIE, "")
        if not token or len(token) > 128:
            return False
        with db() as con:
            return con.execute("SELECT 1 FROM sessions WHERE token_hash=? AND expires>?",
                               (digest(token), int(time.time()))).fetchone() is not None

    def issue_session(response, con):
        token = secrets.token_urlsafe(32)
        now = int(time.time())
        con.execute("DELETE FROM sessions WHERE expires<=?", (now,))
        con.execute("INSERT INTO sessions VALUES (?,?)", (digest(token), now+TTL))
        response.set_cookie(COOKIE, token, httponly=True, samesite="strict",
                            secure=secure_cookie, max_age=TTL, path="/")

    @api.get("/")
    def index():
        return FileResponse(ROOT / "index.html")

    @api.get("/style.css")
    def style():
        return FileResponse(ROOT / "style.css", media_type="text/css")

    @api.get("/app.js")
    def javascript():
        return FileResponse(ROOT / "app.js", media_type="text/javascript")

    @api.get("/health")
    def health():
        with db() as con:
            con.execute("SELECT 1")
        return {"status": "ok"}

    @api.get("/api/status")
    def status(request: Request):
        with db() as con:
            row = con.execute("SELECT server_name FROM admin WHERE id=1").fetchone()
            first = con.execute("SELECT result FROM first_run WHERE id=1").fetchone()
        is_admin = admin_session(request)
        return {"setup_required": row is None, "admin": is_admin,
                "selection_pending": bool(is_admin and first["result"] is None),
                "server_name": row["server_name"] if row else "AfterGrid",
                "version": "0.3.5-dev"}

    @api.get("/api/modules")
    def modules():
        result = [{"id": i, "name": n, "description": d, "category": c,
                   "status": "planned", "installable": False} for i,n,d,c in CATALOG]
        try:
            code, installed = call("/modules")
            if code == 200:
                by_id = {item["id"]: item for item in result}
                for m in installed:
                    item = {key: m[key] for key in ("id", "name", "description", "category", "status", "port")}
                    item["installable"] = True
                    item.update(loopback_only=m.get("loopback_only", False), admin_only=m.get("admin_only", False), setup_note=m.get("setup_note", ""), share_available=m.get("share_available", False), shared=m.get("shared", False), lan_url=m.get("lan_url", ""), registration_closed=m.get("registration_closed", False), lan_dns=m.get("lan_dns", False))
                    by_id[m["id"]] = item
                result = list(by_id.values())
        except WorkerUnavailable:
            pass
        return result

    def require_admin(request):
        if not admin_session(request):
            raise HTTPException(401, "Administrator login required")

    @api.get("/api/admin/content/downloads")
    def content_downloads(request: Request):
        require_admin(request)
        return downloads.list()

    class DownloadRequest(BaseModel):
        key: str = Field(min_length=1,max_length=400)

    @api.post("/api/admin/content/downloads",status_code=202)
    def content_download(payload: DownloadRequest,request: Request):
        require_admin(request)
        same_origin(request)
        try:
            downloads.enqueue(payload.key)
        except (ValueError,sqlite3.IntegrityError) as exc:
            raise HTTPException(400,str(exc))
        return {"queued":True}

    @api.get("/api/admin/content/local")
    def content_local(request: Request):
        require_admin(request)
        try:
            return local_inventory(os.environ.get("AFTERGRID_KIWIX_CONTENT","/content/kiwix"))
        except OSError:
            raise HTTPException(503,"Local content storage unavailable")

    @api.get("/api/admin/content/catalog")
    def content_catalog(request: Request, q: str = "", lang: str = "eng", start: int = 0):
        require_admin(request)
        if len(q)>100 or not 0<=start<=10000:
            raise HTTPException(400,"Invalid catalog query")
        try:
            return search_catalog(q,lang,start)
        except ValueError as exc:
            raise HTTPException(400,str(exc))
        except CatalogUnavailable as exc:
            raise HTTPException(503,str(exc))

    @api.post("/api/admin/first-run", status_code=202)
    def first_run(payload: Selection, request: Request):
        require_admin(request)
        same_origin(request)
        selected = payload.modules
        if len(set(selected)) != len(selected) or any(not re.fullmatch(r"[a-z][a-z0-9-]{0,39}",i) for i in selected):
            raise HTTPException(400, "Invalid module selection")
        canonical = json.dumps(sorted(selected))
        with db() as con:
            con.execute("BEGIN IMMEDIATE")
            saved = con.execute("SELECT * FROM first_run WHERE id=1").fetchone()
            if saved["result"] is not None:
                if saved["selection"] != canonical:
                    raise HTTPException(409, "Initial selection already saved; use the application catalog")
                return json.loads(saved["result"])
            if selected:
                try:
                    code, result = call("/jobs/batch", {"token":saved["token"],"modules":selected})
                except WorkerUnavailable:
                    raise HTTPException(503, "Module manager unavailable; retry the same selection")
                if code != 202:
                    raise HTTPException(code if code in {400,409} else 502, result.get("detail","Module manager request failed"))
            else:
                result = {"ids":[]}
            con.execute("UPDATE first_run SET selection=?,result=? WHERE id=1", (canonical,json.dumps(result)))
            return result

    @api.get("/api/admin/jobs")
    def list_jobs(request: Request):
        require_admin(request)
        try:
            code, result = call("/jobs")
        except WorkerUnavailable:
            raise HTTPException(503, "Module manager unavailable")
        if code != 200:
            raise HTTPException(502, "Module manager request failed")
        return result

    def local_credential_origin():
        origin = urlsplit(configured_origin)
        host = origin.hostname or ""
        if secure_cookie and origin.scheme == "https":
            return True
        if origin.scheme != "http":
            return False
        if host == "localhost" or host == "127.0.0.1" or host.endswith(".home.arpa"):
            return True
        try:
            addr = ipaddress.IPv4Address(host)
            return any(addr in ipaddress.IPv4Network(n) for n in ("10.0.0.0/8","172.16.0.0/12","192.168.0.0/16"))
        except ValueError:
            return False

    @api.post("/api/admin/kopia/credentials")
    def kopia_credentials(request: Request):
        require_admin(request)
        same_origin(request)
        if not local_credential_origin():
            raise HTTPException(403, "Use the configured private LAN or trusted HTTPS portal to reveal credentials")
        try:
            code, result = call("/credentials/kopia")
        except WorkerUnavailable:
            raise HTTPException(503, "Module manager unavailable")
        if code != 200:
            raise HTTPException(code if code == 404 else 502, result.get("detail", "Module manager request failed"))
        return result

    @api.post("/api/admin/modules/{ident}/{action}", status_code=202)
    def module_action(ident: str, action: str, request: Request):
        require_admin(request)
        same_origin(request)
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,39}", ident) or action not in {"install","start","stop","restart","update","uninstall","share","unshare"}:
            raise HTTPException(400, "Unsupported module or action")
        try:
            code, result = call("/jobs", {"module": ident, "action": action})
        except WorkerUnavailable:
            raise HTTPException(503, "Module manager unavailable")
        if code != 202:
            raise HTTPException(code if code in {400,409} else 502, result.get("detail", "Module manager request failed"))
        return result

    @api.post("/api/setup", status_code=201)
    def setup(payload: Setup, request: Request, response: Response):
        same_origin(request)
        rate_limit()
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", payload.username):
            raise HTTPException(400, "Use letters, numbers, dots, hyphens or underscores")
        if len(payload.password) < 12 or not payload.server_name.strip():
            raise HTTPException(400, "Use a nonempty server name and a password of at least 12 characters")
        with db() as con:
            con.execute("BEGIN IMMEDIATE")
            if con.execute("SELECT 1 FROM admin").fetchone():
                raise HTTPException(409, "Already configured")
            try:
                token = (data / "setup-token").read_text().strip()
            except OSError:
                raise HTTPException(503, "Setup token unavailable; see installation instructions")
            if not token or not hmac.compare_digest(token.encode(), payload.token.encode()):
                raise HTTPException(403, "Invalid setup token")
            salt = secrets.token_bytes(16)
            con.execute("INSERT INTO admin VALUES (1,?,?,?,?)",
                        (payload.username, salt.hex(), password_hash(payload.password,salt),
                         payload.server_name.strip()))
            issue_session(response, con)
        # The token is invalid once the admin exists, even if unlink fails.
        try:
            (data / "setup-token").unlink()
        except OSError:
            pass
        return {"ok": True}

    @api.post("/api/login")
    def login(payload: Credentials, request: Request, response: Response):
        same_origin(request)
        rate_limit()
        with db() as con:
            row = con.execute("SELECT * FROM admin WHERE id=1").fetchone()
            salt = bytes.fromhex(row["salt"]) if row else b"\x00"*16
            calculated = password_hash(payload.password,salt)
            if not row or not hmac.compare_digest(calculated,row["password_hash"]) or payload.username != row["username"]:
                raise HTTPException(401, "Invalid username or password")
            issue_session(response,con)
        return {"ok": True}

    @api.post("/api/logout")
    def logout(request: Request, response: Response):
        same_origin(request)
        with db() as con:
            token = request.cookies.get(COOKIE,"")
            if token and len(token)<=128:
                con.execute("DELETE FROM sessions WHERE token_hash=?", (digest(token),))
        response.delete_cookie(COOKIE,path="/",secure=secure_cookie,httponly=True,samesite="strict")
        return {"ok": True}

    @api.get("/api/admin/status")
    def admin_status(request: Request):
        if not admin_session(request):
            raise HTTPException(401,"Administrator login required")
        return {"core":"running","module_manager":"compose-worker"}

    return api

app = create_app()
