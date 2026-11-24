import pytest
from core.routing import decode_shape,parse_route,route,RouteError
from core.app import create_app
from fastapi.testclient import TestClient

def test_geometry():
    assert decode_shape("??AA")==[[0,0],[.000001,.000001]]
    with pytest.raises(RouteError):decode_shape("?")
    result=parse_route({"trip":{"summary":{"length":1.5,"time":90},"legs":[{"shape":"??AA","maneuvers":[{"instruction":"Continue"}]}]}})
    assert result["distance_km"]==1.5 and result["instructions"]==["Continue"]
    with pytest.raises(ValueError):route([0,0],[1,1],"invalid")

def test_route_api(tmp_path,monkeypatch):
    from core import app
    monkeypatch.setattr(app,"route",lambda *args:{"coordinates":[[0,0],[1,1]],"distance_km":1,"duration_seconds":60,"instructions":[]})
    (tmp_path/"setup-token").write_text("token")
    origin={"Origin":"http://testserver"}
    body={"start":[0,0],"end":[1,1],"mode":"auto"}
    with TestClient(create_app(tmp_path)) as c:
        assert c.post("/api/maps/route",json=body,headers=origin).status_code==403
        assert c.post("/api/setup",json={"token":"token","username":"admin","password":"long test password"},headers=origin).status_code==201
        c.cookies.clear()
        assert c.post("/api/maps/route",json=body).status_code==403
        assert c.post("/api/maps/route",json=body,headers=origin).json()["distance_km"]==1


def test_native_alternates():
    from core.routing import parse_routes
    trip={"trip":{"summary":{"length":1.5,"time":90},"legs":[{"shape":"??AA","maneuvers":[]}]}}
    result=parse_routes({**trip,"alternates":[trip]})
    assert result["alternatives"][0]["distance_km"]==1.5
    assert parse_routes(trip)["alternatives"]==[]
    with pytest.raises(RouteError):parse_routes({**trip,"alternates":[trip]*3})
