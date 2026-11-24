import pytest
from core import inventory
from core.inventory import Inventory, InventoryError, homebox_tree, grocy_stock
from core.app import create_app
from fastapi.testclient import TestClient

A="11111111-2222-3333-4444-555555555555"
B="22222222-2222-3333-4444-555555555555"
C="33333333-2222-3333-4444-555555555555"
D="44444444-2222-3333-4444-555555555555"
TREE=[{"id":A,"name":"Shed","type":"location","children":[{"id":B,"name":"Tool","type":"item","children":[]},{"id":C,"name":"Cabinet","type":"location","children":[{"id":D,"name":"Radio","type":"item","children":[]}]}]}]

def test_homebox_counts_are_not_recursive_location_totals():
    found=homebox_tree(TREE)
    assert [r["item_records"] for r in found]==[1,1]
    assert found[1]["native_id"]==C
    with pytest.raises(InventoryError):homebox_tree(TREE+TREE)

def test_grocy_preserves_product_units():
    stock=[{"location_id":2,"product_id":1,"amount":"1.25"},{"location_id":2,"product_id":1,"amount":"2.5"}]
    products=[{"id":1,"name":"Water","qu_id_stock":3}]
    units=[{"id":3,"name":"Liter","name_plural":"Liters"}]
    assert grocy_stock(stock,products,units,"2")==[{"product":"Water","amount":"3.75","unit":"Liters"}]
    with pytest.raises(InventoryError):grocy_stock(stock,products,units,"9")

def test_connection_access_and_no_key_disclosure(tmp_path,monkeypatch):
    monkeypatch.setattr(inventory,"get",lambda m,p,k:TREE)
    (tmp_path/"setup-token").write_text("token")
    origin={"Origin":"http://testserver"}
    with TestClient(create_app(tmp_path)) as c:
        assert c.get("/api/admin/inventory/connections").status_code==401
        assert c.post("/api/setup",json={"token":"token","username":"admin","password":"long test password"},headers=origin).status_code==201
        body={"module":"homebox","key":"test-native-secret"}
        assert c.post("/api/admin/inventory/connect",json=body).status_code==403
        r=c.post("/api/admin/inventory/connect",json=body,headers=origin)
        assert r.status_code==200 and "test-native-secret" not in r.text
        assert c.get("/api/admin/inventory/connections").json()=={"homebox":True,"grocy":False}
        loc=c.post("/api/admin/households/locations",json={"module":"homebox","native_id":A,"label":"Shed"},headers=origin).json()["id"]
        assert c.get("/api/admin/inventory/report/"+str(loc)).json()["item_records"]==1
        c.cookies.clear()
        assert c.get("/api/admin/inventory/report/"+str(loc)).status_code==401
        assert "test-native-secret" not in c.get("/api/households").text
