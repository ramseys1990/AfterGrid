import pytest
from core.place_search import PlaceSearch,create_index,query_index
from core.app import create_app
from fastapi.testclient import TestClient

def test_local_index_and_source_changes(tmp_path):
    content=tmp_path/"routing";content.mkdir()
    (content/"region.osm.pbf").write_bytes(b"source")
    search=PlaceSearch(tmp_path,content)
    _,path,identity=search.source()
    features=[{"geometry":{"type":"Point","coordinates":[-81,34]},"properties":{"name":"Town Hospital","amenity":"hospital"}},{"geometry":{"type":"Point","coordinates":[-80,35]},"properties":{"addr:housenumber":"12","addr:street":"Main Street","addr:city":"Town"}}]
    create_index(path,features,identity)
    assert search.status()["ready"]
    assert search.search("town hosp")[0]["title"]=="Town Hospital"
    assert search.search("12 main")[0]["title"]=="12 Main Street"
    assert search.search('Town" OR nonexistent')==[]
    (content/"region.osm.pbf").write_bytes(b"changed")
    assert not search.status()["ready"]
    with pytest.raises(ValueError):search.search("Town")

def test_index_api_access(tmp_path,monkeypatch):
    monkeypatch.setenv("AFTERGRID_ROUTING_CONTENT",str(tmp_path/"missing"))
    (tmp_path/"setup-token").write_text("token")
    origin={"Origin":"http://testserver"}
    with TestClient(create_app(tmp_path)) as c:
        assert c.get("/api/maps/places?q=test").status_code==403
        assert c.get("/api/admin/maps/places").status_code==401
        assert c.post("/api/setup",json={"token":"token","username":"admin","password":"long test password"},headers=origin).status_code==201
        assert c.post("/api/admin/maps/places/build",json={}).status_code==403
        assert c.post("/api/admin/maps/places/build",json={},headers=origin).status_code==409
