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

def parse_import(fmt,raw):
    if len(raw.encode("utf-8"))>1_000_000 or "<!DOCTYPE" in raw.upper() or "<!ENTITY" in raw.upper():
        raise ValueError("Unsafe or oversized XML (1 MB maximum)")
    try:
        root=ET.fromstring(raw)
    except (ET.ParseError,UnicodeError):
        raise ValueError("Invalid XML") from None
    waypoints=[];routes=[]
    def name(node,fallback):
        return clean((node.findtext("name") or fallback).strip(),100)
    def coordinates(node):
        return point([float(node.attrib["lon"]),float(node.attrib["lat"])])
    def add_route(title,coords):
        if not 2<=len(coords)<=20000:raise ValueError("Route must contain 2–20,000 points")
        if len(routes)>=50:raise ValueError("Too many imported routes")
        routes.append((clean(title,100),coords))
    def add_waypoint(title,kind,coords):
        if len(waypoints)>=500:raise ValueError("Too many imported waypoints")
        waypoints.append((title,kind,coords))
    # Strip only the recognized format namespace. Never resolve external data.
    ns={"gpx":{"http://www.topografix.com/GPX/1/1","http://www.topografix.com/GPX/1/0"},
        "kml":{"http://www.opengis.net/kml/2.2","http://earth.google.com/kml/2.2"}}.get(fmt)
    if not ns:raise ValueError("Unsupported import format")
    for node in root.iter():
        if node.tag.startswith("{"):
            namespace,tag=node.tag[1:].split("}",1)
            if namespace in ns:node.tag=tag
    if root.tag!=fmt:raise ValueError("File does not match selected import format")
    try:
        if fmt=="gpx":
            for node in root.findall("wpt"):
                kind=node.findtext("type") or "other"
                add_waypoint(name(node,"Imported waypoint"),kind if kind in KINDS else "other",coordinates(node))
            for node in root.findall("rte"):
                add_route(name(node,"Imported route"),[coordinates(p) for p in node.findall("rtept")])
            for node in root.findall("trk"):
                title=name(node,"Imported track");segments=node.findall("trkseg")
                for i,seg in enumerate(segments,1):
                    add_route(title if len(segments)==1 else title[:85]+f" (segment {i})",[coordinates(p) for p in seg.findall("trkpt")])
        else:
            if any(n.tag.split("}")[-1] in ("NetworkLink","NetworkLinkControl","Link","Url") for n in root.iter()):
                raise ValueError("External KML links are not supported")
            def kcoords(node):
                coords=[]
                for token in (node.findtext("coordinates") or "").split():
                    parts=token.split(",")
                    if len(parts) not in (2,3):raise ValueError("Invalid KML coordinate")
                    coords.append(point([float(parts[0]),float(parts[1])]))
                return coords
            for placemark in root.iter("Placemark"):
                title=name(placemark,"Imported placemark")
                if any(n.tag.split("}")[-1] not in ("Placemark","name","description","Style","styleUrl","visibility","open","Point","LineString","MultiGeometry","coordinates","altitudeMode","extrude","tessellate","ExtendedData","Data","value","displayName") for n in placemark.iter()):
                    raise ValueError("Unsupported KML placemark geometry or extension")
                for node in placemark.iter("Point"):
                    coords=kcoords(node)
                    if len(coords)!=1:raise ValueError("Invalid KML point")
                    add_waypoint(title,"other",coords[0])
                for node in placemark.iter("LineString"):
                    add_route(title,kcoords(node))
        if not waypoints and not routes:raise ValueError("No supported points or tracks found")
    except (KeyError,TypeError,OverflowError):
        raise ValueError("Invalid geographic XML data") from None
    return waypoints,routes

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

    def import_file(self,fmt,raw):
        waypoints,routes=parse_import(fmt,raw)
        with self.db() as con:
            con.execute("BEGIN IMMEDIATE")
            if con.execute("SELECT count(*) FROM map_waypoints").fetchone()[0]+len(waypoints)>500:
                raise ValueError("Waypoint limit reached")
            if con.execute("SELECT count(*) FROM map_routes").fetchone()[0]+len(routes)>50:
                raise ValueError("Saved route limit reached")
            con.executemany("INSERT INTO map_waypoints(name,kind,lon,lat) VALUES (?,?,?,?)",
                [(n,k,p[0],p[1]) for n,k,p in waypoints])
            con.executemany("INSERT INTO map_routes(name,mode,geometry,created) VALUES (?,'imported',?,?)",
                [(n,json.dumps(p,separators=(",",":")),int(time.time())) for n,p in routes])
        return {"waypoints":len(waypoints),"routes":len(routes)}

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
