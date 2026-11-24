"""Small local portal. No Docker access or external identity dependencies."""
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import threading
import time
from collections import deque
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

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

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

def password_hash(password, salt):
    return hashlib.scrypt(password.encode(), salt=salt, n=32768, r=8, p=1, maxmem=64*1024*1024).hex()

def create_app(data_dir=None):
    data = Path(data_dir or os.environ.get("AFTERGRID_DATA", "./data/core"))
    secure_cookie = os.environ.get("AFTERGRID_SECURE_COOKIE", "false").lower() == "true"
    configured_origin = os.environ.get("AFTERGRID_ORIGIN", "").rstrip("/")
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
            """)
        yield

    api = FastAPI(title="AfterGrid", version="0.1.0-dev", lifespan=lifespan,
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
        return {"setup_required": row is None, "admin": admin_session(request),
                "server_name": row["server_name"] if row else "AfterGrid",
                "version": "0.1.0-dev"}

    @api.get("/api/modules")
    def modules():
        return [{"id": i, "name": n, "description": d, "category": c,
                 "status": "planned"} for i,n,d,c in CATALOG]

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
        return {"core":"running","module_manager":"planned"}

    return api

app = create_app()
