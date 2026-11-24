import sqlite3
import pytest
from fastapi.testclient import TestClient
from core.app import create_app
from core.households import Households

ORIGIN={"Origin":"http://testserver"}
UUID="11111111-2222-3333-4444-555555555555"

def test_household_references_persist(tmp_path):
    h=Households(tmp_path);h.init()
    a=h.save_household("House A");b=h.save_household("House B")
    assert a!=b
    x=h.save_location("homebox",UUID,"Generator shed",a,b)
    h.save_location("grocy","12","Shared pantry",None,None)
    assert Households(tmp_path).view()["locations"][1]["owner_id"]==a
    with pytest.raises(sqlite3.IntegrityError):h.delete_household(b)
    with pytest.raises(sqlite3.IntegrityError):h.save_location("homebox",UUID,"duplicate",a,b)
    with pytest.raises(ValueError):h.save_location("grocy","../x","bad",a,b)
    h.save_household("House B renamed",b)
    assert any(l["storage_name"]=="House B renamed" for l in h.view()["locations"])
    h.save_location("homebox",UUID,"Generator shed",a,None,x)
    h.delete_household(b)
    h.delete_location(x)
    assert len(h.view()["locations"])==1

def test_shared_read_admin_write(tmp_path):
    (tmp_path/"setup-token").write_text("test-token")
    with TestClient(create_app(tmp_path)) as client:
        assert client.get("/api/households").status_code==403
        assert client.post("/api/admin/households",json={"name":"House A"},headers=ORIGIN).status_code==401
        setup={"username":"admin","password":"long test password","token":"test-token"}
        assert client.post("/api/setup",json=setup,headers=ORIGIN).status_code==201
        assert client.post("/api/admin/households",json={"name":"House A"}).status_code==403
        r=client.post("/api/admin/households",json={"name":"House A"},headers=ORIGIN)
        assert r.status_code==200
        ident=r.json()["id"]
        body={"module":"grocy","native_id":"12","label":"Pantry","owner_id":ident}
        assert client.post("/api/admin/households/locations",json=body,headers=ORIGIN).status_code==200
        assert client.post("/api/admin/households/delete",json={"id":ident},headers=ORIGIN).status_code==409
        client.cookies.clear()
        assert client.get("/api/households").json()["locations"][0]["owner_name"]=="House A"
        assert client.post("/api/admin/households/locations/delete",json={"id":1},headers=ORIGIN).status_code==401
