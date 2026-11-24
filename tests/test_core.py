from fastapi.testclient import TestClient
from core.app import create_app

ORIGIN = {"Origin":"http://testserver"}

def test_setup_login_restart(tmp_path):
    (tmp_path/"setup-token").write_text("one-time-secret")
    creds={"username":"admin","password":"correct horse battery staple"}
    with TestClient(create_app(tmp_path)) as client:
        assert client.get("/health").status_code==200
        assert client.get("/api/status").json()["setup_required"]
        assert client.get("/api/admin/status").status_code==401
        assert client.post("/api/admin/modules/kiwix/install",json={},headers=ORIGIN).status_code==401
        setup={**creds,"token":"one-time-secret","server_name":"Family"}
        assert client.post("/api/setup",json=setup).status_code==403
        assert client.post("/api/setup",json={**setup,"token":"wrong"},headers=ORIGIN).status_code==403
        assert client.post("/api/setup",json=setup,headers=ORIGIN).status_code==201
        assert not (tmp_path/"setup-token").exists()
        assert client.post("/api/admin/modules/kiwix/install",json={}).status_code==403
        assert client.get("/api/admin/status").status_code==200
        assert client.post("/api/setup",json=setup,headers=ORIGIN).status_code==409
        assert client.post("/api/logout",json={},headers=ORIGIN).status_code==200
        assert client.get("/api/admin/status").status_code==401
    with TestClient(create_app(tmp_path)) as client:
        assert client.get("/api/status").json()["server_name"]=="Family"
        assert client.post("/api/login",json={**creds,"password":"wrong"},headers=ORIGIN).status_code==401
        assert client.post("/api/login",json=creds,headers=ORIGIN).status_code==200
        assert client.get("/api/admin/status").status_code==200
        assert all(m["status"]=="planned" for m in client.get("/api/modules").json())
        assert client.get("/").status_code==200

