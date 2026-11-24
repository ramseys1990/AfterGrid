from core.communications import Communications
from core.app import create_app
from fastapi.testclient import TestClient
import pytest

def test_plan_and_device_persistence(tmp_path):
    c=Communications(tmp_path);c.init()
    d={"label":"Radio A","method":"meshtastic","assigned":"Household","callsign":"A","notes":"Charge weekly"}
    ident=c.save("device",d);c.checked(ident)
    c.save("device",{**d,"label":"Radio B"},ident)
    p=c.save("plan",{"name":"Check-in","scope":"Shared","steps":{"primary":"Phone","alternate":"Mesh","contingency":"Radio","emergency":"Meet safely"}})
    r=Communications(tmp_path).directory()
    assert r["devices"][0]["label"]=="Radio B" and r["devices"][0]["checked"]
    assert r["plans"][0]["steps"]["alternate"]=="Mesh"
    with pytest.raises(ValueError):c.save("plan",{"name":"Bad","scope":"","steps":{"primary":"Phone"}})
    c.delete("plan",p);assert not c.directory()["plans"]

def test_access(tmp_path):
    (tmp_path/"setup-token").write_text("token")
    origin={"Origin":"http://testserver"}
    device={"label":"Radio","method":"meshcore"}
    plan={"name":"Check-in","primary":"Phone","alternate":"Mesh","contingency":"Radio","emergency":"Meet safely"}
    with TestClient(create_app(tmp_path)) as c:
        assert c.get("/api/communications").status_code==403
        assert c.post("/api/admin/communications/device",json=device,headers=origin).status_code==401
        assert c.post("/api/setup",json={"token":"token","username":"admin","password":"long test password"},headers=origin).status_code==201
        assert c.post("/api/admin/communications/device",json=device).status_code==403
        d=c.post("/api/admin/communications/device",json=device,headers=origin).json()["id"]
        assert c.post("/api/admin/communications/checked",json={"id":d},headers=origin).status_code==200
        assert c.post("/api/admin/communications/plan",json=plan,headers=origin).status_code==200
        c.cookies.clear()
        assert c.get("/api/communications").json()["plans"][0]["steps"]["primary"]=="Phone"
        assert c.post("/api/admin/communications/delete",json={"kind":"device","id":d},headers=origin).status_code==401
        assert c.get("/communications").status_code==200
