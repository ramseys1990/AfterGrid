import hashlib
import pytest
from core import routing_downloads as m
from core.app import create_app
from fastapi.testclient import TestClient

def test_metadata_and_slots(tmp_path,monkeypatch):
    p=tmp_path/"routing";p.mkdir();manager=m.RoutingDownloads(tmp_path,p)
    assert m.url_for("sc").endswith("/us/south-carolina-latest.osm.pbf")
    with pytest.raises(ValueError):m.url_for("https://other.test")
    digest=hashlib.md5(b"pbf",usedforsecurity=False).hexdigest()
    assert m.parse_md5((digest+"  south-carolina-latest.osm.pbf\n").encode(),"south-carolina-latest.osm.pbf")==digest
    with pytest.raises(ValueError):m.parse_md5((digest+"  wrong.pbf").encode(),"expected.pbf")
    monkeypatch.setattr(m,"metadata",lambda region:(3,digest))
    monkeypatch.setattr(manager,"check_space",lambda size:None)
    job={"region":"sc","size_bytes":3,"digest":digest,"slot":"region.osm.pbf"}
    monkeypatch.setattr(manager,"transfer",lambda url,path,size,job:path.write_bytes(b"bad"))
    manager.execute(job,"downloading")
    assert manager.read()["state"]=="failed" and not (p/"region.osm.pbf").exists()
    monkeypatch.setattr(manager,"transfer",lambda url,path,size,job:path.write_bytes(b"pbf"))
    manager.execute(job,"downloading")
    assert manager.read()["state"]=="complete" and (p/"region.osm.pbf").read_bytes()==b"pbf"
    assert manager.slot()=="incoming.osm.pbf"
    (p/"tiles").mkdir();(p/"tiles/.aftergrid-ready").touch()
    manager.execute({**job,"slot":"incoming.osm.pbf"},"downloading")
    assert manager.status()["graph_ready"] and (p/"incoming.osm.pbf").read_bytes()==b"pbf"
    with pytest.raises(ValueError):manager.slot()

def test_routing_data_api(tmp_path):
    (tmp_path/"setup-token").write_text("token")
    origin={"Origin":"http://testserver"}
    with TestClient(create_app(tmp_path)) as c:
        assert c.get("/api/admin/routing-data").status_code==401
        assert c.post("/api/setup",json={"token":"token","username":"admin","password":"long test password"},headers=origin).status_code==201
        assert c.get("/api/admin/routing-data").json()["state"]=="idle"
        assert c.post("/api/admin/routing-data/estimate",json={"region":"sc"}).status_code==403
        assert c.post("/api/admin/routing-data/estimate",json={"region":"invalid"},headers=origin).status_code==400
        assert c.post("/api/admin/routing-data/download",json={},headers=origin).status_code==409
