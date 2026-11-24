import pytest
from core import map_downloads as m
from core.app import create_app
from fastapi.testclient import TestClient

def test_bounds_and_estimate():
    m.validate("20260101",[-81,34,-80,35],12)
    for bbox in [[-180,-85,180,85],[0,0,-1,2],[0,float("nan"),1,2]]:
        with pytest.raises(ValueError):m.validate("20260101",bbox,12)
    assert m.estimate_bytes("Extract transferred 22 MB (overfetch 0.05) for an archive size of 20 MB")==20_000_000
    with pytest.raises(ValueError):m.estimate_bytes("unexpected")
    args=m.command({"build":"20260101","bbox":[-81,34,-80,35],"zoom":12},"/tmp/output",True)
    assert args[2]=="https://build.protomaps.com/20260101.pmtiles" and "--dry-run" in args

def test_publish_only_after_verify(tmp_path,monkeypatch):
    content=tmp_path/"maps";content.mkdir()
    manager=m.MapDownloads(tmp_path,content)
    job={"build":"20260101","bbox":[-81,34,-80,35],"zoom":12,"estimate_bytes":1}
    monkeypatch.setattr(manager,"check_space",lambda size:None)
    def fake(args,seconds):
        if args[1]=="extract":
            from pathlib import Path
            Path(args[3]).write_bytes(b"archive")
        else:
            raise ValueError("bad archive")
    monkeypatch.setattr(manager,"run",fake)
    manager.execute(job,"downloading")
    assert manager.read()["state"]=="failed" and not (content/"region.pmtiles").exists()
    def success(args,seconds):
        if args[1]=="extract":fake(args,seconds)
    monkeypatch.setattr(manager,"run",success)
    manager.execute(job,"downloading")
    assert manager.read()["state"]=="complete"
    with pytest.raises(ValueError,match="occupied"):manager.storage()

def test_map_api_requires_admin(tmp_path):
    (tmp_path/"setup-token").write_text("token")
    with TestClient(create_app(tmp_path)) as c:
        assert c.get("/api/admin/maps").status_code==401
        origin={"Origin":"http://testserver"}
        assert c.post("/api/setup",json={"token":"token","username":"admin","password":"long test password"},headers=origin).status_code==201
        assert c.get("/api/admin/maps").json()["state"]=="idle"
        assert c.post("/api/admin/maps/download",json={}).status_code==403
        assert c.post("/api/admin/maps/download",json={},headers=origin).status_code==409
