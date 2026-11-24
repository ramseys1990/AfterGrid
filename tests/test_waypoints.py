import xml.etree.ElementTree as ET
import pytest
from core.waypoints import MapPlans
from core.app import create_app
from fastapi.testclient import TestClient

def test_persistence_and_xml(tmp_path):
    p=MapPlans(tmp_path);p.init()
    ident=p.waypoint("Water & shelter","water",[-81,34])
    rid=p.save_route("Evacuation <A>","auto",[[-81,34],[-80,35]])
    assert MapPlans(tmp_path).get_route(rid)["coordinates"]==[[-81,34],[-80,35]]
    for fmt in ("gpx","kml"):
        assert ET.fromstring(p.export(fmt)) is not None
        assert b"Water &amp; shelter" in p.export(fmt)
        assert b"Evacuation &lt;A&gt;" in p.export(fmt,rid)
    with pytest.raises(ValueError):p.waypoint("Bad","water",[181,0])
    p.delete("waypoint",ident)
    assert not p.directory()["waypoints"]

def test_shared_read_admin_write(tmp_path):
    (tmp_path/"setup-token").write_text("token")
    origin={"Origin":"http://testserver"}
    body={"name":"Meeting","kind":"meeting","coords":[-81,34]}
    with TestClient(create_app(tmp_path)) as c:
        assert c.get("/api/maps/plans").status_code==403
        assert c.post("/api/admin/maps/waypoints",json=body,headers=origin).status_code==401
        assert c.post("/api/setup",json={"token":"token","username":"admin","password":"long test password"},headers=origin).status_code==201
        assert c.post("/api/admin/maps/waypoints",json=body).status_code==403
        assert c.post("/api/admin/maps/waypoints",json=body,headers=origin).status_code==200
        r=c.post("/api/admin/maps/routes",json={"name":"Plan","mode":"auto","coordinates":[[-81,34],[-80,35]]},headers=origin)
        assert r.status_code==200
        rid=r.json()["id"];c.cookies.clear()
        assert c.get("/api/maps/plans").json()["waypoints"][0]["name"]=="Meeting"
        assert c.get("/api/maps/export/gpx?route_id="+str(rid)).status_code==200
        assert c.post("/api/admin/maps/plans/delete",json={"kind":"route","id":rid},headers=origin).status_code==401