def test_throttle(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        for _ in range(8):
            assert client.post("/api/login",json={"username":"x","password":"x"},headers=ORIGIN).status_code==401
        assert client.post("/api/login",json={"username":"x","password":"x"},headers=ORIGIN).status_code==429


def test_manifest_catalog_is_generic(tmp_path, monkeypatch):
    from core import app as core_app
    def fake_call(path, payload=None):
        if path == "/modules":
            return 200, [{"id":"new-app","name":"New App","description":"Example","category":"Tools","port":8099,"status":"not installed"}]
        assert payload == {"module":"new-app","action":"install"}
        return 202, {"id":1}
    monkeypatch.setattr(core_app,"call",fake_call)
    (tmp_path/"setup-token").write_text("test-token")
    with TestClient(create_app(tmp_path)) as client:
        assert any(m["id"]=="new-app" and m["installable"] for m in client.get("/api/modules").json())
        setup={"username":"admin","password":"long test password","token":"test-token","server_name":"Test"}
        assert client.post("/api/setup",json=setup,headers=ORIGIN).status_code==201
        assert client.post("/api/admin/modules/new-app/install",json={},headers=ORIGIN).status_code==202


def test_kopia_credentials_are_admin_only(tmp_path, monkeypatch):
    from core import app as core_app
    monkeypatch.setenv("AFTERGRID_ORIGIN","http://127.0.0.1:8080")
    monkeypatch.setattr(core_app,"call",lambda path: (200,{"username":"aftergrid","ui_password":"secret","repository_password":"secret2"}))
    (tmp_path/"setup-token").write_text("test-token")
    with TestClient(create_app(tmp_path)) as client:
        assert client.post("/api/admin/kopia/credentials",json={},headers={"Origin":"http://127.0.0.1:8080"}).status_code==401
        setup={"username":"admin","password":"long test password","token":"test-token","server_name":"Test"}
        assert client.post("/api/setup",json=setup,headers={"Origin":"http://127.0.0.1:8080"}).status_code==201
        assert client.get("/api/admin/kopia/credentials").status_code==405
        assert client.post("/api/admin/kopia/credentials",json={},headers={"Origin":"http://127.0.0.1:8080"}).json()["username"]=="aftergrid"


def test_first_run_selection(tmp_path, monkeypatch):
    from core import app as core_app
    calls=[]
    def fake_call(path,payload=None):
        calls.append((path,payload))
        assert path=="/jobs/batch"
        return 202,{"ids":[1,2]}
    monkeypatch.setattr(core_app,"call",fake_call)
    (tmp_path/"setup-token").write_text("test-token")
    with TestClient(create_app(tmp_path)) as client:
        assert client.post("/api/admin/first-run",json={"modules":[]},headers=ORIGIN).status_code==401
        setup={"username":"admin","password":"long test password","token":"test-token"}
        assert client.post("/api/setup",json=setup,headers=ORIGIN).status_code==201
        assert client.get("/api/status").json()["selection_pending"]
        assert client.post("/api/admin/first-run",json={"modules":[]}).status_code==403
        assert client.post("/api/admin/first-run",json={"modules":["kiwix","kiwix"]},headers=ORIGIN).status_code==400
        assert client.post("/api/admin/first-run",json={"modules":["kiwix","grocy"]},headers=ORIGIN).json()=={"ids":[1,2]}
        assert not client.get("/api/status").json()["selection_pending"]
        assert client.post("/api/admin/first-run",json={"modules":["grocy","kiwix"]},headers=ORIGIN).json()=={"ids":[1,2]}
        assert client.post("/api/admin/first-run",json={"modules":[]},headers=ORIGIN).status_code==409
        assert len(calls)==1

def test_first_run_skip_without_worker(tmp_path):
    (tmp_path/"setup-token").write_text("test-token")
    with TestClient(create_app(tmp_path)) as client:
        setup={"username":"admin","password":"long test password","token":"test-token"}
        assert client.post("/api/setup",json=setup,headers=ORIGIN).status_code==201
        assert client.post("/api/admin/first-run",json={"modules":[]},headers=ORIGIN).json()=={"ids":[]}
        assert not client.get("/api/status").json()["selection_pending"]


def test_sharing_requires_admin(tmp_path, monkeypatch):
    from core import app as core_app
    monkeypatch.setattr(core_app,"call",lambda path,payload=None: (202,{"id":7}))
    (tmp_path/"setup-token").write_text("test-token")
    with TestClient(create_app(tmp_path)) as client:
        assert client.post("/api/admin/modules/homebox/share",json={},headers=ORIGIN).status_code==401
        setup={"username":"admin","password":"long test password","token":"test-token"}
        assert client.post("/api/setup",json=setup,headers=ORIGIN).status_code==201
        assert client.post("/api/admin/modules/homebox/share",json={}).status_code==403
        assert client.post("/api/admin/modules/homebox/share",json={},headers=ORIGIN).json()=={"id":7}


def test_lan_kopia_credentials_require_origin(tmp_path, monkeypatch):
    from core import app as core_app
    origin="http://192.168.10.4:8080"
    monkeypatch.setenv("AFTERGRID_ORIGIN",origin)
    monkeypatch.setattr(core_app,"call",lambda path: (200,{"username":"aftergrid","ui_password":"secret","repository_password":"secret2"}))
    (tmp_path/"setup-token").write_text("test-token")
    with TestClient(create_app(tmp_path)) as client:
        setup={"username":"admin","password":"long test password","token":"test-token"}
        assert client.post("/api/setup",json=setup,headers={"Origin":origin}).status_code==201
        assert client.post("/api/admin/kopia/credentials",json={}).status_code==403
        assert client.post("/api/admin/kopia/credentials",json={},headers={"Origin":origin}).status_code==200


def test_content_catalog_admin_only(tmp_path,monkeypatch):
    from core import app as core_app
    monkeypatch.setattr(core_app,"search_catalog",lambda q,lang,start: {"entries":[],"total":0})
    (tmp_path/"setup-token").write_text("test-token")
    with TestClient(create_app(tmp_path)) as client:
        assert client.get("/api/admin/content/catalog").status_code==401
        setup={"username":"admin","password":"long test password","token":"test-token"}
        assert client.post("/api/setup",json=setup,headers=ORIGIN).status_code==201
        assert client.get("/api/admin/content/catalog?q=medicine").json()=={"entries":[],"total":0}
        assert client.get("/api/admin/content/catalog?start=-1").status_code==400
        assert client.get("/api/admin/content/local").status_code==200


def test_local_content_mutation_requires_admin_and_origin(tmp_path,monkeypatch):
    monkeypatch.setenv("AFTERGRID_KIWIX_CONTENT",str(tmp_path))
    (tmp_path/"setup-token").write_text("test-token")
    with TestClient(create_app(tmp_path)) as client:
        body={"name":"../other.zim","action":"remove"}
        assert client.post("/api/admin/content/local",json=body,headers=ORIGIN).status_code==401
        setup={"username":"admin","password":"long test password","token":"test-token"}
        assert client.post("/api/setup",json=setup,headers=ORIGIN).status_code==201
        assert client.post("/api/admin/content/local",json=body).status_code==403
        assert client.post("/api/admin/content/local",json=body,headers=ORIGIN).status_code==409


def test_meshmonitor_credentials_admin_only(tmp_path,monkeypatch):
    from core import app as core_app
    monkeypatch.setenv("AFTERGRID_ORIGIN","http://127.0.0.1:8080")
    monkeypatch.setattr(core_app,"call",lambda path:(200,{"username":"admin","initial_password":"initial-secret"}))
    (tmp_path/"setup-token").write_text("token")
    origin={"Origin":"http://127.0.0.1:8080"}
    with TestClient(create_app(tmp_path)) as client:
        assert client.post("/api/admin/meshmonitor/credentials",json={},headers=origin).status_code==401
        assert client.post("/api/setup",json={"token":"token","username":"admin","password":"long test password"},headers=origin).status_code==201
        assert client.post("/api/admin/meshmonitor/credentials",json={}).status_code==403
        assert client.post("/api/admin/meshmonitor/credentials",json={},headers=origin).json()["initial_password"]=="initial-secret"


def test_preparedness_shared_counts_no_private_fields(tmp_path,monkeypatch):
    from core import app as core_app
    root=tmp_path/"kiwix";root.mkdir()
    monkeypatch.setenv("AFTERGRID_KIWIX_CONTENT",str(root))
    monkeypatch.setattr(core_app,"local_inventory",lambda directory:{"files":[{"name":"private-name.zim","indexed":True},{"name":"not-indexed.zim","indexed":False}]})
    monkeypatch.setattr(core_app.MapDownloads,"status",lambda self:{"files":[{"name":"private-map"}],"output":"private-log"})
    monkeypatch.setattr(core_app.RoutingDownloads,"status",lambda self:{"graph_ready":True,"detail":"private-detail"})
    monkeypatch.setattr(core_app.Communications,"directory",lambda self:{"plans":[{"name":"private-plan"}],"devices":[{"checked":12},{"checked":None}]})
    (tmp_path/"setup-token").write_text("token")
    with TestClient(create_app(tmp_path)) as c:
        assert c.get("/api/preparedness").status_code==403
        assert c.post("/api/setup",json={"token":"token","username":"admin","password":"long test password"},headers=ORIGIN).status_code==201
        assert c.post("/api/admin/households",json={"name":"private-household"},headers=ORIGIN).status_code==200
        c.cookies.clear()
        response=c.get("/api/preparedness")
        assert response.status_code==200 and "private-" not in response.text
        r=response.json()
        assert r["knowledge"]=={"indexed":1,"unindexed":1}
        assert r["navigation"]=={"map_archives":1,"routing_graph_prepared":True,"waypoints":0,"saved_routes":0}
        assert r["communications"]=={"pace_plans":1,"device_records":2,"devices_ever_checked":1}
        assert r["resources"]=={"households":1,"mapped_locations":0}
        def unavailable(directory):raise OSError("private-path")
        monkeypatch.setattr(core_app,"local_inventory",unavailable)
        r=c.get("/api/preparedness").json()
        assert r["knowledge"] is None and r["resources"]["households"]==1
        import xml.etree.ElementTree as ET
        def malformed(directory):raise ET.ParseError("private-library")
        monkeypatch.setattr(core_app,"local_inventory",malformed)
        response=c.get("/api/preparedness")
        assert response.status_code==200 and response.json()["knowledge"] is None
        assert "private-library" not in response.text


def test_version_access_and_manual_update_confirmation(tmp_path,monkeypatch):
    from core import app as core_app
    calls=[]
    def fake(path,payload=None):
        calls.append((path,payload))
        return (200,{"registry_checked":False}) if path.startswith("/versions/") else (202,{"id":1})
    monkeypatch.setattr(core_app,"call",fake)
    (tmp_path/"setup-token").write_text("token")
    path="/api/admin/modules/kiwix/"
    with TestClient(create_app(tmp_path)) as c:
        assert c.get(path+"versions").status_code==401
        assert c.post("/api/setup",json={"token":"token","username":"admin","password":"long test password"},headers=ORIGIN).status_code==201
        assert c.get(path+"versions").json()=={"registry_checked":False}
        assert c.post(path+"update",json={},headers=ORIGIN).status_code==409
        assert c.post(path+"update",json={"backup_confirmed":"true"},headers=ORIGIN).status_code==422
        assert c.post(path+"update",json={"backup_confirmed":True}).status_code==403
        assert c.post("/api/admin/modules/routing/update",json={"backup_confirmed":True},headers=ORIGIN).status_code==409
        assert c.post(path+"update",json={"backup_confirmed":True},headers=ORIGIN).status_code==202
        assert calls==[("/versions/kiwix",None),("/jobs",{"module":"kiwix","action":"update","backup_confirmed":True})]


def test_registry_check_requires_admin_and_same_origin(tmp_path,monkeypatch):
    from core import app as core_app
    calls=[]
    def fake(path,payload=None,timeout=20):
        calls.append((path,payload,timeout))
        return 200,{"comparison":"unavailable"}
    monkeypatch.setattr(core_app,"call",fake)
    (tmp_path/"setup-token").write_text("token")
    path="/api/admin/modules/kiwix/registry-check"
    with TestClient(create_app(tmp_path)) as c:
        assert c.post(path,json={},headers=ORIGIN).status_code==401
        assert c.post("/api/setup",json={"token":"token","username":"admin","password":"long test password"},headers=ORIGIN).status_code==201
        assert c.post(path,json={}).status_code==403
        assert c.post(path,json={},headers=ORIGIN).json()=={"comparison":"unavailable"}
        assert calls==[("/registry-check",{"module":"kiwix"},45)]


def test_backup_plans_require_admin(tmp_path,monkeypatch):
    from core import app as core_app
    calls=[]
    def fake(path,payload=None):
        calls.append(path)
        return 200,{"module":"homebox","snapshot_verified":False}
    monkeypatch.setattr(core_app,"call",fake)
    (tmp_path/"setup-token").write_text("token")
    with TestClient(create_app(tmp_path)) as c:
        paths=["/api/admin/backups/core","/api/admin/modules/homebox/backup-plan"]
        assert all(c.get(path).status_code==401 for path in paths)
        assert c.post("/api/setup",json={"token":"token","username":"admin","password":"long test password"},headers=ORIGIN).status_code==201
        core=c.get(paths[0]).json()
        assert not core["snapshot_verified"] and any("Worker state" in x for x in core["missing"])
        assert c.get(paths[1]).json()["snapshot_verified"] is False
        assert calls==["/backup-plan/homebox"]
        c.cookies.clear()
        assert all(c.get(path).status_code==401 for path in paths)


def test_kopia_repository_admin_and_confirmation(tmp_path,monkeypatch):
    from core import app as core_app
    calls=[]
    def fake(path,payload=None):
        calls.append((path,payload))
        return (200,{"connection":"not connected","snapshot_verified":False}) if path=="/kopia/status" else (202,{"id":7})
    monkeypatch.setattr(core_app,"call",fake)
    (tmp_path/"setup-token").write_text("token")
    with TestClient(create_app(tmp_path)) as c:
        assert c.get("/api/admin/kopia/status").status_code==401
        assert c.post("/api/admin/kopia/initialize",json={"confirmed":True},headers=ORIGIN).status_code==401
        assert c.post("/api/setup",json={"token":"token","username":"admin","password":"long test password"},headers=ORIGIN).status_code==201
        assert c.get("/api/admin/kopia/status").json()["connection"]=="not connected"
        assert c.post("/api/admin/kopia/initialize",json={"confirmed":False},headers=ORIGIN).status_code==409
        assert c.post("/api/admin/kopia/initialize",json={"confirmed":True}).status_code==403
        assert c.post("/api/admin/kopia/initialize",json={"confirmed":True},headers=ORIGIN).status_code==202
        assert calls==[("/kopia/status",None),("/jobs",{"module":"kopia","action":"initialize-repository"})]


def test_snapshot_requires_admin_and_confirmation(tmp_path,monkeypatch):
    from core import app as core_app
    calls=[]
    def fake(path,payload=None):
        calls.append((path,payload))
        return 202,{"id":5}
    monkeypatch.setattr(core_app,"call",fake)
    (tmp_path/"setup-token").write_text("token")
    path="/api/admin/modules/grocy/snapshot"
    with TestClient(create_app(tmp_path)) as c:
        assert c.post(path,json={"confirmed":True},headers=ORIGIN).status_code==401
        assert c.post("/api/setup",json={"token":"token","username":"admin","password":"long test password"},headers=ORIGIN).status_code==201
        assert c.post(path,json={"confirmed":True}).status_code==403
        assert c.post(path,json={"confirmed":False},headers=ORIGIN).status_code==409
        assert c.post("/api/admin/modules/homebox/snapshot",json={"confirmed":True},headers=ORIGIN).status_code==400
        assert c.post(path,json={"confirmed":True},headers=ORIGIN).status_code==202
        assert calls==[("/jobs",{"module":"grocy","action":"snapshot"})]


def test_restore_verification_requires_admin_and_confirmation(tmp_path,monkeypatch):
    from core import app as core_app
    calls=[]
    def fake(path,payload=None):
        calls.append((path,payload))
        return 202,{"id":6}
    monkeypatch.setattr(core_app,"call",fake)
    (tmp_path/"setup-token").write_text("token")
    path="/api/admin/modules/grocy/verify-snapshot"
    with TestClient(create_app(tmp_path)) as c:
        assert c.post(path,json={"confirmed":True},headers=ORIGIN).status_code==401
        assert c.post("/api/setup",json={"token":"token","username":"admin","password":"long test password"},headers=ORIGIN).status_code==201
        assert c.post(path,json={"confirmed":True}).status_code==403
        assert c.post(path,json={"confirmed":False},headers=ORIGIN).status_code==409
        assert c.post(path,json={"confirmed":True},headers=ORIGIN).status_code==202
        assert calls==[("/jobs",{"module":"grocy","action":"verify-snapshot"})]
