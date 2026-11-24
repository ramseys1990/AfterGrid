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


def test_import_segments_and_atomic_rejection(tmp_path):
    p=MapPlans(tmp_path);p.init()
    raw='<gpx xmlns="http://www.topografix.com/GPX/1/1"><wpt lat="34" lon="-81"><name>Water</name></wpt><trk><name>Plan</name><trkseg><trkpt lat="34" lon="-81"/><trkpt lat="35" lon="-80"/></trkseg><trkseg><trkpt lat="36" lon="-79"/><trkpt lat="37" lon="-78"/></trkseg></trk></gpx>'
    assert p.import_file("gpx",raw)=={"waypoints":1,"routes":2}
    assert len(p.directory()["routes"])==2
    bad='<gpx><wpt lat="34" lon="-81"/><wpt lat="100" lon="0"/></gpx>'
    with pytest.raises(ValueError):p.import_file("gpx",bad)
    assert len(p.directory()["waypoints"])==1
    with pytest.raises(ValueError):p.import_file("kml",'<kml><NetworkLink><Link><href>https://example.org/file</href></Link></NetworkLink></kml>')
    with pytest.raises(ValueError):p.import_file("gpx",'<!DOCTYPE gpx [<!ENTITY x "a">]><gpx/>')
    kml='<kml xmlns="http://www.opengis.net/kml/2.2"><Document><Placemark><name>Shelter</name><Point><coordinates>-81,34,0</coordinates></Point></Placemark><Placemark><LineString><coordinates>-81,34 -80,35</coordinates></LineString></Placemark></Document></kml>'
    assert p.import_file("kml",kml)=={"waypoints":1,"routes":1}

def test_import_api(tmp_path):
    (tmp_path/"setup-token").write_text("token")
    origin={"Origin":"http://testserver","Content-Type":"application/xml"}
    raw=b'<gpx><wpt lat="34" lon="-81"><name>Water</name></wpt></gpx>'
    with TestClient(create_app(tmp_path)) as c:
        assert c.post("/api/admin/maps/import/gpx",content=raw,headers=origin).status_code==401
        assert c.post("/api/setup",json={"token":"token","username":"admin","password":"long test password"},headers={"Origin":"http://testserver"}).status_code==201
        assert c.post("/api/admin/maps/import/gpx",content=raw).status_code==403
        assert c.post("/api/admin/maps/import/gpx",content=raw,headers=origin).json()=={"waypoints":1,"routes":0}
        assert c.post("/api/admin/maps/import/gpx",content=b"x"*1000001,headers=origin).status_code==413
