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


def test_consolidated_inventory_filters_partial_failure_and_permissions(tmp_path,monkeypatch):
    calls=[]
    def native(m,p,k):
        calls.append((m,p))
        if m=="homebox": return TREE
        if p.startswith("/objects/locations"): return [{"id":2,"name":"Pantry"},{"id":3,"name":"Garage"}]
        if p.startswith("/objects/products"): return [{"id":1,"name":"Water","qu_id_stock":3}]
        if p.startswith("/objects/quantity_units"): return [{"id":3,"name":"Liter","name_plural":"Liters"}]
        if p.startswith("/stock/locations/2/"): return [{"location_id":2,"product_id":1,"amount":"1.25"}]
        raise InventoryError("Native inventory unavailable")
    monkeypatch.setattr(inventory,"get",native)
    (tmp_path/"setup-token").write_text("token")
    origin={"Origin":"http://testserver"}
    path="/api/admin/inventory/overview"
    with TestClient(create_app(tmp_path)) as c:
        assert c.get(path).status_code==401
        assert c.post("/api/setup",json={"token":"token","username":"admin","password":"long test password"},headers=origin).status_code==201
        for module in ("homebox","grocy"):
            assert c.post("/api/admin/inventory/connect",json={"module":module,"key":"test-native-secret"},headers=origin).status_code==200
        owner=c.post("/api/admin/households",json={"name":"Owner"},headers=origin).json()["id"]
        storage=c.post("/api/admin/households",json={"name":"Storage"},headers=origin).json()["id"]
        for m,n,label,own,stored in [("homebox",A,"Shed",owner,storage),("homebox",C,"Cabinet",None,None),("grocy","2","Pantry",owner,storage),("grocy","3","Garage",owner,None)]:
            assert c.post("/api/admin/households/locations",json={"module":m,"native_id":n,"label":label,"owner_id":own,"storage_id":stored},headers=origin).status_code==200
        calls.clear()
        response=c.get(path)
        r=response.json()
        assert response.status_code==200 and "test-native-secret" not in response.text
        assert r["total_locations"]==4 and r["available_locations"]==3 and r["unavailable_locations"]==1
        assert r["homebox_item_records"]==2 and r["next_offset"] is None
        assert calls.count(("homebox","/entities/tree?withItems=true"))==1
        assert calls.count(("grocy","/objects/products?limit=10001"))==1
        pantry=next(l for l in r["locations"] if l["label"]=="Pantry")
        assert pantry["products"]==[{"product":"Water","amount":"1.25","unit":"Liters"}]
        failed=next(l for l in r["locations"] if l["label"]=="Garage")
        assert failed["state"]=="unavailable" and "products" not in failed
        assert c.get(path,params={"household":owner,"basis":"owner"}).json()["total_locations"]==3
        assert c.get(path,params={"household":storage,"basis":"storage"}).json()["total_locations"]==2
        assert c.get(path,params={"household":0,"basis":"owner"}).json()["total_locations"]==1
        assert c.get(path,params={"basis":"invalid"}).status_code==400
        assert c.get(path,params={"household":999}).status_code==404
        c.cookies.clear()
        assert c.get(path).status_code==401

def test_inventory_overview_is_bounded_and_missing_connection_is_not_zero(tmp_path):
    inv=Inventory(tmp_path)
    inv.init()
    locations=[{"id":i,"module":"homebox","native_id":A} for i in range(1,11)]
    first=inv.overview(locations)
    assert len(first["locations"])==8 and first["next_offset"]==8
    assert first["unavailable_locations"]==8 and first["homebox_item_records"] is None
    last=inv.overview(locations,8)
    assert len(last["locations"])==2 and last["next_offset"] is None
