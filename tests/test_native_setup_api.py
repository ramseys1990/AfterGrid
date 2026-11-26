import json
import pytest
from fastapi.testclient import TestClient
from core import app

ORIGIN={"Origin":"http://127.0.0.1:8080"}
ACCOUNT={"username":"admin@aftergrid.home.arpa","password":"native-test-password-123!","current_password":"","confirmed":True}

def configure(tmp_path,monkeypatch):
    monkeypatch.setenv("AFTERGRID_ORIGIN",ORIGIN["Origin"])
    (tmp_path/"setup-token").write_text("test-token")
    client=TestClient(app.create_app(tmp_path));client.__enter__()
    payload={"username":"admin","password":"portal-test-password-123!","token":"test-token","server_name":"Test"}
    assert client.post("/api/setup",json=payload,headers=ORIGIN).status_code==201
    return client

def test_native_setup_requires_admin_origin_confirmation_and_private_destination(tmp_path,monkeypatch):
    calls=[]
    monkeypatch.setattr(app,"call",lambda path,payload=None:(calls.append((path,payload)) or (202,{"id":12})))
    client=configure(tmp_path,monkeypatch)
    try:
        assert client.post("/api/admin/native-setup/homebox",json=ACCOUNT).status_code==403
        assert client.post("/api/admin/native-setup/homebox",json={**ACCOUNT,"confirmed":False},headers=ORIGIN).status_code==409
        assert client.post("/api/admin/native-setup/kiwix",json=ACCOUNT,headers=ORIGIN).status_code==400
        response=client.post("/api/admin/native-setup/homebox",json=ACCOUNT,headers=ORIGIN)
        assert response.status_code==202 and response.json()=={"id":12}
        assert calls[-1]==("/native-setup",{"module":"homebox","account":{k:v for k,v in ACCOUNT.items() if k!="confirmed"}})
        assert ACCOUNT["password"] not in response.text
        assert client.post("/api/logout",json={},headers=ORIGIN).status_code==200
        assert client.post("/api/admin/native-setup/homebox",json=ACCOUNT,headers=ORIGIN).status_code==401
    finally:client.__exit__(None,None,None)

@pytest.mark.parametrize("changes",[{"password":"short-secret"},{"password":"x"*3000},{"extra":"secret"},{"password":False}])
def test_invalid_native_fields_never_echo_rejected_credentials(tmp_path,monkeypatch,changes):
    client=configure(tmp_path,monkeypatch)
    try:
        payload={**ACCOUNT,**changes}
        response=client.post("/api/admin/native-setup/homebox",json=payload,headers=ORIGIN)
        assert response.status_code==400
        assert str(payload["password"]) not in response.text
        assert ACCOUNT["username"] not in response.text
    finally:client.__exit__(None,None,None)

@pytest.mark.parametrize("mode",["AFTERGRID_RECOVERY_CORE_ONLY","AFTERGRID_RECOVERY_OFFLINE"])
def test_native_setup_is_blocked_in_recovery(tmp_path,monkeypatch,mode):
    monkeypatch.setenv(mode,"1")
    client=configure(tmp_path,monkeypatch)
    try:
        assert client.post("/api/admin/native-setup/homebox",json=ACCOUNT,headers=ORIGIN).status_code==409
    finally:client.__exit__(None,None,None)
