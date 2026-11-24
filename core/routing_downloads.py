"""Explicit Geofabrik PBF acquisition; never modify an existing graph."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

HOST="https://download.geofabrik.de"
REGIONS={
    "sc":("South Carolina","north-america/us/south-carolina"),
    "nc":("North Carolina","north-america/us/north-carolina"),
    "ga":("Georgia","north-america/us/georgia"),
    "tn":("Tennessee","north-america/us/tennessee"),
    "va":("Virginia","north-america/us/virginia"),
    "fl":("Florida","north-america/us/florida"),
    "liechtenstein":("Liechtenstein (small test region)","europe/liechtenstein"),
}
LIMIT=2*1024**3
RESERVE=512*1024**2
ACTIVE={"estimating","downloading","verifying"}

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def url_for(region):
    if region not in REGIONS:raise ValueError("Choose a supported routing region")
    return HOST+"/"+REGIONS[region][1]+"-latest.osm.pbf"

def parse_md5(raw,filename):
    match=re.fullmatch(r"([a-fA-F0-9]{32})[ \t]+\*?([^\r\n]+)\r?\n?",raw.decode("ascii"))
    if not match or match[2]!=filename:raise ValueError("Unexpected upstream checksum metadata")
    return match[1].lower()

def metadata(region):
    url=url_for(region)
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    with opener.open(urllib.request.Request(url,method="HEAD"),timeout=20) as r:
        size=int(r.headers.get("Content-Length","0"))
    with opener.open(url+".md5",timeout=20) as r:
        digest=parse_md5(r.read(1024),url.rsplit("/",1)[-1])
    if not 0<size<=LIMIT:raise ValueError("Unsupported dataset size (2 GiB development cap)")
    return size,digest

class RoutingDownloads:
    def __init__(self,state,content):
        self.record=Path(state)/"routing-download.json"
        self.content=Path(content)
        self.lock=threading.RLock()
        self.stop=threading.Event()
        self.thread=None

    def read(self):
        return json.loads(self.record.read_text()) if self.record.exists() else {"state":"idle"}

    def write(self,job):
        temp=self.record.with_suffix(".tmp")
        temp.write_text(json.dumps(job))
        os.replace(temp,self.record)

    def start(self):
        with self.lock:
            job=self.read()
            if job["state"] in ACTIVE:self.write({**job,"state":"failed","detail":"Interrupted; estimate again"})
        self.stop.clear()

    def close(self):
        self.stop.set()
        if self.thread:self.thread.join(timeout=5)

    def slot(self):
        if not self.content.is_dir() or not os.access(self.content,os.W_OK):raise ValueError("Routing data directory is not writable")
        selected=self.selected()
        if selected=="invalid":raise ValueError("Invalid routing selector")
        def occupied(name):
            p=self.content/name
            return p.exists() or p.is_symlink()
        if selected=="tiles-next":
            target,name="tiles","region.osm.pbf"
        elif occupied("region.osm.pbf") or occupied("tiles"):
            target,name="tiles-next","incoming.osm.pbf"
        else:
            target,name="tiles","region.osm.pbf"
        if occupied(name) or occupied(target):raise ValueError("Inactive graph or source slot occupied; archive it before downloading another")
        return name

    def selected(self):
        selector=self.content/"active-slot"
        try:
            value="invalid" if selector.is_symlink() else selector.read_text().strip() if selector.exists() else "tiles"
        except OSError:
            value="invalid"
        return value if value in ("tiles","tiles-next") else "invalid"

    def check_space(self,size):
        # This is only the PBF requirement. Native graph preparation has its own much larger needs.
        if not 0<size<=LIMIT or shutil.disk_usage(self.content).free<size+RESERVE:
            raise ValueError("Insufficient download space or dataset exceeds 2 GiB")

    def status(self):
        with self.lock:
            job=self.read()
            files=[]
            free=None
            if self.content.is_dir():
                free=shutil.disk_usage(self.content).free
                for name in ("region.osm.pbf","incoming.osm.pbf"):
                    p=self.content/name
                    if p.is_file() and not p.is_symlink():files.append({"name":name,"size_bytes":p.stat().st_size})
            def ready(name):
                path=self.content/name
                marker=path/".aftergrid-ready"
                return path.is_dir() and not path.is_symlink() and marker.is_file() and not marker.is_symlink()
            selected=self.selected()
            archive_dir=self.content/"archives"
            archives=[]
            if archive_dir.is_dir() and not archive_dir.is_symlink():
                for folder in sorted(archive_dir.iterdir(),reverse=True)[:100]:
                    if folder.is_dir() and not folder.is_symlink():
                        archives.append({"name":folder.name,"complete":any((folder/g/".aftergrid-ready").is_file() and (folder/p).is_file() for g,p in (("tiles","region.osm.pbf"),("tiles-next","incoming.osm.pbf")))})
            original=ready("tiles")
            candidate=ready("tiles-next")
            return {**job,"files":files,"free_bytes":free,"graph_ready":(original if selected=="tiles" else candidate if selected=="tiles-next" else False),
                    "selected_slot":selected,"original_ready":original,"candidate_ready":candidate,
                    "candidate_occupied":(self.content/"tiles-next").exists() or (self.content/"tiles-next").is_symlink(),
                    "original_occupied":(self.content/"tiles").exists() or (self.content/"tiles").is_symlink(),
                    "archives":archives,
                    "regions":[{"id":i,"name":v[0]} for i,v in REGIONS.items()]}

    def launch(self,job,phase):
        self.write({**job,"state":phase,"detail":phase.capitalize(),"bytes":0})
        self.thread=threading.Thread(target=self.execute,args=(job,phase),daemon=True)
        self.thread.start()

    def estimate(self,region):
        url_for(region)
        with self.lock:
            if self.read()["state"] in ACTIVE:raise ValueError("Routing download already active")
            self.slot()
            self.launch({"region":region},"estimating")

    def download(self):
        with self.lock:
            job=self.read()
            if job["state"]!="estimated":raise ValueError("Estimate the selected dataset first")
            if self.slot()!=job["slot"]:raise ValueError("Storage changed; estimate again")
            self.check_space(job["size_bytes"])
            self.launch(job,"downloading")

    def transfer(self,url,path,size,job):
        args=["curl","--disable","--fail","--silent","--show-error","--proto","=https","--noproxy","*",
              "--connect-timeout","20","--speed-time","60","--speed-limit","1024","--max-filesize",str(size),
              "--output",str(path),url]
        proc=subprocess.Popen(args,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        deadline=time.monotonic()+3600
        try:
            while proc.poll() is None:
                if self.stop.wait(1) or time.monotonic()>deadline:raise ValueError("Routing download interrupted or timed out")
                if shutil.disk_usage(self.content).free<RESERVE//2:raise ValueError("Storage reserve reached")
                with self.lock:self.write({**job,"state":"downloading","detail":"Downloading regional PBF","bytes":path.stat().st_size if path.exists() else 0})
            if proc.returncode:raise ValueError("Native download failed; estimate and retry")
        finally:
            if proc.poll() is None:proc.kill();proc.wait()

    def execute(self,job,phase):
        try:
            region=job["region"]
            size,digest=metadata(region)
            if phase=="estimating":
                with self.lock:self.write({**job,"state":"estimated","size_bytes":size,"digest":digest,"slot":self.slot(),"detail":"Confirm regional PBF download; graph construction needs additional space and RAM"})
                return
            if (size,digest)!=(job["size_bytes"],job["digest"]):raise ValueError("Upstream dataset changed; estimate again")
            self.check_space(size)
            with tempfile.TemporaryDirectory(prefix=".pbf-",dir=self.content) as tmp:
                path=Path(tmp)/"data.pbf"
                self.transfer(url_for(region),path,size,job)
                with self.lock:self.write({**job,"state":"verifying","bytes":size,"detail":"Checking publisher MD5"})
                if path.stat().st_size!=size:raise ValueError("Dataset size mismatch")
                with path.open("rb") as stream:
                    actual=hashlib.file_digest(stream,lambda:hashlib.md5(usedforsecurity=False)).hexdigest()
                if actual!=digest:raise ValueError("Publisher checksum mismatch; retry after estimating")
                if self.slot()!=job["slot"]:raise ValueError("Storage changed during transfer")
                os.chmod(path,0o644)
                os.link(path,self.content/job["slot"])
            with self.lock:self.write({**job,"state":"complete","bytes":size,"detail":"Verified PBF staged; install routing for a first graph, or prepare replacement separately"})
        except Exception as exc:
            with self.lock:self.write({**job,"state":"failed","detail":str(exc)[:240]})
