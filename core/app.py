"""Small local portal. No Docker access or external identity dependencies."""
import asyncio
import hashlib
import stat
import tempfile
import hmac
import json
import ipaddress
import os
import re
import secrets
import sqlite3
import threading
import time
import xml.etree.ElementTree as ET
from collections import deque
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

try:
    from .worker_client import call, WorkerUnavailable
    from .content import search_catalog, local_inventory, CatalogUnavailable
    from .content_backup_guard import content_admission
    from .backup_schedule import BackupSchedules, SOURCES as SCHEDULE_SOURCES, INTERVALS as SCHEDULE_INTERVALS
    from .update_preferences import UpdatePreferences
    from .downloads import Downloads
    from .households import Households
    from .inventory import Inventory, InventoryError
    from .map_downloads import MapDownloads
    from .routing import route, RouteError
    from .waypoints import MapPlans
    from .routing_downloads import RoutingDownloads
    from .place_search import PlaceSearch
    from .communications import Communications
except ImportError:
    from worker_client import call, WorkerUnavailable
    from content import search_catalog, local_inventory, CatalogUnavailable
    from content_backup_guard import content_admission
    from backup_schedule import BackupSchedules, SOURCES as SCHEDULE_SOURCES, INTERVALS as SCHEDULE_INTERVALS
    from update_preferences import UpdatePreferences
    from downloads import Downloads
    from households import Households
    from inventory import Inventory, InventoryError
    from map_downloads import MapDownloads
    from routing import route, RouteError
    from waypoints import MapPlans
    from routing_downloads import RoutingDownloads
    from place_search import PlaceSearch
    from communications import Communications

