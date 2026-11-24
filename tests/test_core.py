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
