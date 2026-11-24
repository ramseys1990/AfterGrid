"""Shared LAN map annotations and saved route snapshots, not live navigation data."""
import json
import math
import sqlite3
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from contextlib import contextmanager

KINDS={"meeting","medical","water","shelter","household","other"}
MODES={"auto","pedestrian","bicycle","imported"}

def clean(value,limit):
    value=value.strip()
    if not value or len(value)>limit or any(ord(c)<32 for c in value):
        raise ValueError("Invalid name")
    return value

def point(p):
    if len(p)!=2 or not all(math.isfinite(v) for v in p) or not -180<=p[0]<=180 or not -90<=p[1]<=90:
        raise ValueError("Invalid geographic point")
    return p

class MapPlans:
    def __init__(self,data):self.path=Path(data)/"core.sqlite3"

    @contextmanager
    def db(self):
        con=sqlite3.connect(self.path,timeout=10)
        con.row_factory=sqlite3.Row
        try:
            with con:yield con
        finally:con.close()

    def init(self):
        with self.db() as con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS map_waypoints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,kind TEXT NOT NULL,
                    lon REAL NOT NULL,lat REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS map_routes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,mode TEXT NOT NULL,
                    geometry TEXT NOT NULL,created INTEGER NOT NULL);
            """)

    def directory(self):
        with self.db() as con:
            return {"waypoints":[dict(r) for r in con.execute("SELECT * FROM map_waypoints ORDER BY name,id")],
                    "routes":[dict(r) for r in con.execute("SELECT id,name,mode,created FROM map_routes ORDER BY name,id")]}

    def waypoint(self,name,kind,coords,ident=None):
        name=clean(name,100);lon,lat=point(coords)
        if kind not in KINDS:raise ValueError("Invalid waypoint category")
        with self.db() as con:
            con.execute("BEGIN IMMEDIATE")
            if ident is None:
                if con.execute("SELECT count(*) FROM map_waypoints").fetchone()[0]>=500:raise ValueError("Waypoint limit reached")
                return con.execute("INSERT INTO map_waypoints(name,kind,lon,lat) VALUES (?,?,?,?)",(name,kind,lon,lat)).lastrowid
            if not con.execute("UPDATE map_waypoints SET name=?,kind=?,lon=?,lat=? WHERE id=?",(name,kind,lon,lat,ident)).rowcount:raise ValueError("Waypoint not found")
            return ident

    def save_route(self,name,mode,coords):
        name=clean(name,100)
        if mode not in MODES or not 2<=len(coords)<=20000:raise ValueError("Invalid route snapshot")
        for p in coords:point(p)
        raw=json.dumps(coords,separators=(",",":"))
        with self.db() as con:
            con.execute("BEGIN IMMEDIATE")
            if con.execute("SELECT count(*) FROM map_routes").fetchone()[0]>=50:raise ValueError("Saved route limit reached")
            return con.execute("INSERT INTO map_routes(name,mode,geometry,created) VALUES (?,?,?,?)",(name,mode,raw,int(time.time()))).lastrowid

    def get_route(self,ident):
        with self.db() as con:
            r=con.execute("SELECT * FROM map_routes WHERE id=?",(ident,)).fetchone()
        if not r:raise ValueError("Saved route not found")
        return {"id":r["id"],"name":r["name"],"mode":r["mode"],"created":r["created"],"coordinates":json.loads(r["geometry"])}

    def delete(self,kind,ident):
        table={"waypoint":"map_waypoints","route":"map_routes"}.get(kind)
        if not table:raise ValueError("Invalid record type")
        with self.db() as con:
            if not con.execute("DELETE FROM "+table+" WHERE id=?",(ident,)).rowcount:raise ValueError("Record not found")

    def export(self,fmt,ident=None):
        directory=self.directory()
        routes=[self.get_route(ident)] if ident is not None else []
        waypoints=[] if ident is not None else directory["waypoints"]
        if fmt=="gpx":
            root=ET.Element("gpx",{"version":"1.1","creator":"AfterGrid","xmlns":"http://www.topografix.com/GPX/1/1"})
            for w in waypoints:
                node=ET.SubElement(root,"wpt",{"lat":str(w["lat"]),"lon":str(w["lon"])})
                ET.SubElement(node,"name").text=w["name"];ET.SubElement(node,"type").text=w["kind"]
            for r in routes:
                track=ET.SubElement(root,"trk");ET.SubElement(track,"name").text=r["name"]
                segment=ET.SubElement(track,"trkseg")
                for lon,lat in r["coordinates"]:ET.SubElement(segment,"trkpt",{"lat":str(lat),"lon":str(lon)})
        elif fmt=="kml":
            root=ET.Element("kml",{"xmlns":"http://www.opengis.net/kml/2.2"})
            doc=ET.SubElement(root,"Document")
            for w in waypoints:
                node=ET.SubElement(doc,"Placemark");ET.SubElement(node,"name").text=w["name"]
                ET.SubElement(ET.SubElement(node,"Point"),"coordinates").text=f'{w["lon"]},{w["lat"]}'
            for r in routes:
                node=ET.SubElement(doc,"Placemark");ET.SubElement(node,"name").text=r["name"]
                ET.SubElement(ET.SubElement(node,"LineString"),"coordinates").text=" ".join(f"{lon},{lat}" for lon,lat in r["coordinates"])
        else:raise ValueError("Unsupported export format")
        return ET.tostring(root,encoding="utf-8",xml_declaration=True)
