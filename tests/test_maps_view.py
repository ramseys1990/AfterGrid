from fastapi.testclient import TestClient
from core.app import create_app

def test_map_range_and_csp(tmp_path,monkeypatch):
    content=tmp_path/"maps";content.mkdir()
    (content/"region.pmtiles").write_bytes(b"0123456789")
    monkeypatch.setenv("AFTERGRID_MAP_CONTENT",str(content))
    (tmp_path/"setup-token").write_text("token")
    with TestClient(create_app(tmp_path)) as c:
        assert c.get("/maps/archive.pmtiles").status_code==403
        assert c.post("/api/setup",json={"token":"token","username":"admin","password":"long test password"},headers={"Origin":"http://testserver"}).status_code==201
        c.cookies.clear()
        r=c.get("/maps/archive.pmtiles",headers={"Range":"bytes=2-5"})
        assert r.status_code==206 and r.content==b"2345"
        assert r.headers["content-range"]=="bytes 2-5/10"
        assert "worker-src blob:" in c.get("/maps").headers["content-security-policy"]
        assert "worker-src blob:" not in c.get("/").headers["content-security-policy"]
        assert c.get("/maps.js").status_code==200
        (content/"region.pmtiles").unlink()
        (content/"region.pmtiles").symlink_to(tmp_path/"core.sqlite3")
        assert c.get("/maps/archive.pmtiles").status_code==404
