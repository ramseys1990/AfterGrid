"""Bounded read-only requests to the bundled inventory services."""
import json
import re
import sqlite3
import urllib.request
import urllib.error
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import UUID

BASE={"homebox":"http://aftergrid-homebox:7745/api/v1","grocy":"http://aftergrid-grocy/api"}
MAX_BYTES=4*1024*1024
class InventoryError(Exception):
    pass

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        return None

def get(module,path,key):
    headers={"Accept":"application/json"}
    headers.update({"Authorization":"Bearer "+key} if module=="homebox" else {"GROCY-API-KEY":key})
    request=urllib.request.Request(BASE[module]+path,headers=headers,method="GET")
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    try:
        with opener.open(request,timeout=8) as response:
            data=response.read(MAX_BYTES+1)
            if len(data)>MAX_BYTES:
                raise InventoryError("Native response exceeds report limit")
            return json.loads(data)
    except urllib.error.HTTPError as exc:
        raise InventoryError("Native service returned HTTP "+str(exc.code)) from None
    except (OSError,ValueError):
        raise InventoryError("Native inventory unavailable or returned invalid JSON") from None

def rows(data):
    if not isinstance(data,list) or len(data)>10000 or any(not isinstance(r,dict) for r in data):
        raise InventoryError("Unexpected or oversized native inventory response")
    return data

def label(value):
    if not isinstance(value,str) or not value.strip():
        raise InventoryError("Native record has no name")
    return value[:160]

def numeric(value):
    s=str(value)
    if not re.fullmatch(r"[1-9][0-9]{0,18}",s):
        raise InventoryError("Invalid native numeric ID")
    return s

def homebox_tree(data):
    result={}
    seen=set()
    def walk(nodes,current=None,depth=0):
        if depth>30: raise InventoryError("Native tree depth exceeds limit")
        for node in rows(nodes):
            try:
                ident=str(UUID(node["id"]))
            except (KeyError,TypeError,ValueError,AttributeError):
                raise InventoryError("Invalid Homebox entity ID") from None
            if ident in seen or len(seen)>=10000:
                raise InventoryError("Duplicate or oversized native tree")
            seen.add(ident)
            kind=node.get("type")
            if kind=="location":
                here=ident
                result[ident]={"native_id":ident,"label":label(node.get("name")),"item_records":0}
            elif kind=="item":
                here=current
                if here is not None:
                    result[here]["item_records"]+=1
            else:
                raise InventoryError("Unrecognized Homebox tree node")
            walk(node.get("children") or [],here,depth+1)
    walk(data)
    return list(result.values())

def grocy_locations(data):
    return [{"native_id":numeric(r.get("id")),"label":label(r.get("name"))} for r in rows(data)]

def grocy_stock(data,products,units,location):
    products={numeric(r.get("id")):r for r in rows(products)}
    units={numeric(r.get("id")):r for r in rows(units)}
    entries=rows(data)
    if len(entries)>=1001:
        raise InventoryError("Location exceeds 1000 stock entries; use native Grocy")
    amounts={}
    for r in entries:
        if numeric(r.get("location_id"))!=location:
            raise InventoryError("Unexpected stock location")
        product=numeric(r.get("product_id"))
        if product not in products: raise InventoryError("Missing native product metadata")
        try:
            amount=Decimal(str(r.get("amount")))
            if not amount.is_finite() or abs(amount)>Decimal("1e15"):
                raise ValueError()
        except (InvalidOperation,ValueError):
            raise InventoryError("Invalid native stock amount") from None
        amounts[product]=amounts.get(product,Decimal(0))+amount
    result=[]
    for ident,amount in amounts.items():
        p=products[ident]
        unit=units.get(numeric(p.get("qu_id_stock")))
        if not unit: raise InventoryError("Missing native stock unit")
        result.append({"product":label(p.get("name")),"amount":format(amount,"f"),"unit":label(unit.get("name_plural") or unit.get("name"))})
    return sorted(result,key=lambda r:r["product"].casefold())

class Inventory:
    def __init__(self,data):
        self.path=Path(data)/"core.sqlite3"

    @contextmanager
    def db(self):
        con=sqlite3.connect(self.path,timeout=10)
        try:
            with con: yield con
        finally: con.close()

    def init(self):
        with self.db() as con:
            con.execute("CREATE TABLE IF NOT EXISTS inventory_connections (module TEXT PRIMARY KEY, token TEXT NOT NULL)")

    def status(self):
        with self.db() as con:
            return {m:bool(con.execute("SELECT 1 FROM inventory_connections WHERE module=?",(m,)).fetchone()) for m in BASE}

    def token(self,module):
        if module not in BASE: raise ValueError("Unsupported inventory")
        with self.db() as con:
            row=con.execute("SELECT token FROM inventory_connections WHERE module=?",(module,)).fetchone()
        if not row: raise InventoryError("Connect the native inventory first")
        return row[0]

    def discover(self,module,key=None):
        if module not in BASE: raise ValueError("Unsupported inventory")
        key=self.token(module) if key is None else key
        if module=="homebox":
            return homebox_tree(get(module,"/entities/tree?withItems=true",key))
        return grocy_locations(get(module,"/objects/locations?limit=10001",key))

    def save(self,module,key):
        if module not in BASE: raise ValueError("Unsupported inventory")
        if not key or len(key)>1024 or not re.fullmatch(r"[!-~]+",key):
            raise ValueError("Enter a native API key without spaces")
        found=self.discover(module,key)
        with self.db() as con:
            con.execute("INSERT INTO inventory_connections VALUES (?,?) ON CONFLICT(module) DO UPDATE SET token=excluded.token",(module,key))
        return found

    def disconnect(self,module):
        if module not in BASE: raise ValueError("Unsupported inventory")
        with self.db() as con: con.execute("DELETE FROM inventory_connections WHERE module=?",(module,))

    def report(self,location):
        module=location["module"]
        key=self.token(module)
        native=location["native_id"]
        if module=="homebox":
            match=next((r for r in self.discover(module,key) if r["native_id"]==native),None)
            if match is None: raise InventoryError("Mapped native location not found")
            return {"module":module,"location":match["label"],"item_records":match["item_records"]}
        native=numeric(native)
        found=next((r for r in self.discover(module,key) if r["native_id"]==native),None)
        if found is None: raise InventoryError("Mapped native location not found")
        stock=get(module,"/stock/locations/"+native+"/entries?limit=1001",key)
        products=get(module,"/objects/products?limit=10001",key)
        units=get(module,"/objects/quantity_units?limit=10001",key)
        return {"module":module,"location":found["label"],"products":grocy_stock(stock,products,units,native)}
