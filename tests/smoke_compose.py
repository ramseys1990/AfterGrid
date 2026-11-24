"""Disposable CI integration test. Never run on an existing AfterGrid host."""
import http.cookiejar
import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8080"
client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

def api(path, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(BASE + path, data=data, headers={"Origin": BASE, "Content-Type": "application/json"})
    with client.open(req, timeout=60 if path.endswith("/registry-check") else 30) as res:
        return json.load(res)

def module(ident="kiwix"):
    return next(m for m in api("/api/modules") if m["id"]==ident)

def action(name, ident="kiwix"):
    # Only retry a known transient registry pull failure; never retry graph
    # switches or other state-changing jobs on arbitrary failures.
    for attempt in range(3):
        job_id=api("/api/admin/modules/"+ident+"/"+name,{})["id"]
        try:
            wait_job(job_id,name)
            return
        except AssertionError as exc:
            job=exc.args[0] if exc.args else None
            if not (attempt<2 and name=="install" and isinstance(job,dict) and job.get("completed")==1 and any(x in job.get("log","").lower() for x in ("retry-after","too many requests","toomanyrequests","429"))):
                raise
            print("Registry throttled; retrying install after bounded delay",ident,flush=True)
            time.sleep(10*(attempt+1))

def wait_job(job_id,name):
    deadline=time.monotonic()+240
    while time.monotonic()<deadline:
        job=next(j for j in api("/api/admin/jobs") if j["id"]==job_id)
        if job["state"]=="succeeded":
            assert job["completed"]==job["total"],job
            return
        if job["state"] in ("failed","interrupted"):
            raise AssertionError(job)
        time.sleep(2)
    raise AssertionError("Timed out waiting for "+name)

assert api("/api/status")["setup_required"]
api("/api/setup",{"token":os.environ["SMOKE_TOKEN"],"username":"admin","password":"a disposable test password","server_name":"CI"})
assert module()["status"]=="not installed"
batch=api("/api/admin/first-run",{"modules":["kiwix","homebox"]})
assert len(batch["ids"])==2
assert not api("/api/status")["selection_pending"]
assert api("/api/admin/first-run",{"modules":["homebox","kiwix"]})==batch
wait_job(batch["ids"][0],"kiwix initial install")
assert module()["status"]=="running"
plan=api("/api/admin/modules/kiwix/backup-plan")
assert not plan["snapshot_verified"] and any(s["kopia_path"]=="/source/content/kiwix" for s in plan["sources"]),plan
assert not api("/api/admin/backups/core")["snapshot_verified"]
versions=api("/api/admin/modules/kiwix/versions")
assert versions["registry_checked"] is False and versions["services"][0]["comparison"]=="matches local target",versions
assert versions["services"][0]["installed_image_ids"]
registry=api("/api/admin/modules/kiwix/registry-check",{})
assert registry["digest_pinned"] and registry["installed_image_ids"]==versions["services"][0]["installed_image_ids"],registry
assert registry["comparison"] in ("matches configured registry image","unavailable"),registry
if registry["comparison"]=="unavailable":
    print("Live registry metadata check unavailable; no match claimed.",registry,flush=True)
else:
    print("Live configured registry digest matched installed Kiwix.",flush=True)
assert api("/api/admin/modules/kiwix/versions")["services"][0]["installed_image_ids"]==registry["installed_image_ids"]
with urllib.request.urlopen("http://127.0.0.1:8081/",timeout=10) as response:
    assert response.status==200
# Exercise native indexing and real reader catalog reload with a local fixture.
def local_action(action):
    assert api("/api/admin/content/local",{"name":"fixture.zim","action":action})["ok"]
def reader_contains(expected):
    import xml.etree.ElementTree as ET
    deadline=time.monotonic()+60
    while time.monotonic()<deadline:
        with urllib.request.urlopen("http://127.0.0.1:8081/catalog/v2/entries",timeout=10) as response:
            root=ET.fromstring(response.read())
        entries=root.findall("{http://www.w3.org/2005/Atom}entry")
        if bool(entries)==expected:
            return
        time.sleep(2)
    raise AssertionError("Reader catalog did not reload to expected state")
local_action("index")
assert any(x["name"]=="fixture.zim" and x["indexed"] for x in api("/api/admin/content/local")["files"])
reader_contains(True)
local_action("remove")
reader_contains(False)
assert any(x["name"]=="fixture.zim" for x in api("/api/admin/content/local")["removed"])
local_action("restore")
reader_contains(True)
local_action("remove")
reader_contains(False)
local_action("purge")
assert not any(x["name"]=="fixture.zim" for x in api("/api/admin/content/local")["removed"])
print("Native local archive indexing, reader reload, remove, restore and purge passed.")
action("stop")
assert module()["status"]=="stopped"
action("start")
assert module()["status"]=="running"
action("restart")
assert module()["status"]=="running"
action("uninstall")
assert module()["status"]=="not installed"
assert Path("content/kiwix/library.xml").is_file()
print("Kiwix Compose lifecycle passed; content preserved.")

# Exercise the same lifecycle for the new inventory and backup services.
for ident, port in [("homebox",8082),("grocy",8083),("kopia",51515)]:
    if ident=="homebox":
        wait_job(batch["ids"][1],"homebox initial install")
    else:
        assert module(ident)["status"]=="not installed"
        action("install",ident)
    assert module(ident)["status"]=="running"
    if ident=="kopia":
        import base64
        credentials=api("/api/admin/kopia/credentials",{})
        auth=base64.b64encode((credentials["username"]+":"+credentials["ui_password"]).encode()).decode()
        req=urllib.request.Request("http://127.0.0.1:51515/",headers={"Authorization":"Basic "+auth})
        with urllib.request.urlopen(req,timeout=10) as response:
            assert response.status==200
        assert api("/api/admin/kopia/status")["connection"]=="not connected"
        job=api("/api/admin/kopia/initialize",{"confirmed":True})["id"]
        wait_job(job,"create disposable Kopia repository")
        connected=api("/api/admin/kopia/status")
        assert connected=={"connection":"connected","storage_type":"filesystem","snapshot_verified":False},connected
        # Reopen from persistent config and repository rather than assuming an
        # upstream storage marker filename or host-side access permissions.
        action("restart","kopia")
        assert api("/api/admin/kopia/status")["connection"]=="connected"
        print("Native Kopia creation and persistent reconnection passed.",flush=True)
        core_snapshot=api("/api/admin/backups/core/snapshot",{"confirmed":True})["id"]
        wait_job(core_snapshot,"private core database snapshot")
        core_record=next(j for j in api("/api/admin/jobs") if j["id"]==core_snapshot)
        assert "Core database export snapshot:" in core_record["log"]
        assert subprocess.run(["sudo","test","!","-e","data/core/recovery-export"]).returncode==0
        assert api("/api/admin/status")
        print("Consistent core database export, snapshot and staging cleanup passed.",flush=True)
        core_verify=api("/api/admin/backups/core/verify-snapshot",{"confirmed":True})["id"]
        wait_job(core_verify,"isolated core restore verification")
        core_restored=next(j for j in api("/api/admin/jobs") if j["id"]==core_verify)
        assert "administrator present and sessions absent" in core_restored["log"] and "content metadata verified" in core_restored["log"]
        assert api("/api/admin/status")
        import re
        core_target=re.search(r"Isolated restore directory: (/restore/aftergrid-core-[0-9]+-[a-f0-9]{16})",core_restored["log"]).group(1)
        restored_db=Path("restore")/core_target.removeprefix("/restore/")/"data/core.sqlite3"
        subprocess.run(["sudo","python3","-c","import sqlite3,sys,pathlib; c=sqlite3.connect(pathlib.Path(sys.argv[1]).resolve().as_uri()+\"?mode=ro&immutable=1\",uri=True); assert c.execute(\"SELECT username,server_name FROM admin\").fetchone()==(\"admin\",\"CI\"); assert c.execute(\"SELECT COUNT(*) FROM sessions\").fetchone()==(0,)",str(restored_db)],check=True)
        print("Isolated core database restore, expected administrator and absent sessions passed.",flush=True)
        worker_snapshot=api("/api/admin/backups/worker/snapshot",{"confirmed":True})["id"]
        wait_job(worker_snapshot,"private worker state snapshot")
        worker_record=next(j for j in api("/api/admin/jobs") if j["id"]==worker_snapshot)
        assert "Worker state export snapshot:" in worker_record["log"] and "2 secret sets" in worker_record["log"]
        assert subprocess.run(["docker","exec","aftergrid-kopia-kopia-1","test","!","-e","/tmp/aftergrid-worker-export"]).returncode==0
        assert api("/api/admin/status")
        print("Private worker state and generated secret snapshot, staging cleanup passed.",flush=True)
        worker_verify=api("/api/admin/backups/worker/verify-snapshot",{"confirmed":True})["id"]
        wait_job(worker_verify,"isolated worker restore verification")
        worker_restored=next(j for j in api("/api/admin/jobs") if j["id"]==worker_verify)
        assert "Exact worker envelope digest" in worker_restored["log"] and "2 reviewed secret sets verified" in worker_restored["log"]
        target=re.search(r"Isolated restore directory: (/restore/aftergrid-worker-[0-9]+-[a-f0-9]{16})",worker_restored["log"]).group(1)
        # Compare actual captured native secrets without printing either copy.
        envelope=subprocess.check_output(["sudo","cat",str(Path("restore")/target.removeprefix("/restore/")/"data/worker-recovery.json")])
        check=subprocess.run(["docker","compose","exec","-T","worker","python3","-c","import json,sys,pathlib,hmac; v=json.load(sys.stdin); assert set(v[\"secrets\"])=={\"homebox\",\"kopia\"}; assert all(hmac.compare_digest(secret,json.loads((pathlib.Path(\"/worker-state/secrets\")/(ident+\".json\")).read_text())[key]) for ident,fields in v[\"secrets\"].items() for key,secret in fields.items())"],input=envelope,capture_output=True)
        assert check.returncode==0,"restored worker secret comparison failed"
        del envelope,check
        print("Isolated worker recovery and exact generated secret comparison passed.",flush=True)
        action("install","grocy")
        snapshot_job=api("/api/admin/modules/grocy/snapshot",{"confirmed":True})["id"]
        wait_job(snapshot_job,"quiesced Grocy snapshot")
        assert module("grocy")["status"]=="running"
        record=next(j for j in api("/api/admin/jobs") if j["id"]==snapshot_job)
        assert "Native snapshot reported complete:" in record["log"]
        assert "restore not verified" in record["stage"]
        print("Managed Grocy snapshot and prior running state restoration passed.",flush=True)
        restore_job=api("/api/admin/modules/grocy/verify-snapshot",{"confirmed":True})["id"]
        wait_job(restore_job,"isolated Grocy restore")
        verification=next(j for j in api("/api/admin/jobs") if j["id"]==restore_job)
        assert "SQLite integrity and expected schema passed" in verification["log"]
        print("Isolated Grocy restore and SQLite integrity passed.",flush=True)
        assert module("grocy")["status"]=="running"
        action("uninstall","grocy")
        action("install","homebox")
        homebox_snapshot=api("/api/admin/modules/homebox/snapshot",{"confirmed":True})["id"]
        wait_job(homebox_snapshot,"quiesced Homebox snapshot")
        assert module("homebox")["status"]=="running"
        homebox_restore=api("/api/admin/modules/homebox/verify-snapshot",{"confirmed":True})["id"]
        wait_job(homebox_restore,"isolated Homebox restore")
        restored=next(j for j in api("/api/admin/jobs") if j["id"]==homebox_restore)
        assert "SQLite integrity and expected schema passed" in restored["log"]
        assert "pepper is outside this snapshot" in restored["log"]
        action("uninstall","homebox")
        print("Homebox managed snapshot and isolated database restore passed.",flush=True)
    else:
        with urllib.request.urlopen("http://127.0.0.1:"+str(port)+"/",timeout=10) as response:
            assert response.status==200
    if ident in ("homebox","grocy","kopia"):
        def inspect_container():
            cid=subprocess.check_output(["docker","ps","-q","--filter","label=com.docker.compose.project=aftergrid-"+ident],text=True).strip()
            return json.loads(subprocess.check_output(["docker","inspect",cid],text=True))[0]
        def check_bind(host):
            bindings=inspect_container()["HostConfig"]["PortBindings"]
            published=[entry for entries in bindings.values() for entry in entries]
            assert published and all(entry["HostIp"]==host for entry in published)
        check_bind("127.0.0.1")
        assert module(ident)["share_available"]
        action("share",ident)
        assert module(ident)["shared"]
        assert module(ident)["lan_url"]=="http://"+ident+".aftergrid.home.arpa:"+str(port)
        check_bind(os.environ["AFTERGRID_LAN_BIND"])
        if ident=="homebox":
            env=inspect_container()["Config"]["Env"]
            assert "HBOX_OPTIONS_ALLOW_REGISTRATION=false" in env
            assert "HBOX_OPTIONS_HOSTNAME=http://homebox.aftergrid.home.arpa:8082" in env
        action("unshare",ident)
        assert not module(ident)["shared"]
        check_bind("127.0.0.1")
        if ident=="homebox":
            assert "HBOX_OPTIONS_ALLOW_REGISTRATION=false" in inspect_container()["Config"]["Env"]
        print(ident+" LAN binding and local-only reconfiguration passed.")
    action("stop",ident)
    assert module(ident)["status"]=="stopped"
    action("start",ident)
    assert module(ident)["status"]=="running"
    # Keep the already-pulled native repository online for the rest of the smoke test.
    # Its uninstall/persistence acceptance is exercised at the end.
    if ident!="kopia":
        action("uninstall",ident)
        assert module(ident)["status"]=="not installed"
    assert Path("data",ident).is_dir()
    print(ident+" lifecycle passed; data directory retained.")

def verify_content_backup(ident):
    snap=api("/api/admin/backups/content/"+ident+"/snapshot",{"confirmed":True})["id"]
    wait_job(snap,"managed "+ident+" content snapshot")
    verify=api("/api/admin/backups/content/"+ident+"/verify",{"confirmed":True})["id"]
    wait_job(verify,"native "+ident+" content read verification")
    record=next(j for j in api("/api/admin/jobs") if j["id"]==verify)
    assert "zero reported errors. No files restored." in record["log"]
    print(ident+" native content snapshot and full read verification passed.",flush=True)

verify_content_backup("kiwix")
# Maps starts without downloading any demo data, then serves a local fixture.
assert module("maps")["status"]=="not installed"
action("install","maps")
assert module("maps")["status"]=="running"
map_base="http://127.0.0.1:8084"
with urllib.request.urlopen(map_base+"/data.json",timeout=10) as response:
    assert json.load(response)==[]
import shutil
subprocess.run(["sudo","cp",os.environ["MAP_FIXTURE"],"content/maps/region.pmtiles"],check=True)
subprocess.run(["docker","compose","exec","-T","core","pmtiles","verify","/content/maps/region.pmtiles"],check=True)
assert any(x["name"]=="region.pmtiles" for x in api("/api/admin/maps")["files"])
for asset in ("/maps","/maps.js","/maps.css","/region.js","/map-assets/land.geojson","/map-assets/licenses/basemaps.txt","/map-assets/maplibre-gl.js","/map-assets/pmtiles.js","/map-assets/basemaps.js","/map-assets/fonts/Noto%20Sans%20Regular/0-255.pbf","/map-assets/sprites/v4/light.json"):
    with urllib.request.urlopen(BASE+asset,timeout=10) as response:
        assert response.status==200 and response.read(1)
request=urllib.request.Request(BASE+"/maps/archive.pmtiles",headers={"Range":"bytes=0-6"})
with urllib.request.urlopen(request,timeout=10) as response:
    assert response.status==206 and response.read()==b"PMTiles"
action("restart","maps")
with urllib.request.urlopen(map_base+"/data/region-pmtiles.json",timeout=10) as response:
    tilejson=json.load(response)
    assert tilejson["tiles"]
    url=tilejson["tiles"][0].replace("{z}","0").replace("{x}","0").replace("{y}","0")
    assert url.startswith(map_base+"/")
with urllib.request.urlopen(url,timeout=10) as response:
    assert response.status==200 and response.headers.get_content_type().startswith("image/") and len(response.read())>0
with urllib.request.urlopen(map_base+"/",timeout=10) as response:
    assert response.status==200
    assert b"region-pmtiles" in response.read()
action("stop","maps")
assert module("maps")["status"]=="stopped"
action("start","maps")
assert module("maps")["status"]=="running"
action("uninstall","maps")
assert module("maps")["status"]=="not installed"
assert Path("content/maps/region.pmtiles").is_file()
print("Maps empty startup, local tile serving and lifecycle passed; map archive retained.")
verify_content_backup("maps")

# Native graph build and route calculation using the small pinned OSM fixture.
action("install","routing")
assert module("routing")["status"]=="running"
for mode in ("auto","pedestrian","bicycle"):
    result=api("/api/maps/route",{"start":[9.5209,47.1394],"end":[9.5238,47.1417],"mode":mode})
    assert result["distance_km"]>0 and result["duration_seconds"]>0 and len(result["coordinates"])>=2
    assert result["instructions"]
# Prepare a second graph without changing the selected first graph.
subprocess.run(["sudo","cp","content/routing/region.osm.pbf","content/routing/incoming.osm.pbf"],check=True)
action("prepare-graph","routing")
r=api("/api/admin/routing-data")
assert r["original_ready"] and r["candidate_ready"] and r["selected_slot"]=="tiles"
assert api("/api/maps/route",{"start":[9.5209,47.1394],"end":[9.5238,47.1417],"mode":"auto"})["distance_km"]>0
action("activate-graph","routing")
assert api("/api/admin/routing-data")["selected_slot"]=="tiles-next"
assert api("/api/maps/route",{"start":[9.5209,47.1394],"end":[9.5238,47.1417],"mode":"auto"})["distance_km"]>0
action("rollback-graph","routing")
assert api("/api/admin/routing-data")["selected_slot"]=="tiles"
assert api("/api/maps/route",{"start":[9.5209,47.1394],"end":[9.5238,47.1417],"mode":"auto"})["distance_km"]>0
assert api("/api/admin/routing-data")["candidate_ready"]
# Retain the old inactive slot, refill it, and build another replacement.
action("activate-graph","routing")
action("archive-original","routing")
r=api("/api/admin/routing-data")
assert r["selected_slot"]=="tiles-next" and r["candidate_ready"] and not r["original_occupied"]
assert any(a["complete"] for a in r["archives"])
subprocess.run(["sudo","cp","content/routing/incoming.osm.pbf","content/routing/region.osm.pbf"],check=True)
action("prepare-graph","routing")
assert api("/api/admin/routing-data")["original_ready"]
action("rollback-graph","routing")
assert api("/api/admin/routing-data")["selected_slot"]=="tiles"
assert api("/api/maps/route",{"start":[9.5209,47.1394],"end":[9.5238,47.1417],"mode":"auto"})["distance_km"]>0
# Native Osmium index from the selected real OSM fixture.
assert api("/api/admin/maps/places/build",{})["queued"]
deadline=time.monotonic()+120
while time.monotonic()<deadline:
    index=api("/api/admin/maps/places")
    if index["state"] in ("complete","failed"):break
    time.sleep(1)
assert index["ready"] and index["count"]>0,index
assert api("/api/maps/places?q=Vaduz")["results"]
print("Local Osmium place index and search passed.")

from browser_maps import browser_maps
browser_maps()
action("stop","routing")
assert module("routing")["status"]=="stopped"
action("start","routing")
assert module("routing")["status"]=="running"
action("uninstall","routing")
assert module("routing")["status"]=="not installed"
assert api("/api/admin/routing-data")["graph_ready"]
assert any(x["name"]=="region.osm.pbf" for x in api("/api/admin/routing-data")["files"])
print("Native routing graph, three costing modes and lifecycle passed.")
verify_content_backup("routing")

assert api("/api/maps/places?q=Vaduz")["results"]
print("Place index remains accessible with routing uninstalled.")

# Exercise managed recovery while Kopia remains connected, with no native admin jobs.
def verify_managed(ident,expected):
    import re
    snap=api("/api/admin/modules/"+ident+"/snapshot",{"confirmed":True})["id"]
    wait_job(snap,"quiesced "+ident+" snapshot")
    assert module(ident)["status"]=="running"
    verify=api("/api/admin/modules/"+ident+"/verify-snapshot",{"confirmed":True})["id"]
    wait_job(verify,"isolated "+ident+" restore")
    record=next(j for j in api("/api/admin/jobs") if j["id"]==verify)
    assert expected in record["log"],record["stage"]
    target=re.search(r"Isolated restore directory: (/restore/aftergrid-"+ident+r"-[0-9]+-[a-f0-9]{16})",record["log"]).group(1)
    assert module(ident)["status"]=="running"
    print(ident+" managed snapshot and isolated restore passed.",flush=True)
    return Path("restore")/target.removeprefix("/restore/")/"data"

# Native MeshMonitor lifecycle without radio hardware or remote broker.
action("install","meshmonitor")
assert module("meshmonitor")["status"]=="running"
creds=api("/api/admin/meshmonitor/credentials",{})
assert len(creds["initial_password"])==64 and creds["username"]=="admin"
meshbase="http://127.0.0.1:8085"
native=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
def mesh_login(password):
    with native.open(meshbase+"/api/csrf-token",timeout=20) as res:csrf=json.load(res)["csrfToken"]
    req=urllib.request.Request(meshbase+"/api/auth/login",data=json.dumps({"username":"admin","password":password}).encode(),headers={"Origin":meshbase,"Content-Type":"application/json","X-CSRF-Token":csrf})
    with native.open(req,timeout=20) as res:return json.load(res)
assert mesh_login(creds["initial_password"])["success"]
action("share","meshmonitor")
assert module("meshmonitor")["shared"]
action("unshare","meshmonitor")
assert not module("meshmonitor")["shared"]
action("stop","meshmonitor")
assert module("meshmonitor")["status"]=="stopped"
action("start","meshmonitor")
assert module("meshmonitor")["status"]=="running"
assert mesh_login(creds["initial_password"])["success"]
verify_managed("meshmonitor","SQLite integrity and expected schema passed")
assert mesh_login(creds["initial_password"])["success"]
action("uninstall","meshmonitor")
assert module("meshmonitor")["status"]=="not installed"
assert Path("data/meshmonitor").is_dir()
print("MeshMonitor native login, sharing and lifecycle passed; no radio hardware tested.")

# Native MicroTAK enrollment with a disposable CA, one-time bootstrap and TLS.
import ssl
import tempfile
import base64
import urllib.error
action("install","tak")
assert module("tak")["status"]=="running"
with tempfile.TemporaryDirectory() as tmp:
    folder=Path(tmp)
    ca=folder/"ca.pem"
    ca.write_bytes(subprocess.check_output(["sudo","cat","data/tak/data/ca-cert.pem"]))
    token=subprocess.check_output(["sudo","cat","data/tak/data/bootstrap-token"],text=True).strip()
    assert token
    tls=ssl.create_default_context(cafile=str(ca))
    opener=urllib.request.build_opener(urllib.request.HTTPSHandler(context=tls))
    endpoint="https://127.0.0.1:8446/Marti/api/tls/signClient/v2"
    key=folder/"client.key";csr=folder/"client.csr";cert=folder/"client.pem"
    subprocess.run(["openssl","req","-new","-newkey","rsa:2048","-nodes","-subj","/CN=admin","-keyout",str(key),"-out",str(csr)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    def enroll(secret=None):
        headers={"Content-Type":"application/pkcs10","Accept":"application/json"}
        if secret:headers["Authorization"]="Basic "+base64.b64encode(("admin:"+secret).encode()).decode()
        return opener.open(urllib.request.Request(endpoint,data=csr.read_bytes(),headers=headers),timeout=15)
    try:
        enroll()
        raise AssertionError("Unauthenticated enrollment unexpectedly succeeded")
    except urllib.error.HTTPError as exc:assert exc.code==403
    with enroll(token) as response:
        result=json.load(response)
        cert.write_text("-----BEGIN CERTIFICATE-----\n"+result["signedCert"]+"\n-----END CERTIFICATE-----\n")
    subprocess.run(["openssl","verify","-CAfile",str(ca),str(cert)],check=True)
    try:
        enroll(token)
        raise AssertionError("Bootstrap token unexpectedly reusable")
    except urllib.error.HTTPError as exc:assert exc.code in (403,409)
    # Native certificate-authenticated CoT TLS handshake; no live radio/client data.
    tls.load_cert_chain(str(cert),str(key))
    import socket
    with socket.create_connection(("127.0.0.1",8089),timeout=10) as sock:
        with tls.wrap_socket(sock,server_hostname="127.0.0.1") as secure:
            assert secure.version()
    action("share","tak")
    assert module("tak")["shared"]
    with urllib.request.urlopen("https://192.168.254.253:8446/Marti/api/tls/ca.pem",context=ssl.create_default_context(cafile=str(ca)),timeout=10) as response:
        assert response.read()==ca.read_bytes()
    action("unshare","tak")
    action("stop","tak")
    assert module("tak")["status"]=="stopped"
    action("start","tak")
    assert module("tak")["status"]=="running"
    with socket.create_connection(("127.0.0.1",8089),timeout=10) as sock:
        with tls.wrap_socket(sock,server_hostname="127.0.0.1") as secure:assert secure.version()
    recovered=verify_managed("tak","MicroTAK restored CA certificate presence passed")
    assert subprocess.check_output(["sudo","cat",str(recovered/"data/ca-cert.pem")])==ca.read_bytes()
    with socket.create_connection(("127.0.0.1",8089),timeout=10) as sock:
        with tls.wrap_socket(sock,server_hostname="127.0.0.1") as secure:assert secure.version()
    action("uninstall","tak")
    assert module("tak")["status"]=="not installed"
    assert subprocess.check_output(["sudo","cat","data/tak/data/ca-cert.pem"])==ca.read_bytes()
print("MicroTAK TLS enrollment, bootstrap rejection/reuse, certificate handshake, sharing and retained CA passed.")

# Official Kolibri image, both local ports, native data and stable node identity.
action("install","kolibri")
assert module("kolibri")["status"]=="running"
with urllib.request.urlopen("http://127.0.0.1:8086/",timeout=20) as response:
    assert response.status==200 and response.read(1)
def kolibri_identity():
    return subprocess.check_output(["sudo","cat","data/kolibri/.node_id"]).strip()
identity=kolibri_identity()
assert identity
def kolibri_bindings():
    ids=subprocess.check_output(["docker","compose","-p","aftergrid-kolibri","-f","modules/kolibri/compose.yaml","ps","-q"],text=True).split()
    assert len(ids)==1
    return json.loads(subprocess.check_output(["docker","inspect",ids[0]],text=True))[0]["NetworkSettings"]["Ports"]
for port in ("8086/tcp","8087/tcp"):
    assert any(p["HostIp"]=="127.0.0.1" for p in kolibri_bindings()[port])
# Disposable native provisioning. Do not use these credentials on a real host.
subprocess.run(["docker","exec","-u","kolibri","aftergrid-kolibri-kolibri-1","kolibri","manage","provisiondevice","--noinput","--facility","AfterGrid CI","--superusername","ciadmin","--superuserpassword","disposable-education-test-password","--language_id","en","--preset","nonformal"],check=True)
action("share","kolibri")
assert module("kolibri")["shared"]
for port in ("8086/tcp","8087/tcp"):
    assert any(p["HostIp"]=="192.168.254.253" for p in kolibri_bindings()[port])
action("unshare","kolibri")
action("stop","kolibri")
assert module("kolibri")["status"]=="stopped"
action("start","kolibri")
assert module("kolibri")["status"]=="running" and kolibri_identity()==identity
recovered=verify_managed("kolibri","SQLite integrity and expected schema passed")
assert subprocess.check_output(["sudo","cat",str(recovered/".node_id")]).strip()==identity
action("uninstall","kolibri")
assert module("kolibri")["status"]=="not installed" and kolibri_identity()==identity
print("Kolibri native setup, dual-port sharing, lifecycle and persistent identity passed.")

# Native media server: local setup, read-only content, authentication and retained state.
import wave
fixture=Path("content/media/fixture.wav")
with tempfile.TemporaryDirectory() as tmp:
    wav=Path(tmp)/"fixture.wav"
    with wave.open(str(wav),"wb") as audio:
        audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(8000);audio.writeframes(b"\0\0"*8000)
    subprocess.run(["sudo","cp",str(wav),str(fixture)],check=True)
action("install","media")
assert module("media")["status"]=="running"
media_base="http://127.0.0.1:8096"
media_auth='MediaBrowser Client="AfterGrid CI", Device="CI", DeviceId="aftergrid-disposable-ci", Version="1.0"'
def media_request(path,body=None,token=None):
    headers={"Authorization":media_auth+((', Token="'+token+'"') if token else ""),"Content-Type":"application/json"}
    req=urllib.request.Request(media_base+path,data=None if body is None else json.dumps(body).encode(),headers=headers)
    with urllib.request.urlopen(req,timeout=30) as response:
        raw=response.read()
        return json.loads(raw) if raw else None
assert media_request("/System/Info/Public")["StartupWizardCompleted"] is False
media_request("/Startup/User")
media_request("/Startup/Configuration",{"ServerName":"AfterGrid CI","UICulture":"en-US","MetadataCountryCode":"US","PreferredMetadataLanguage":"en"})
media_request("/Startup/User",{"Name":"ciadmin","Password":"disposable-media-test-password"})
media_request("/Startup/RemoteAccess",{"EnableRemoteAccess":False})
media_request("/Startup/Complete",{})
def media_login():
    return media_request("/Users/AuthenticateByName",{"Username":"ciadmin","Pw":"disposable-media-test-password"})
session=media_login()
assert session["AccessToken"]
media_request("/Library/VirtualFolders?name=Local%20Audio&collectionType=music&paths=%2Fmedia&refreshLibrary=false",{"LibraryOptions":{"EnableInternetProviders":False,"SaveLocalMetadata":False,"EnableRealtimeMonitor":False,"MetadataFetchers":[],"ImageFetchers":[]}},session["AccessToken"])
assert any(x["Name"]=="Local Audio" for x in media_request("/Library/VirtualFolders",token=session["AccessToken"]))
container_id="aftergrid-media-media-1"
inspection=json.loads(subprocess.check_output(["docker","inspect",container_id],text=True))[0]
assert any(m["Destination"]=="/media" and not m["RW"] for m in inspection["Mounts"])
subprocess.run(["docker","exec",container_id,"test","-r","/media/fixture.wav"],check=True)
action("share","media")
assert module("media")["shared"]
inspection=json.loads(subprocess.check_output(["docker","inspect",container_id],text=True))[0]
assert any(p["HostIp"]=="192.168.254.253" for p in inspection["NetworkSettings"]["Ports"]["8096/tcp"])
action("unshare","media")
action("stop","media")
assert module("media")["status"]=="stopped"
action("start","media")
assert module("media")["status"]=="running"
assert media_login()["AccessToken"]
verify_managed("media","Jellyfin restored system configuration presence passed")
assert media_login()["AccessToken"]
action("uninstall","media")
assert module("media")["status"]=="not installed"
assert fixture.is_file()
assert subprocess.run(["sudo","test","-f","data/media/config/config/system.xml"]).returncode==0 or subprocess.run(["sudo","test","-f","data/media/config/system.xml"]).returncode==0
print("Jellyfin native setup, library, authentication, read-only media, sharing and lifecycle passed.")
verify_content_backup("media")

# Native DokuWiki installer and edit flow, using disposable credentials.
from playwright.sync_api import sync_playwright, expect
action("install","notes")
assert module("notes")["status"]=="running"
notes_base="http://127.0.0.1:8097"
def notes_binding(host):
    inspect=json.loads(subprocess.check_output(["docker","inspect","aftergrid-notes-notes-1"],text=True))[0]
    assert any(p["HostIp"]==host for p in inspect["NetworkSettings"]["Ports"]["8080/tcp"])
notes_binding("127.0.0.1")
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    context=browser.new_context(service_workers="block")
    context.route("**/*",lambda route: route.continue_() if route.request.url.startswith(notes_base+"/") else route.abort())
    page=context.new_page()
    page.goto(notes_base+"/install.php")
    for field,value in {"title":"AfterGrid CI","superuser":"ciadmin","fullname":"CI Administrator","email":"ci@example.invalid","password":"disposable-wiki-test-password","confirm":"disposable-wiki-test-password"}.items():
        page.locator("#"+field).fill(value)
    page.locator("#acl").check()
    page.locator("#policy").select_option("2")
    page.locator("#allowreg").uncheck()
    page.locator("#pop").uncheck()
    page.locator("button[name=submit]").click()
    page.goto(notes_base+"/doku.php?id=emergency:fixture&do=login")
    page.locator("input[name=u]").fill("ciadmin")
    page.locator("input[name=p]").fill("disposable-wiki-test-password")
    page.locator("form#dw__login button[type=submit], form#dw__login input[type=submit]").first.click()
    page.goto(notes_base+"/doku.php?id=emergency:fixture&do=edit")
    page.locator("textarea[name=wikitext]").fill("====== AfterGrid private fixture ======\n\nLocal emergency checklist.")
    page.locator("#edbtn__save").click()
    expect(page.locator("body")).to_contain_text("Local emergency checklist.")
    guest=browser.new_context(service_workers="block")
    guest.route("**/*",lambda route: route.continue_() if route.request.url.startswith(notes_base+"/") else route.abort())
    public=guest.new_page()
    public.goto(notes_base+"/doku.php?id=emergency:fixture")
    expect(public.locator("body")).not_to_contain_text("Local emergency checklist.")
    guest.close()
    browser.close()
assert subprocess.run(["sudo","test","-f","data/notes/conf/users.auth.php"]).returncode==0
# Reuse the initialized repository without an unnecessary second registry pull.
assert api("/api/admin/kopia/status")["connection"]=="connected"
notes_snapshot=api("/api/admin/modules/notes/snapshot",{"confirmed":True})["id"]
wait_job(notes_snapshot,"quiesced DokuWiki snapshot")
assert module("notes")["status"]=="running"
notes_restore=api("/api/admin/modules/notes/verify-snapshot",{"confirmed":True})["id"]
wait_job(notes_restore,"isolated DokuWiki restore")
restored=next(j for j in api("/api/admin/jobs") if j["id"]==notes_restore)
assert "DokuWiki configuration, ACL/account files and page presence passed" in restored["log"]
# The disposable test knows the expected document contents, unlike generic validation.
import re
target=re.search(r"Isolated restore directory: (/restore/aftergrid-notes-[0-9]+-[a-f0-9]{16})",restored["log"]).group(1)
fixture=Path("restore")/target.removeprefix("/restore/")/"data/data/pages/emergency/fixture.txt"
assert b"Local emergency checklist." in subprocess.check_output(["sudo","cat",str(fixture)])
assert module("notes")["status"]=="running"
manifest_job=api("/api/admin/backups/recovery-manifest",{"confirmed":True})["id"]
wait_job(manifest_job,"recovery inventory")
manifest=api("/api/admin/backups/recovery-manifest")
assert manifest["manifest_job"]==manifest_job and not manifest["atomic"] and not manifest["complete_system_recovery"]
records={x["key"]:x for x in manifest["records"]}
assert len(records)==13 and all(x["repository_status"]=="present" for x in records.values())
assert records["worker"]["envelope_sha256"] and records["worker"]["verification"]=="isolated"
assert records["core"]["content_metadata_included"]
assert records["application/notes"]["verification"]=="isolated" and records["content/maps"]["verification"]=="read-only"
print("Native recovery inventory and exact snapshot verification evidence passed.",flush=True)
action("uninstall","kopia")
assert module("kopia")["status"]=="not installed" and Path("data/kopia").is_dir()
print("DokuWiki managed snapshot, isolated restore and private fixture comparison passed.",flush=True)
action("share","notes")
assert module("notes")["shared"]
notes_binding("192.168.254.253")
action("unshare","notes")
notes_binding("127.0.0.1")
action("stop","notes")
assert module("notes")["status"]=="stopped"
action("start","notes")
assert module("notes")["status"]=="running"
action("uninstall","notes")
assert module("notes")["status"]=="not installed"
assert b"Local emergency checklist." in subprocess.check_output(["sudo","cat","data/notes/data/pages/emergency/fixture.txt"])
print("DokuWiki native setup, private page, LAN sharing and data preservation passed.")
