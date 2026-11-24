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
        setup={**creds,"token":"one-time-secret","server_name":"Family"}
        assert client.post("/api/setup",json=setup).status_code==403
        assert client.post("/api/setup",json={**setup,"token":"wrong"},headers=ORIGIN).status_code==403
        assert client.post("/api/setup",json=setup,headers=ORIGIN).status_code==201
        assert not (tmp_path/"setup-token").exists()
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
