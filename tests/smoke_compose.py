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
    with client.open(req, timeout=30) as res:
        return json.load(res)

def module(ident="kiwix"):
    return next(m for m in api("/api/modules") if m["id"]==ident)

def action(name, ident="kiwix"):
    job_id=api("/api/admin/modules/"+ident+"/"+name,{})["id"]
    wait_job(job_id,name)

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
    action("uninstall",ident)
    assert module(ident)["status"]=="not installed"
    assert Path("data",ident).is_dir()
    print(ident+" lifecycle passed; data directory retained.")

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

assert api("/api/maps/places?q=Vaduz")["results"]
print("Place index remains accessible with routing uninstalled.")