ROOT = Path(__file__).parent
COOKIE = "aftergrid_session"
TTL = 12 * 60 * 60
CATALOG = [
    ("kiwix", "Kiwix", "Offline knowledge", "Knowledge"),
    ("homebox", "Homebox", "Equipment, storage and QR labels", "Inventory"),
    ("grocy", "Grocy", "Consumables and recipes", "Inventory"),
    ("kopia", "Kopia", "Encrypted backups", "System"),
    ("maps", "Offline maps and routing", "Regional maps and navigation", "Navigation"),
    ("meshmonitor", "MeshMonitor (Meshtastic / MeshCore)", "Local mesh communications", "Communications"),
    ("tak", "MicroTAK server", "Local certificate-authenticated TAK", "Communications"),
    ("kolibri", "Kolibri", "Offline education", "Knowledge"),
    ("media", "Jellyfin media library", "Offline videos and audio", "Knowledge"),
    ("notes", "DokuWiki documents and notes", "Shared emergency documents and procedures", "Preparedness"),
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
    recovery_core_only = os.environ.get("AFTERGRID_RECOVERY_CORE_ONLY") == "1"
    recovery_offline = os.environ.get("AFTERGRID_RECOVERY_OFFLINE") == "1"
    downloads = Downloads(data, os.environ.get("AFTERGRID_KIWIX_CONTENT","/content/kiwix"))
    households = Households(data)
    inventory = Inventory(data)
    plans = MapPlans(data)
    comms = Communications(data)
    routing_data = RoutingDownloads(data,os.environ.get('AFTERGRID_ROUTING_CONTENT','/content/routing'))
    maps = MapDownloads(data,os.environ.get('AFTERGRID_MAP_CONTENT','/content/maps'))
    places = PlaceSearch(data,routing_data.content)
    attempts = deque()
    lock = threading.Lock()
    mutation_lock = asyncio.Lock()
    maintenance_path = data / "recovery-maintenance.json"
    schedules = BackupSchedules(data)
    update_preferences = UpdatePreferences(data)

    def maintenance():
        try:
            info=maintenance_path.lstat()
        except FileNotFoundError:
            return None
        if not stat.S_ISREG(info.st_mode) or not 0<info.st_size<=8192:
            raise ValueError("Invalid maintenance marker")
        value=json.loads(maintenance_path.read_text())
        if value.get("format")!=1 or value.get("phase") not in {"capturing","sealed","updating"}:
            raise ValueError("Invalid maintenance marker")
        return value

    def save_maintenance(value):
        fd,tmp=tempfile.mkstemp(prefix=".recovery-maintenance-",dir=data)
        try:
            with os.fdopen(fd,"w") as out:
                json.dump(value,out,sort_keys=True)
                out.flush()
                os.fsync(out.fileno())
            os.replace(tmp,maintenance_path)
            directory_fd=os.open(data,os.O_RDONLY|os.O_DIRECTORY)
            try:os.fsync(directory_fd)
            finally:os.close(directory_fd)
        finally:Path(tmp).unlink(missing_ok=True)

    def maintenance_owner(request,value):
        return hmac.compare_digest(digest(request.cookies.get(COOKIE,"")),value.get("owner","")) and admin_session(request)

    @contextmanager
    def db():
        con = sqlite3.connect(data / "core.sqlite3", timeout=10)
        con.row_factory = sqlite3.Row
        try:
            with con:
                yield con
        finally:
            con.close()

    async def schedule_loop(stop):
        # Only the existing single-process portal admits managed work.
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(),timeout=30)
                break
            except asyncio.TimeoutError:
                pass
            async with mutation_lock:
                try:
                    if maintenance() is None:
                        await asyncio.to_thread(schedules.tick,call,maintenance_idle)
                        await asyncio.to_thread(update_preferences.tick,call,maintenance_idle)
                except (HTTPException,WorkerUnavailable,OSError,ValueError,TypeError,KeyError,sqlite3.Error):
                    # Fail closed; never schedule on a corrupt file or busy host.
                    continue

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
        households.init()
        inventory.init()
        downloads.start()
        plans.init()
        comms.init()
        maps.start()
        routing_data.start()
        stop_schedules=asyncio.Event()
        scheduler=None if recovery_core_only or recovery_offline else asyncio.create_task(schedule_loop(stop_schedules))
        try:
            yield
        finally:
            stop_schedules.set()
            if scheduler is not None:await scheduler
            places.close()
            routing_data.close()
            maps.close()
            downloads.close()

    api = FastAPI(title="AfterGrid", version="0.8.26-dev", lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)

    api.mount("/map-assets", StaticFiles(directory=ROOT / "map-assets", check_dir=False), name="map-assets")

    @api.middleware("http")
    async def security(request, call_next):
        path=request.url.path
        lifecycle=bool(re.fullmatch(r"/api/admin/modules/[a-z][a-z0-9-]{0,39}/(?:start|stop|restart|uninstall|share|unshare)",path))
        backup_post=bool(re.fullmatch(r"/api/admin/(?:backups/(?:core|worker)/(?:snapshot|verify-snapshot)|backups/content/[a-z][a-z0-9-]{0,39}/(?:snapshot|verify)|backups/recovery-manifest|modules/[a-z][a-z0-9-]{0,39}/(?:snapshot|verify-snapshot))",path))
        safe_posts={"/api/login","/api/logout","/api/maps/route","/api/admin/kopia/credentials","/api/admin/meshmonitor/credentials"}
        restricted=(recovery_core_only or recovery_offline)
        denied=(request.method not in {"GET","HEAD","OPTIONS"} and
                path not in ({"/api/login","/api/logout"} if recovery_core_only else safe_posts) and
                not (recovery_offline and not recovery_core_only and (lifecycle or backup_post)))
        if restricted and (denied or path=="/api/admin/content/catalog"):
            response=JSONResponse({"detail":"Recovery mode: this operation is disabled"},status_code=409)
        elif request.method not in {"GET","HEAD","OPTIONS"}:
            # The supported deployment runs one Uvicorn process. Serialize
            # mutation admission and completion with begin/seal/release.
            async with mutation_lock:
                try:active=maintenance()
                except (OSError,ValueError,TypeError):
                    active={"phase":"invalid"}
                controls={"/api/admin/recovery-maintenance/begin","/api/admin/recovery-maintenance/seal","/api/admin/recovery-maintenance/release","/api/admin/core-update/claim"}
                auth=path in {"/api/login","/api/logout"}
                permitted=not active or auth or path in controls
                if active and active.get("phase")=="capturing" and (backup_post or (path=="/api/admin/backups/protected-snapshot" and not restricted)):
                    permitted=maintenance_owner(request,active)
                if active and active.get("phase") in {"updating","invalid"}:
                    # No login/logout or release during a host-owned update hold.
                    # Only the host updater may reconcile the persistent marker.
                    permitted=False
                if not permitted:
                    response=JSONResponse({"detail":"Recovery maintenance active; operation disabled"},status_code=409)
                else:
                    response=await call_next(request)
        else:
            response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = ("default-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'; worker-src blob:; child-src blob:; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; connect-src 'self'" if request.url.path == "/maps" else "default-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
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

    class RouteRequest(BaseModel):
        start: list[float] = Field(min_length=2,max_length=2)
        end: list[float] = Field(min_length=2,max_length=2)
        mode: str = Field(max_length=16)
        alternatives: int = Field(default=0,ge=0,le=2)

    @api.post("/api/maps/route")
    def map_route(payload: RouteRequest,request: Request):
        same_origin(request)
        with db() as con:
            if not con.execute("SELECT 1 FROM admin WHERE id=1").fetchone():
                raise HTTPException(403,"Complete initial setup first")
        try:
            return route(payload.start,payload.end,payload.mode,payload.alternatives)
        except ValueError as exc:
            raise HTTPException(400,str(exc))
        except RouteError as exc:
            raise HTTPException(503,str(exc))

    def require_setup():
        with db() as con:
            if not con.execute("SELECT 1 FROM admin WHERE id=1").fetchone():
                raise HTTPException(403,"Complete initial setup first")

    class WaypointRequest(BaseModel):
        name: str = Field(min_length=1,max_length=100)
        kind: str = Field(max_length=16)
        coords: list[float] = Field(min_length=2,max_length=2)
        id: int | None = Field(default=None,gt=0)

    class SavedRouteRequest(BaseModel):
        name: str = Field(min_length=1,max_length=100)
        mode: str = Field(max_length=16)
        coordinates: list[list[float]] = Field(min_length=2,max_length=20000)

    class PlanDelete(BaseModel):
        id: int = Field(gt=0)
        kind: str = Field(max_length=16)

    def plan_operation(operation):
        try:
            return operation()
        except ValueError as exc:
            raise HTTPException(400,str(exc))

    @api.get("/api/maps/places")
    def search_places(q: str = ""):
        require_setup()
        try:
            return {"results":places.search(q)}
        except (ValueError,OSError,sqlite3.Error) as exc:
            raise HTTPException(400,str(exc))

    @api.get("/api/admin/maps/places")
    def place_index_status(request: Request):
        require_admin(request)
        return places.status()

    @api.post("/api/admin/maps/places/build",status_code=202)
    def build_place_index(request: Request):
        require_admin(request)
        same_origin(request)
        try:
            places.launch()
        except (ValueError,OSError) as exc:
            raise HTTPException(409,str(exc))
        return {"queued":True}

    class CommDevice(BaseModel):
        id: int | None = Field(default=None,gt=0)
        label: str = Field(max_length=100)
        method: str = Field(max_length=20)
        assigned: str = Field(default="",max_length=100)
        callsign: str = Field(default="",max_length=60)
        notes: str = Field(default="",max_length=500)

    class CommPlan(BaseModel):
        id: int | None = Field(default=None,gt=0)
        name: str = Field(max_length=100)
        scope: str = Field(default="",max_length=100)
        primary: str = Field(max_length=500)
        alternate: str = Field(max_length=500)
        contingency: str = Field(max_length=500)
        emergency: str = Field(max_length=500)

    class CommDelete(BaseModel):
        id: int = Field(gt=0)
        kind: str = Field(max_length=10)

    @api.get("/api/communications")
    def communications_directory():
        require_setup()
        return comms.directory()

    @api.post("/api/admin/communications/device")
    def save_comm_device(payload: CommDevice,request: Request):
        require_admin(request)
        same_origin(request)
        return {"id":plan_operation(lambda:comms.save("device",payload.model_dump(exclude={"id"}),payload.id))}

    @api.post("/api/admin/communications/plan")
    def save_comm_plan(payload: CommPlan,request: Request):
        require_admin(request)
        same_origin(request)
        values={"name":payload.name,"scope":payload.scope,"steps":{k:getattr(payload,k) for k in ("primary","alternate","contingency","emergency")}}
        return {"id":plan_operation(lambda:comms.save("plan",values,payload.id))}

    class CommCheck(BaseModel):
        id: int = Field(gt=0)

    @api.post("/api/admin/communications/checked")
    def check_comm_device(payload: CommCheck,request: Request):
        require_admin(request)
        same_origin(request)
        plan_operation(lambda:comms.checked(payload.id))
        return {"ok":True}

    @api.post("/api/admin/communications/delete")
    def delete_comm_record(payload: CommDelete,request: Request):
        require_admin(request)
        same_origin(request)
        plan_operation(lambda:comms.delete(payload.kind,payload.id))
        return {"ok":True}

    @api.get("/communications")
    def comms_view():
        return FileResponse(ROOT/"communications.html")

    @api.get("/communications.js")
    def comms_script():
        return FileResponse(ROOT/"communications.js",media_type="text/javascript")

    @api.get("/api/maps/plans")
    def map_plans():
        require_setup()
        return plans.directory()

    @api.get("/api/maps/plans/routes/{ident}")
    def saved_route(ident: int):
        require_setup()
        return plan_operation(lambda:plans.get_route(ident))

    @api.post("/api/admin/maps/waypoints")
    def save_waypoint(payload: WaypointRequest,request: Request):
        require_admin(request)
        same_origin(request)
        return {"id":plan_operation(lambda:plans.waypoint(payload.name,payload.kind,payload.coords,payload.id))}

    @api.post("/api/admin/maps/routes")
    def save_route(payload: SavedRouteRequest,request: Request):
        require_admin(request)
        same_origin(request)
        return {"id":plan_operation(lambda:plans.save_route(payload.name,payload.mode,payload.coordinates))}

    @api.post("/api/admin/maps/plans/delete")
    def delete_plan(payload: PlanDelete,request: Request):
        require_admin(request)
        same_origin(request)
        plan_operation(lambda:plans.delete(payload.kind,payload.id))
        return {"ok":True}

    @api.post("/api/admin/maps/import/{fmt}")
    async def import_map_plan(fmt: str,request: Request):
        require_admin(request)
        same_origin(request)
        chunks=bytearray()
        async for chunk in request.stream():
            if len(chunks)+len(chunk)>1_000_000:
                raise HTTPException(413,"Import exceeds 1 MB")
            chunks.extend(chunk)
        try:
            raw=chunks.decode("utf-8-sig")
        except UnicodeError:
            raise HTTPException(400,"Use UTF-8 GPX or KML")
        return plan_operation(lambda:plans.import_file(fmt,raw))

    @api.get("/api/maps/export/{fmt}")
    def export_map_plan(fmt: str,route_id: int | None = None):
        require_setup()
        raw=plan_operation(lambda:plans.export(fmt,route_id))
        media={"gpx":"application/gpx+xml","kml":"application/vnd.google-earth.kml+xml"}[fmt]
        return Response(content=raw,media_type=media,headers={"Content-Disposition":f'attachment; filename="aftergrid-map.{fmt}"'})

    @api.get("/maps")
    def map_view():
        return FileResponse(ROOT / "maps.html")

    @api.get("/maps.js")
    def map_script():
        return FileResponse(ROOT / "maps.js",media_type="text/javascript")

    @api.get("/region.js")
    def region_script():
        return FileResponse(ROOT / "region.js",media_type="text/javascript")

    @api.get("/maps.css")
    def map_style():
        return FileResponse(ROOT / "maps.css",media_type="text/css")

    @api.get("/maps/archive.pmtiles")
    @api.head("/maps/archive.pmtiles")
    def map_archive():
        with db() as con:
            if not con.execute("SELECT 1 FROM admin WHERE id=1").fetchone():
                raise HTTPException(403,"Complete initial setup first")
        path=maps.content/"region.pmtiles"
        if path.is_symlink() or not path.is_file():
            raise HTTPException(404,"No local PMTiles archive")
        return FileResponse(path,media_type="application/octet-stream")

    @api.get("/health")
    def health():
        with db() as con:
            con.execute("SELECT 1")
        return {"status": "ok"}

    @api.get("/api/status")
    def status(request: Request):
        with db() as con:
            row = con.execute("SELECT server_name FROM admin WHERE id=1").fetchone()
            first = con.execute("SELECT selection,result FROM first_run WHERE id=1").fetchone()
        is_admin = admin_session(request)
        return {"setup_required": row is None, "admin": is_admin,
                "selection_pending": bool(is_admin and first["result"] is None),
                "submitted_selection": json.loads(first["selection"]) if is_admin and first["result"] is None and first["selection"] is not None else None,
                "server_name": row["server_name"] if row else "AfterGrid",
                "version": api.version, "recovery_core_only": recovery_core_only, "recovery_offline": recovery_offline,
                "recovery_maintenance": maintenance_path.exists() or maintenance_path.is_symlink()}

    @api.get("/api/preparedness")
    def preparedness():
        require_setup()
        # Share only counts and presence indicators, not credentials, paths,
        # logs, private stock quantities, or assertions of emergency readiness.
        def read(operation):
            try:
                return operation()
            except (OSError, ValueError, sqlite3.Error, ET.ParseError):
                return None
        def knowledge():
            directory=Path(os.environ.get("AFTERGRID_KIWIX_CONTENT","/content/kiwix"))
            if not directory.is_dir():
                return None
            files=local_inventory(directory)["files"]
            return {"indexed":sum(1 for item in files if item["indexed"]),"unindexed":sum(1 for item in files if not item["indexed"])}
        def navigation():
            info=maps.status()
            saved=plans.directory()
            return {"map_archives":len(info["files"]),"routing_graph_prepared":routing_data.status()["graph_ready"],
                    "waypoints":len(saved["waypoints"]),"saved_routes":len(saved["routes"])}
        def communications():
            info=comms.directory()
            return {"pace_plans":len(info["plans"]),"device_records":len(info["devices"]),
                    "devices_ever_checked":sum(1 for device in info["devices"] if device["checked"] is not None)}
        def resources():
            info=households.view()
            return {"households":len(info["households"]),"mapped_locations":len(info["locations"])}
        return {"knowledge":read(knowledge),"navigation":read(navigation),
                "communications":read(communications),"resources":read(resources)}

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

    @api.get("/api/households")
    def household_directory():
        # Shared LAN resource directory; no member contact information or credentials.
        with db() as con:
            if not con.execute("SELECT 1 FROM admin WHERE id=1").fetchone():
                raise HTTPException(403,"Complete initial setup first")
        return households.view()

    class HouseholdRequest(BaseModel):
        id: int | None = Field(default=None,gt=0)
        name: str = Field(min_length=1,max_length=80)

    class LocationRequest(BaseModel):
        id: int | None = Field(default=None,gt=0)
        module: str = Field(max_length=16)
        native_id: str = Field(min_length=1,max_length=64)
        label: str = Field(min_length=1,max_length=120)
        owner_id: int | None = Field(default=None,gt=0)
        storage_id: int | None = Field(default=None,gt=0)

    class DeleteRequest(BaseModel):
        id: int = Field(gt=0)

    def household_change(request,operation):
        require_admin(request)
        same_origin(request)
        try:
            return {"id":operation()}
        except ValueError as exc:
            raise HTTPException(400,str(exc))
        except sqlite3.IntegrityError:
            raise HTTPException(409,"Duplicate record, unknown household, or household still referenced by a location")

    @api.post("/api/admin/households")
    def household_save(payload: HouseholdRequest,request: Request):
        return household_change(request,lambda:households.save_household(payload.name,payload.id))

    @api.post("/api/admin/households/delete")
    def household_delete(payload: DeleteRequest,request: Request):
        return household_change(request,lambda:households.delete_household(payload.id))

    @api.post("/api/admin/households/locations")
    def location_save(payload: LocationRequest,request: Request):
        return household_change(request,lambda:households.save_location(payload.module,payload.native_id,payload.label,payload.owner_id,payload.storage_id,payload.id))

    @api.post("/api/admin/households/locations/delete")
    def location_delete(payload: DeleteRequest,request: Request):
        return household_change(request,lambda:households.delete_location(payload.id))

    class InventoryConnection(BaseModel):
        module: str = Field(max_length=16)
        key: str = Field(default="",max_length=1024)

    def inventory_result(operation):
        try:
            return operation()
        except ValueError as exc:
            raise HTTPException(400,str(exc))
        except InventoryError as exc:
            raise HTTPException(503,str(exc))

    @api.get("/api/admin/inventory/connections")
    def inventory_status(request: Request):
        require_admin(request)
        return inventory.status()

    @api.post("/api/admin/inventory/connect")
    def inventory_connect(payload: InventoryConnection,request: Request):
        require_admin(request)
        same_origin(request)
        return inventory_result(lambda: {"locations":inventory.save(payload.module,payload.key)})

    @api.post("/api/admin/inventory/disconnect")
    def inventory_disconnect(payload: InventoryConnection,request: Request):
        require_admin(request)
        same_origin(request)
        return inventory_result(lambda: {"ok":inventory.disconnect(payload.module) is None})

    @api.get("/api/admin/inventory/locations/{module}")
    def inventory_discover(module: str,request: Request):
        require_admin(request)
        return inventory_result(lambda: {"locations":inventory.discover(module)})

    @api.get("/api/admin/inventory/overview")
    def inventory_overview(request: Request, household: int | None = None, basis: str = "owner", offset: int = 0):
        require_admin(request)
        if basis not in ("owner","storage") or offset<0 or offset>2000 or (household is not None and household<0):
            raise HTTPException(400,"Invalid inventory filter or offset")
        directory=households.view()
        if household and not any(h["id"]==household for h in directory["households"]):
            raise HTTPException(404,"Household not found")
        locations=directory["locations"]
        if household is not None:
            selected=household or None
            locations=[loc for loc in locations if loc[basis+"_id"]==selected]
        return inventory.overview(locations,offset)

    @api.get("/api/admin/inventory/report/{ident}")
    def inventory_report(ident: int,request: Request):
        require_admin(request)
        location=next((r for r in households.view()["locations"] if r["id"]==ident),None)
        if location is None: raise HTTPException(404,"Location mapping not found")
        return inventory_result(lambda: inventory.report(location))

    class RoutingEstimate(BaseModel):
        region: str = Field(max_length=40)

    @api.get("/api/admin/routing-data")
    def routing_data_status(request: Request):
        require_admin(request)
        return routing_data.status()

    @api.post("/api/admin/routing-data/estimate",status_code=202)
    def routing_data_estimate(payload: RoutingEstimate,request: Request):
        require_admin(request)
        same_origin(request)
        try:
            with content_admission(data):
                routing_data.estimate(payload.region)
        except (ValueError,OSError) as exc:
            raise HTTPException(400,str(exc))
        return {"queued":True}

    @api.post("/api/admin/routing-data/download",status_code=202)
    def routing_data_download(request: Request):
        require_admin(request)
        same_origin(request)
        try:
            with content_admission(data):
                routing_data.download()
        except (ValueError,OSError) as exc:
            raise HTTPException(409,str(exc))
        return {"queued":True}

    class MapEstimate(BaseModel):
        build: str = Field(min_length=8,max_length=8)
        bbox: list[float] = Field(min_length=4,max_length=4)
        zoom: int = Field(ge=0,le=15)

    @api.get("/api/admin/maps")
    def map_status(request: Request):
        require_admin(request)
        return maps.status()

    @api.post("/api/admin/maps/estimate",status_code=202)
    def map_estimate(payload: MapEstimate,request: Request):
        require_admin(request)
        same_origin(request)
        try:
            with content_admission(data):
                maps.estimate(payload.build,payload.bbox,payload.zoom)
        except (ValueError,OSError) as exc:
            raise HTTPException(400,str(exc))
        return {"queued":True}

    @api.post("/api/admin/maps/download",status_code=202)
    def map_download(request: Request):
        require_admin(request)
        same_origin(request)
        try:
            with content_admission(data):
                maps.download()
        except (ValueError,OSError) as exc:
            raise HTTPException(409,str(exc))
        return {"queued":True}

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
            with content_admission(data):
                downloads.enqueue(payload.key)
        except (ValueError,sqlite3.IntegrityError) as exc:
            raise HTTPException(400,str(exc))
        return {"queued":True}

    class LocalContentRequest(BaseModel):
        name: str = Field(min_length=1,max_length=244)
        action: str = Field(min_length=1,max_length=16)

    @api.post("/api/admin/content/local")
    def content_local_action(payload: LocalContentRequest,request: Request):
        require_admin(request)
        same_origin(request)
        try:
            with content_admission(data):
                return downloads.local_action(payload.name,payload.action)
        except ValueError as exc:
            raise HTTPException(409,str(exc))
        except (OSError,sqlite3.Error):
            raise HTTPException(503,"Local library operation failed; inspect content storage")
        except Exception:
            raise HTTPException(422,"Native library operation failed; archive retained")

    @api.get("/api/admin/content/local")
    def content_local(request: Request):
        require_admin(request)
        try:
            return local_inventory(os.environ.get("AFTERGRID_KIWIX_CONTENT","/content/kiwix"))
        except (OSError,ValueError):
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
        # Commit the selection BEFORE the socket request. An accepted batch
        # with a lost response must never be replaced by a different selection.
        with db() as con:
            con.execute("BEGIN IMMEDIATE")
            saved = con.execute("SELECT * FROM first_run WHERE id=1").fetchone()
            if saved["selection"] is not None and saved["selection"] != canonical:
                raise HTTPException(409, "Initial selection already submitted; retry that selection or use the catalog after it completes")
            if saved["result"] is not None:
                return json.loads(saved["result"])
            con.execute("UPDATE first_run SET selection=? WHERE id=1", (canonical,))
        if selected:
            try:
                code, result = call("/jobs/batch", {"token":saved["token"],"modules":selected})
            except WorkerUnavailable:
                raise HTTPException(503, "Submission unconfirmed; retry the saved selection")
            if code != 202:
                # The worker checks token replay before catalog admission. An
                # explicit 400 therefore confirms this batch was not accepted.
                if code==400:
                    with db() as con:
                        con.execute("UPDATE first_run SET selection=NULL WHERE id=1 AND result IS NULL AND selection=?",(canonical,))
                raise HTTPException(code if code in {400,409} else 502, result.get("detail","Module manager request failed"))
            if (not isinstance(result,dict) or not isinstance(result.get("ids"),list)
                or len(result["ids"])!=len(selected) or any(type(i) is not int or i<=0 for i in result["ids"])
                or len(set(result["ids"]))!=len(selected)):
                raise HTTPException(502,"Submission unconfirmed; retry the saved selection")
        else:
            result = {"ids":[]}
        with db() as con:
            con.execute("UPDATE first_run SET result=? WHERE id=1 AND selection=?",(json.dumps(result),canonical))
        return result

    @api.get("/api/admin/installation-summary")
    def installation_summary(request: Request):
        require_admin(request)
        try:code,result=call("/installation-summary")
        except WorkerUnavailable:raise HTTPException(503,"Module manager unavailable") from None
        if code!=200 or not isinstance(result,dict) or not isinstance(result.get("applications"),list):
            raise HTTPException(503,"Installation history unavailable")
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

    @api.post("/api/admin/meshmonitor/credentials")
    def meshmonitor_credentials(request: Request):
        require_admin(request)
        same_origin(request)
        if not local_credential_origin():
            raise HTTPException(403,"Use the configured private LAN or trusted HTTPS portal to reveal credentials")
        try:
            code,result=call("/credentials/meshmonitor")
        except WorkerUnavailable:
            raise HTTPException(503,"Module manager unavailable")
        if code!=200:
            raise HTTPException(code if code==404 else 502,result.get("detail","Module manager request failed"))
        return result

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

    @api.get("/api/admin/kopia/status")
    def kopia_repository_status(request: Request):
        require_admin(request)
        try:
            code,result=call("/kopia/status")
        except WorkerUnavailable:
            raise HTTPException(503,"Module manager unavailable")
        if code!=200:
            raise HTTPException(502,"Native Kopia status unavailable")
        return result

    @api.get("/api/admin/backups/policy-sources")
    def backup_policy_sources(request: Request):
        require_admin(request)
        try:code,result=call("/backup-policy/sources")
        except WorkerUnavailable:raise HTTPException(503,"Module manager unavailable") from None
        if code!=200:raise HTTPException(502,"Reviewed policy sources unavailable")
        return result

    @api.get("/api/admin/backups/effective-policy/{key:path}")
    def effective_backup_policy(key: str,request: Request):
        require_admin(request)
        if not re.fullmatch(r"(?:global|core|worker|(?:application|content)/[a-z][a-z0-9-]{0,39})",key):
            raise HTTPException(404,"Unknown reviewed policy source")
        try:code,result=call("/backup-policy/effective/"+key)
        except WorkerUnavailable:raise HTTPException(503,"Module manager unavailable") from None
        if code!=200:raise HTTPException(code if code in {404,503} else 502,"Native effective policy unavailable")
        return result

    @api.get("/api/admin/backups/health")
    def backup_health(request: Request):
        require_admin(request)
        try:
            code,report=call("/backup-health")
        except WorkerUnavailable:raise HTTPException(503,"Module manager unavailable") from None
        if code!=200 or not isinstance(report,dict) or not isinstance(report.get("sources"),list):
            raise HTTPException(503,"Recorded backup health unavailable")
        try:
            rows=schedules.load()
            maintenance_active=maintenance() is not None
        except (OSError,ValueError,TypeError):
            raise HTTPException(409,"Schedule or maintenance state invalid; inspect host") from None
        now=int(time.time())
        execution_enabled=not (recovery_core_only or recovery_offline)
        for source in report["sources"]:
            row=rows.get(source["key"])
            if row is None:
                source["schedule"]={"status":"not configured"}
                continue
            active=row["result"] in {"dispatching","queued","running"}
            if row["result"] in {"failed","interrupted","unknown","dispatching"} and not active:
                label="paused; inspect result"
            elif row["result"]=="dispatching":label="dispatch unconfirmed"
            elif active:label="job recorded active"
            elif not row["enabled"]:label="disabled"
            elif not execution_enabled or maintenance_active:label="deferred by recovery or maintenance"
            elif row["next_due"]<=now:label="due; awaiting admission"
            else:label="scheduled"
            source["schedule"]={**row,"status":label}
        return {**report,"observed_at":now,"managed_execution_enabled":execution_enabled,
                "maintenance_active":maintenance_active,"complete_recovery_certified":False}

    class ScheduleSelection(BaseModel):
        key: str = Field(min_length=1,max_length=80)
        interval: str = Field(min_length=1,max_length=10)
        enabled: bool = Field(strict=True)
        confirmed: bool = Field(strict=True)

    @api.get("/api/admin/backups/schedules")
    def managed_schedules(request: Request):
        require_admin(request)
        try:rows=schedules.load()
        except (OSError,ValueError,TypeError):raise HTTPException(409,"Invalid schedule file; inspect host") from None
        return {"sources":rows,"available":sorted(SCHEDULE_SOURCES),
                "intervals":sorted(SCHEDULE_INTERVALS),"execution_enabled":not (recovery_core_only or recovery_offline),
                "verification_automatic":True}

    @api.post("/api/admin/backups/schedules")
    def configure_schedule(payload: ScheduleSelection,request: Request):
        require_admin(request)
        same_origin(request)
        if not payload.confirmed or payload.key not in SCHEDULE_SOURCES or payload.interval not in SCHEDULE_INTERVALS:
            raise HTTPException(409,"Confirm reviewed schedule and application downtime")
        if payload.enabled:
            try:code,policy=call("/backup-policy/effective/"+payload.key)
            except WorkerUnavailable:raise HTTPException(503,"Module manager unavailable") from None
            if code!=200 or policy.get("policy",{}).get("schedule",{}).get("automatic_policy") is not False:
                raise HTTPException(409,"Review native Kopia policy; automatic native source scheduling must be absent")
        try:return schedules.configure(payload.key,payload.enabled,payload.interval)
        except (OSError,ValueError,TypeError):raise HTTPException(409,"Schedule configuration unavailable; inspect host") from None

    class ProtectedSnapshotSelection(BaseModel):
        key: str = Field(min_length=1,max_length=80)
        confirmed: bool = Field(strict=True)

    @api.post("/api/admin/backups/protected-snapshot",status_code=202)
    def protected_snapshot(payload: ProtectedSnapshotSelection,request: Request):
        require_admin(request)
        same_origin(request)
        if not payload.confirmed or payload.key not in SCHEDULE_SOURCES:
            raise HTTPException(409,"Confirm supported source and persistent native pin")
        active=maintenance()
        if active and payload.key not in {"core","worker"}:
            raise HTTPException(409,"During maintenance only core and worker protected captures are admitted")
        maintenance_idle()
        module,action=SCHEDULE_SOURCES[payload.key]
        try:code,result=call("/jobs",{"module":module,"action":action,"protect":True})
        except WorkerUnavailable:raise HTTPException(503,"Module manager unavailable") from None
        if code!=202:raise HTTPException(code if code in {400,409} else 502,"Protected snapshot unavailable")
        return result

    class RetentionSelection(BaseModel):
        key: str = Field(min_length=1,max_length=80)
        expected: dict[str,int] = Field(max_length=6)
        counts: dict[str,int] = Field(max_length=6)
        confirmed: bool = Field(strict=True)

    @api.post("/api/admin/backups/retention",status_code=202)
    def configure_retention(payload: RetentionSelection,request: Request):
        require_admin(request)
        same_origin(request)
        if not payload.confirmed or payload.key not in SCHEDULE_SOURCES:
            raise HTTPException(409,"Confirm source-specific retention and protected recovery point")
        maintenance_idle()
        try:code,result=call("/backup-policy/retention",{"key":payload.key,"expected":payload.expected,"counts":payload.counts})
        except WorkerUnavailable:raise HTTPException(503,"Module manager unavailable") from None
        if code!=202:raise HTTPException(code if code in {400,409} else 502,"Retention change unavailable")
        return result

    class RepositoryConfirmation(BaseModel):
        confirmed: bool = Field(strict=True)

    class MaintenanceSelection(RepositoryConfirmation):
        modules: list[str] = Field(default_factory=list,max_length=10)

    def maintenance_idle():
        try:
            code,rows=call("/jobs")
            if code!=200 or not isinstance(rows,list) or any(r["state"] in {"queued","running"} for r in rows):
                raise ValueError("Worker jobs active or unavailable")
            with content_admission(data):
                with sqlite3.connect(data/"downloads.sqlite3",timeout=3) as con:
                    if con.execute("SELECT 1 FROM downloads WHERE state IN ('queued','downloading','verifying','indexing') LIMIT 1").fetchone():
                        raise ValueError("Knowledge download active")
                for name in ("map-job.json","routing-download.json"):
                    path=data/name
                    if path.exists() and json.loads(path.read_text())["state"] in {"estimating","downloading","verifying"}:
                        raise ValueError("Regional operation active")
            if places.status()["state"]=="building":raise ValueError("Place index build active")
            return rows
        except (WorkerUnavailable,OSError,sqlite3.Error,ValueError,KeyError,TypeError):
            raise HTTPException(409,"Finish active jobs and content operations; inspect interrupted maintenance") from None

    @api.get("/api/admin/recovery-maintenance")
    def recovery_maintenance_status(request: Request):
        require_admin(request)
        try:active=maintenance()
        except (OSError,ValueError,TypeError):raise HTTPException(409,"Invalid maintenance marker; inspect host") from None
        return {"active":bool(active),"phase":active["phase"] if active else None,
                "modules":active.get("modules",[]) if active else []}

    @api.post("/api/admin/recovery-maintenance/begin")
    def begin_recovery_maintenance(payload: MaintenanceSelection,request: Request):
        require_admin(request)
        same_origin(request)
        modules=sorted(payload.modules)
        allowed={"grocy","homebox","notes","meshmonitor","kolibri","media","kiwix","maps","routing"}
        if not payload.confirmed or len(modules)!=len(set(modules)) or not set(modules)<=allowed:
            raise HTTPException(409,"Confirm maintenance and supported recovery selection")
        if maintenance() is not None:raise HTTPException(409,"Existing maintenance; inspect before releasing")
        rows=maintenance_idle()
        save_maintenance({"format":1,"phase":"capturing","owner":digest(request.cookies[COOKIE]),
                          "modules":modules,"baseline_job":max((r["id"] for r in rows),default=0)})
        return {"active":True,"phase":"capturing"}

    @api.post("/api/admin/recovery-maintenance/seal")
    def seal_recovery_maintenance(payload: RepositoryConfirmation,request: Request):
        require_admin(request)
        same_origin(request)
        active=maintenance()
        if not payload.confirmed or not active or active["phase"]!="capturing" or not maintenance_owner(request,active):
            raise HTTPException(409,"Active capture owner required")
        rows=maintenance_idle()
        try:code,value=call("/recovery-manifest")
        except WorkerUnavailable:raise HTTPException(409,"Recovery inventory unavailable") from None
        if code!=200 or value.get("manifest_job")!=max((r["id"] for r in rows),default=0):
            raise HTTPException(409,"Fresh final recovery inventory required")
        expected={"core","worker"}
        for module in active["modules"]:
            if module not in {"kiwix","maps","routing"}:expected.add("application/"+module)
            if module in {"kiwix","maps","routing","media"}:expected.add("content/"+module)
        records={r["key"]:r for r in value["records"]}
        baseline=active["baseline_job"]
        for key in expected:
            r=records.get(key,{})
            if (type(r.get("snapshot_job")) is not int or type(r.get("verification_job")) is not int
                or not baseline<r["snapshot_job"]<r["verification_job"]<value["manifest_job"]
                or r.get("repository_status")!="present"
                or r.get("verification")!=("read-only" if key.startswith("content/") else "isolated")):
                raise HTTPException(409,"Fresh verified recovery sources required")
        # Canonical JSON is independent of key order in the HTTP response.
        checksum=hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":")).encode()).hexdigest()
        sealed={"format":1,"phase":"sealed","modules":active["modules"],"inventory_sha256":checksum,
                "manifest_job":value["manifest_job"]}
        save_maintenance(sealed)
        return {"active":True,"phase":"sealed","inventory_sha256":checksum}

    class CoreUpdateClaim(RepositoryConfirmation):
        candidate_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
        inventory_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @api.get("/api/admin/core-update/status")
    def core_update_status(request: Request):
        require_admin(request)
        try:active=maintenance()
        except (OSError,ValueError,TypeError):active={"phase":"invalid"}
        phase=active.get("phase") if active else "idle"
        return {"activation_enabled":False,"phase":phase,
                "maintenance_active":bool(active),"host_reconciliation_required":phase in {"updating","invalid"},
                "affected_services":["core","worker"],"optional_applications_stopped":False,
                "message":"Core update activation is not released; no changes can be initiated from this dashboard."}

    @api.post("/api/admin/core-update/claim")
    def claim_core_update(payload: CoreUpdateClaim,request: Request):
        require_admin(request)
        same_origin(request)
        active=maintenance()
        if (not payload.confirmed or not active or active["phase"]!="sealed"
            or active.get("modules")!=[] or active.get("inventory_sha256")!=payload.inventory_sha256):
            raise HTTPException(409,"Matching sealed core-only recovery capture required")
        rows=maintenance_idle()
        if active.get("manifest_job")!=max((r["id"] for r in rows),default=0):
            raise HTTPException(409,"Recovery inventory changed")
        try:code,value=call("/recovery-manifest")
        except WorkerUnavailable:raise HTTPException(409,"Recovery inventory unavailable") from None
        if code!=200 or not isinstance(value,dict) or value.get("manifest_job")!=active["manifest_job"]:
            raise HTTPException(409,"Recovery inventory unavailable")
        checksum=hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":")).encode()).hexdigest()
        if checksum!=payload.inventory_sha256:
            raise HTTPException(409,"Sealed inventory changed")
        for key in ("core","worker"):
            matches=[row for row in value.get("records",[]) if row.get("key")==key]
            if len(matches)!=1 or matches[0].get("aftergrid_pinned") is not True or matches[0].get("verification")!="isolated" or matches[0].get("repository_status")!="present":
                raise HTTPException(409,"Protected verified core and worker captures required")
        save_maintenance({**active,"phase":"updating","candidate_sha256":payload.candidate_sha256,
                          "claimed_at":int(time.time())})
        return {"active":True,"phase":"updating","activation_enabled":False}

    @api.post("/api/admin/recovery-maintenance/release")
    def release_recovery_maintenance(payload: RepositoryConfirmation,request: Request):
        require_admin(request)
        same_origin(request)
        active=maintenance()
        if not payload.confirmed or not active or active["phase"]=="updating":raise HTTPException(409,"Confirm existing maintenance release; update holds require host reconciliation")
        maintenance_idle()
        maintenance_path.unlink()
        return {"active":False}

    @api.post("/api/admin/kopia/initialize",status_code=202)
    def kopia_initialize(payload: RepositoryConfirmation,request: Request):
        require_admin(request)
        same_origin(request)
        if not payload.confirmed:
            raise HTTPException(409,"Confirm destination and secure recovery credentials")
        try:
            code,result=call("/jobs",{"module":"kopia","action":"initialize-repository"})
        except WorkerUnavailable:
            raise HTTPException(503,"Module manager unavailable")
        if code!=202:
            raise HTTPException(code if code in (400,409) else 502,result.get("detail","Repository initialization unavailable"))
        return result

    @api.post("/api/admin/backups/core/snapshot",status_code=202)
    def core_snapshot(payload: RepositoryConfirmation,request: Request):
        require_admin(request)
        same_origin(request)
        if not payload.confirmed:
            raise HTTPException(409,"Confirm connected repository and private core export")
        try:
            code,result=call("/jobs",{"module":"kopia","action":"core-snapshot"})
        except WorkerUnavailable:
            raise HTTPException(503,"Module manager unavailable")
        if code!=202:
            raise HTTPException(code if code in (400,409) else 502,result.get("detail","Core snapshot unavailable"))
        return result

    @api.post("/api/admin/backups/core/verify-snapshot",status_code=202)
    def core_verify_snapshot(payload: RepositoryConfirmation,request: Request):
        require_admin(request)
        same_origin(request)
        if not payload.confirmed:
            raise HTTPException(409,"Confirm isolated private restoration")
        try:
            code,result=call("/jobs",{"module":"kopia","action":"core-verify-snapshot"})
        except WorkerUnavailable:
            raise HTTPException(503,"Module manager unavailable")
        if code!=202:
            raise HTTPException(code if code in (400,409) else 502,result.get("detail","Core restore verification unavailable"))
        return result

    @api.post("/api/admin/backups/worker/snapshot",status_code=202)
    def worker_snapshot(payload: RepositoryConfirmation,request: Request):
        require_admin(request)
        same_origin(request)
        if not payload.confirmed:
            raise HTTPException(409,"Confirm encrypted repository and off-server recovery password")
        try:
            code,result=call("/jobs",{"module":"kopia","action":"worker-snapshot"})
        except WorkerUnavailable:
            raise HTTPException(503,"Module manager unavailable")
        if code!=202:
            raise HTTPException(code if code in (400,409) else 502,result.get("detail","Worker snapshot unavailable"))
        return result

    @api.post("/api/admin/backups/worker/verify-snapshot",status_code=202)
    def worker_verify_snapshot(payload: RepositoryConfirmation,request: Request):
        require_admin(request)
        same_origin(request)
        if not payload.confirmed:
            raise HTTPException(409,"Confirm isolated private worker restoration")
        try:
            code,result=call("/jobs",{"module":"kopia","action":"worker-verify-snapshot"})
        except WorkerUnavailable:
            raise HTTPException(503,"Module manager unavailable")
        if code!=202:
            raise HTTPException(code if code in (400,409) else 502,result.get("detail","Worker restore verification unavailable"))
        return result

    @api.post("/api/admin/backups/recovery-manifest",status_code=202)
    def generate_recovery_manifest(payload: RepositoryConfirmation,request: Request):
        require_admin(request)
        same_origin(request)
        if not payload.confirmed:
            raise HTTPException(409,"Confirm native repository inventory check")
        try:
            code,result=call("/jobs",{"module":"kopia","action":"recovery-manifest"})
        except WorkerUnavailable:
            raise HTTPException(503,"Module manager unavailable")
        if code!=202:
            raise HTTPException(code if code in (400,409) else 502,result.get("detail","Recovery inventory unavailable"))
        return result

    @api.get("/api/admin/backups/recovery-manifest")
    def get_recovery_manifest(request: Request):
        require_admin(request)
        try:
            code,result=call("/recovery-manifest")
        except WorkerUnavailable:
            raise HTTPException(503,"Module manager unavailable")
        if code!=200:
            raise HTTPException(code if code==404 else 502,"No confirmed recovery inventory; generate one first")
        return result

    @api.get("/api/admin/backups/core")
    def core_backup_plan(request: Request):
        require_admin(request)
        return {"coverage":"planned only","snapshot_verified":False,
                "sources":[{"path":"/source/data/core/recovery-export","guidance":"Managed online SQLite export of core.sqlite3 and stable download metadata; sessions removed from copy. Rebuildable indexes are excluded."},
                           {"path":"/tmp/aftergrid-worker-export","guidance":"Managed private worker database and reviewed generated-secret export; restore not yet verified."},
                           {"path":"/source/modules","guidance":"Reviewed module definitions, not the complete core release."}],
                "missing":["Rebuildable place indexes and interrupted downloads","Worker state restoration and exact secret recovery","Core release and host .env configuration","Exact Docker images and recovery metadata"],
                "repository_guidance":"Configure Kopia natively. Keep the repository password and an independent repository copy off the server."}

    @api.post("/api/admin/modules/{ident}/snapshot",status_code=202)
    def module_snapshot(ident: str,payload: RepositoryConfirmation,request: Request):
        require_admin(request)
        same_origin(request)
        if ident not in {"grocy","homebox","notes","meshmonitor","tak","kolibri","media"}:
            raise HTTPException(400,"Application snapshot not yet supported")
        if not payload.confirmed:
            raise HTTPException(409,"Confirm temporary service interruption and exclusive administration")
        try:
            code,result=call("/jobs",{"module":ident,"action":"snapshot"})
        except WorkerUnavailable:
            raise HTTPException(503,"Module manager unavailable")
        if code!=202:
            raise HTTPException(code if code in (400,409) else 502,result.get("detail","Snapshot request unavailable"))
        return result

    @api.post("/api/admin/modules/{ident}/verify-snapshot",status_code=202)
    def module_verify_snapshot(ident: str,payload: RepositoryConfirmation,request: Request):
        require_admin(request)
        same_origin(request)
        if ident not in {"grocy","homebox","notes","meshmonitor","tak","kolibri","media"}:
            raise HTTPException(400,"Application restore verification not yet supported")
        if not payload.confirmed:
            raise HTTPException(409,"Confirm isolated restore and storage requirements")
        try:
            code,result=call("/jobs",{"module":ident,"action":"verify-snapshot"})
        except WorkerUnavailable:
            raise HTTPException(503,"Module manager unavailable")
        if code!=202:
            raise HTTPException(code if code in (400,409) else 502,result.get("detail","Restore verification unavailable"))
        return result

    @api.post("/api/admin/backups/content/{ident}/{action}",status_code=202)
    def content_backup(ident: str,action: str,payload: RepositoryConfirmation,request: Request):
        require_admin(request)
        same_origin(request)
        if ident not in {"kiwix","maps","routing","media"} or action not in {"snapshot","verify"}:
            raise HTTPException(400,"Unsupported content backup action")
        if not payload.confirmed:
            raise HTTPException(409,"Confirm content maintenance and native repository access")
        try:
            code,result=call("/jobs",{"module":ident,"action":"content-"+action})
        except WorkerUnavailable:
            raise HTTPException(503,"Module manager unavailable")
        if code!=202:
            raise HTTPException(code if code in (400,409) else 502,result.get("detail","Content backup unavailable"))
        return result

    @api.get("/api/admin/modules/{ident}/backup-plan")
    def module_backup_plan(ident: str,request: Request):
        require_admin(request)
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,39}",ident):
            raise HTTPException(400,"Unsupported module")
        try:
            code,result=call("/backup-plan/"+ident)
        except WorkerUnavailable:
            raise HTTPException(503,"Module manager unavailable")
        if code!=200:
            raise HTTPException(code if code in (404,503) else 502,"Reviewed backup sources unavailable")
        return result

    @api.get("/api/admin/modules/{ident}/versions")
    def module_versions(ident: str,request: Request):
        require_admin(request)
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,39}",ident):
            raise HTTPException(400,"Unsupported module")
        try:
            code,result=call("/versions/"+ident)
        except WorkerUnavailable:
            raise HTTPException(503,"Module manager unavailable")
        if code!=200:
            raise HTTPException(code if code in (404,503) else 502,"Local module version information unavailable")
        return result

    @api.get("/api/admin/modules/{ident}/update-eligibility")
    def module_update_eligibility(ident: str,request: Request):
        require_admin(request)
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,39}",ident):
            raise HTTPException(400,"Unsupported module")
        try:code,result=call("/update-eligibility/"+ident,timeout=45)
        except WorkerUnavailable:raise HTTPException(503,"Module manager unavailable") from None
        if code!=200:raise HTTPException(code if code in {404,503} else 502,"Update eligibility unavailable")
        try:active=maintenance() is not None
        except (OSError,ValueError,TypeError):active=True
        if active:
            result["status"]="blocked"
            result["blockers"]=[*result["blockers"],"Recovery maintenance active or unavailable"]
        return result

    @api.post("/api/admin/modules/{ident}/update-eligibility")
    def module_update_eligibility_online(ident: str,request: Request):
        require_admin(request)
        same_origin(request)
        if ident!="kiwix":raise HTTPException(400,"Unsupported update pilot")
        maintenance_idle()
        try:code,result=call("/update-eligibility",{"module":ident},timeout=60)
        except WorkerUnavailable:raise HTTPException(503,"Module manager unavailable") from None
        if code!=200:raise HTTPException(code if code in {400,503} else 502,"Update eligibility unavailable")
        return result

    @api.get("/api/admin/updates/health")
    def reader_update_health(request: Request):
        require_admin(request)
        try:code,result=call("/update-health/kiwix",timeout=30)
        except WorkerUnavailable:raise HTTPException(503,"Module manager unavailable") from None
        if code!=200 or not isinstance(result,dict):
            raise HTTPException(503,"Recorded update health unavailable")
        try:
            prefs=update_preferences.report("kiwix")
            active=maintenance() is not None
        except (OSError,ValueError,TypeError):
            raise HTTPException(409,"Update preference or maintenance state invalid; inspect host") from None
        return {**result,"preferences":prefs,"maintenance_active":active,
                "automatic_execution_enabled":prefs["execution_enabled"],"activation_required":prefs["activation_required"]}

    class UpdatePreferenceSelection(BaseModel):
        enabled: bool = Field(strict=True)
        weekday: int = Field(strict=True,ge=0,le=6)
        start_minute: int = Field(strict=True,ge=0,lt=1440)
        duration_minutes: int = Field(strict=True,ge=30,le=360)
        confirmed: bool = Field(strict=True)

    @api.get("/api/admin/modules/kiwix/update-preferences")
    def reader_update_preferences(request: Request):
        require_admin(request)
        try:report=update_preferences.report("kiwix")
        except (OSError,ValueError,TypeError):raise HTTPException(409,"Update preferences invalid; inspect host") from None
        report["recovery_mode"]=recovery_core_only or recovery_offline
        return report

    @api.post("/api/admin/modules/kiwix/update-preferences")
    def configure_reader_update_preferences(payload: UpdatePreferenceSelection,request: Request):
        require_admin(request)
        same_origin(request)
        if not payload.confirmed:raise HTTPException(409,"Confirm update preference and UTC window")
        try:return update_preferences.configure("kiwix",payload.model_dump(exclude={"confirmed"}))
        except (OSError,ValueError,TypeError):raise HTTPException(409,"Invalid or unavailable UTC update preferences") from None

    class UpdateActivationSelection(BaseModel):
        enabled: bool = Field(strict=True)
        confirmed: bool = Field(strict=True)

    @api.post("/api/admin/modules/kiwix/update-activation")
    def activate_reader_updates(payload: UpdateActivationSelection,request: Request):
        require_admin(request)
        same_origin(request)
        if not payload.confirmed:raise HTTPException(409,"Confirm separate automatic update activation")
        try:
            if payload.enabled:maintenance_idle()
            return update_preferences.activate(payload.enabled)
        except (OSError,ValueError,TypeError):raise HTTPException(409,"Automatic update activation unavailable") from None

    class UpdatePreparationSelection(BaseModel):
        candidate: str = Field(min_length=1,max_length=256)
        platform: str = Field(min_length=1,max_length=32)
        previous_image_id: str = Field(min_length=71,max_length=71)
        target_image_id: str = Field(min_length=71,max_length=71)
        confirmed: bool = Field(strict=True)

    @api.get("/api/admin/modules/kiwix/update-preparation")
    def update_preparation_status(request: Request):
        require_admin(request)
        try:code,result=call("/update-preparation/kiwix")
        except WorkerUnavailable:raise HTTPException(503,"Module manager unavailable") from None
        if code!=200:raise HTTPException(503,"Update preparation history unavailable")
        return result

    @api.post("/api/admin/modules/kiwix/update-preparation",status_code=202)
    def queue_update_preparation(payload: UpdatePreparationSelection,request: Request):
        require_admin(request)
        same_origin(request)
        if not payload.confirmed:raise HTTPException(409,"Confirm protected capture and verification")
        maintenance_idle()
        try:code,result=call("/update-preparation",payload.model_dump(exclude={"confirmed"}))
        except WorkerUnavailable:raise HTTPException(503,"Module manager unavailable") from None
        if code!=202:raise HTTPException(code if code in {400,409} else 502,"Approved update preparation unavailable")
        return result

    @api.post("/api/admin/modules/kiwix/guarded-update",status_code=202)
    def queue_guarded_update(payload: UpdatePreparationSelection,request: Request):
        require_admin(request)
        same_origin(request)
        if not payload.confirmed:raise HTTPException(409,"Confirm protected backup, archived previous image and service interruption")
        maintenance_idle()
        try:code,result=call("/guarded-update",payload.model_dump(exclude={"confirmed"}))
        except WorkerUnavailable:raise HTTPException(503,"Module manager unavailable") from None
        if code!=202:raise HTTPException(code if code in {400,409} else 502,"Approved guarded update unavailable")
        return result

    class RollbackResolutionSelection(BaseModel):
        failed_job: int = Field(strict=True,gt=0)
        image_id: str = Field(min_length=71,max_length=71)
        confirmed: bool = Field(strict=True)

    @api.post("/api/admin/modules/kiwix/resolve-rollback",status_code=202)
    def queue_reader_resolution(payload: RollbackResolutionSelection,request: Request):
        require_admin(request)
        same_origin(request)
        if not payload.confirmed:raise HTTPException(409,"Confirm exact recovered image and protected evidence")
        maintenance_idle()
        try:code,result=call("/resolve-rollback",payload.model_dump(exclude={"confirmed"}))
        except WorkerUnavailable:raise HTTPException(503,"Module manager unavailable") from None
        if code!=202:raise HTTPException(code if code in {400,409} else 502,"Rollback resolution unavailable")
        return result

    @api.post("/api/admin/modules/{ident}/registry-check")
    def module_registry_check(ident: str,request: Request):
        require_admin(request)
        same_origin(request)
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,39}",ident):
            raise HTTPException(400,"Unsupported module")
        try:
            code,result=call("/registry-check",{"module":ident},timeout=45)
        except WorkerUnavailable:
            raise HTTPException(503,"Module manager unavailable")
        if code!=200:
            raise HTTPException(code if code in (400,503) else 502,result.get("detail","Registry check unavailable"))
        return result

    class NativeAccountSetup(BaseModel):
        model_config={"extra":"forbid"}
        username: str = Field(min_length=1,max_length=254)
        password: str = Field(min_length=12,max_length=128)
        current_password: str = Field(default="",max_length=128)
        confirmed: bool = Field(default=False,strict=True)

    @api.post("/api/admin/native-setup/{ident}",status_code=202)
    def native_account_setup(ident: str,payload: NativeAccountSetup,request: Request):
        require_admin(request)
        same_origin(request)
        if ident not in {"homebox","grocy"}:
            raise HTTPException(400,"Unsupported native account setup")
        if not local_credential_origin():
            raise HTTPException(403,"Use the configured private LAN or trusted HTTPS portal for native account setup")
        if not payload.confirmed:
            raise HTTPException(409,"Confirm native account setup on your trusted network")
        try:
            code,result=call("/native-setup",{"module":ident,"account":payload.model_dump(exclude={"confirmed"})})
        except WorkerUnavailable:
            raise HTTPException(503,"Module manager unavailable; inspect existing activity before retrying")
        if code!=202:
            raise HTTPException(code if code in {400,409} else 502,result.get("detail","Native account setup unavailable"))
        return result

    class ModuleActionOptions(BaseModel):
        backup_confirmed: bool = Field(default=False,strict=True)

    @api.post("/api/admin/modules/{ident}/{action}", status_code=202)
    def module_action(ident: str, action: str, request: Request, options: ModuleActionOptions | None = None):
        require_admin(request)
        same_origin(request)
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,39}", ident) or action not in {"install","start","stop","restart","update","uninstall","share","unshare","prepare-graph","activate-graph","rollback-graph","archive-original","archive-replacement"} or (action in {"prepare-graph","activate-graph","rollback-graph","archive-original","archive-replacement"} and ident!="routing"):
            raise HTTPException(400, "Unsupported module or action")
        payload={"module":ident,"action":action}
        if action=="update":
            if ident=="routing":
                raise HTTPException(409,"Routing updates require separate graph migration validation")
            if not options or not options.backup_confirmed:
                raise HTTPException(409,"Confirm a current application-consistent backup before updating")
            payload["backup_confirmed"]=True
        try:
            code, result = call("/jobs",payload)
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
