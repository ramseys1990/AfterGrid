"""Small offline node/address index built with native Osmium and SQLite FTS5."""
import json
import math
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import time
from pathlib import Path

CAP=512*1024**2
MAX_ROWS=1_000_000

def feature_record(feature):
    geo=feature.get("geometry") or {}
    if geo.get("type")!="Point":return None
    p=geo.get("coordinates",[])
    if len(p)!=2 or not all(isinstance(x,(int,float)) and math.isfinite(x) for x in p) or abs(p[0])>180 or abs(p[1])>90:return None
    tags=feature.get("properties") or {}
    def tag(key):
        v=tags.get(key,"")
        return v.strip()[:180] if isinstance(v,str) else ""
    address=" ".join(x for x in (tag("addr:housenumber"),tag("addr:street")) if x)
    locality=", ".join(x for x in (tag("addr:city"),tag("addr:postcode")) if x)
    name=tag("name") or tag("name:en")
    if not name and not (tag("addr:housenumber") and tag("addr:street")):return None
    title=name or address
    detail=", ".join(x for x in (address if name else "",locality) if x)
    kind=next((tag(k) for k in ("place","amenity","shop","tourism","emergency","natural") if tag(k)), "address" if address else "named point")
    return title,detail,kind,float(p[0]),float(p[1])

def create_index(path,features,identity):
    con=sqlite3.connect(path)
    try:
        con.execute("PRAGMA journal_mode=DELETE")
        con.execute("PRAGMA max_page_count=131072")
        con.execute("CREATE VIRTUAL TABLE places USING fts5(title,detail,kind,lon UNINDEXED,lat UNINDEXED,tokenize='unicode61 remove_diacritics 2')")
        con.execute("CREATE TABLE metadata (identity TEXT NOT NULL, count INTEGER NOT NULL)")
        count=0
        for feature in features:
            record=feature_record(feature)
            if not record:continue
            count+=1
            if count>MAX_ROWS:raise ValueError("Index exceeds one million point records; select a smaller region")
            con.execute("INSERT INTO places VALUES (?,?,?,?,?)",record)
        if not count:raise ValueError("No supported named or address nodes found")
        con.execute("INSERT INTO metadata VALUES (?,?)",(json.dumps(identity,sort_keys=True),count))
        con.commit()
    finally:con.close()

def query_index(path,query):
    terms=re.findall(r"[^\W_]+",query,flags=re.UNICODE)
    if not terms or len(terms)>12:raise ValueError("Enter 1–12 search words")
    expression=" AND ".join('"'+t+'"*' for t in terms)
    with sqlite3.connect(path.as_uri()+"?mode=ro",uri=True) as con:
        con.row_factory=sqlite3.Row
        return [dict(r) for r in con.execute("SELECT title,detail,kind,lon,lat FROM places WHERE places MATCH ? ORDER BY bm25(places,5,2,1) LIMIT 30",(expression,))]

class PlaceSearch:
    def __init__(self,state,content):
        self.state=Path(state).absolute()
        self.content=Path(content)
        self.lock=threading.RLock()
        self.stop=threading.Event()
        self.thread=None
        self.job={"state":"idle","detail":""}

    def close(self):
        self.stop.set()
        if self.thread:self.thread.join(timeout=5)

    def source(self):
        selector=self.content/"active-slot"
        if selector.is_symlink():raise ValueError("Invalid routing selector")
        selected=selector.read_text().strip() if selector.is_file() else "tiles"
        if selected not in ("tiles","tiles-next"):raise ValueError("Invalid routing selector")
        source=self.content/("region.osm.pbf" if selected=="tiles" else "incoming.osm.pbf")
        if source.is_symlink() or not source.is_file():raise ValueError("Acquire a local routing PBF first")
        stat=source.stat()
        if not 0<stat.st_size<=2*1024**3:raise ValueError("Unsupported source size")
        identity={"slot":selected,"size":stat.st_size,"mtime_ns":stat.st_mtime_ns,"inode":stat.st_ino}
        return source,self.state/("places-"+selected+".sqlite3"),identity

    def metadata(self,path,identity):
        if not path.is_file() or path.is_symlink():return None
        try:
            with sqlite3.connect(path.as_uri()+"?mode=ro",uri=True) as con:
                row=con.execute("SELECT identity,count FROM metadata").fetchone()
                if row and json.loads(row[0])==identity:return row[1]
        except (sqlite3.Error,ValueError):pass
        return None

    def status(self):
        with self.lock:
            try:
                _,path,identity=self.source()
                count=self.metadata(path,identity)
                return {**self.job,"source_available":True,"slot":identity["slot"],"ready":count is not None,"count":count}
            except (OSError,ValueError):
                return {**self.job,"source_available":False,"ready":False,"count":None}

    def search(self,query):
        if len(query)>100:raise ValueError("Search too long")
        source,path,identity=self.source()
        if self.metadata(path,identity) is None:raise ValueError("Build the local place index for the selected source first")
        return query_index(path,query)

    def launch(self):
        with self.lock:
            if self.thread and self.thread.is_alive():raise ValueError("Place index build already running")
            source,path,identity=self.source()
            if shutil.disk_usage(self.state).free<2*1024**3:raise ValueError("Index build requires at least 2 GiB free space")
            self.stop.clear()
            self.job={"state":"building","detail":"Extracting named and address nodes"}
            self.thread=threading.Thread(target=self.build,args=(source,path,identity),daemon=True)
            self.thread.start()

    def run(self,args):
        proc=subprocess.Popen(["prlimit","--fsize="+str(CAP),"--as=1610612736","--",*args],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        deadline=time.monotonic()+600
        try:
            while proc.poll() is None:
                if self.stop.wait(.5) or time.monotonic()>deadline:raise ValueError("Index extraction interrupted or timed out")
                if shutil.disk_usage(self.state).free<512*1024**2:raise ValueError("Index storage reserve reached")
            if proc.returncode:raise ValueError("Native Osmium extraction failed; use a smaller source")
        finally:
            if proc.poll() is None:proc.kill();proc.wait()

    def build(self,source,path,identity):
        try:
            with tempfile.TemporaryDirectory(prefix=".places-",dir=self.state) as tmp:
                folder=Path(tmp);filtered=folder/"nodes.osm.pbf";geo=folder/"nodes.geojsonseq";index=folder/"index.sqlite3"
                self.run(["osmium","tags-filter","--omit-referenced",str(source),"n/name","n/name:en","n/addr:housenumber","-o",str(filtered)])
                self.run(["osmium","export","--geometry-types=point","-f","geojsonseq",str(filtered),"-o",str(geo)])
                with self.lock:self.job={"state":"building","detail":"Creating local full-text index"}
                def features():
                    with geo.open("r",encoding="utf-8") as stream:
                        for line in stream:
                            if self.stop.is_set():raise ValueError("Index build interrupted")
                            if len(line)>1_000_000:raise ValueError("Oversized native feature")
                            yield json.loads(line.lstrip("\x1e").strip())
                create_index(index,features(),identity)
                if self.source()[2]!=identity:raise ValueError("Selected source changed during indexing; rebuild")
                os.replace(index,path)
            with self.lock:self.job={"state":"complete","detail":"Local place index ready"}
        except Exception as exc:
            with self.lock:self.job={"state":"failed","detail":str(exc)[:200]}
