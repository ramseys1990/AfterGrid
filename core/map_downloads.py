"""One regional extract at a time, using the upstream pmtiles CLI."""
import datetime
import json
import math
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

RESERVE=512*1024**2
LIMIT=4*1024**3
ACTIVE={"estimating","downloading","verifying"}

def validate(build,bbox,zoom):
    if not re.fullmatch(r"[0-9]{8}",build):
        raise ValueError("Enter a build date as YYYYMMDD")
    try:
        date=datetime.datetime.strptime(build,"%Y%m%d").date()
    except ValueError:
        raise ValueError("Invalid build date") from None
    if date>datetime.date.today() or date.year<2024:
        raise ValueError("Invalid build date")
    if len(bbox)!=4 or not all(math.isfinite(v) for v in bbox):
        raise ValueError("Enter four finite coordinates")
    west,south,east,north=bbox
    if not -180<=west<east<=180 or not -85<=south<north<=85:
        raise ValueError("Bounds must be west, south, east, north; no antimeridian crossing")
    if east-west>25 or north-south>25 or (east-west)*(north-south)>200:
        raise ValueError("Select a smaller region (maximum 25 degrees per side and 200 square degrees)")
    if not 0<=zoom<=15:
        raise ValueError("Zoom must be 0–15")

def estimate_bytes(log):
    # Upstream humanize.Bytes uses decimal SI units; estimate is rounded and
    # excludes archive metadata. Storage checks include conservative headroom.
    m=re.search(r"for an archive size of ([0-9]+(?:\.[0-9]+)?) (B|kB|MB|GB|TB)\b",log)
    if not m: raise ValueError("Could not read upstream size estimate")
    return math.ceil(float(m[1])*{"B":1,"kB":1000,"MB":10**6,"GB":10**9,"TB":10**12}[m[2]])

def command(job,path,dry=False):
    validate(job["build"],job["bbox"],job["zoom"])
    args=["pmtiles","extract","https://build.protomaps.com/"+job["build"]+".pmtiles",
          str(path),"--bbox="+",".join(str(x) for x in job["bbox"]),
          "--maxzoom="+str(job["zoom"]),"--download-threads=2"]
    if dry: args.append("--dry-run")
    return args

class MapDownloads:
    def __init__(self,state,content):
        self.state=Path(state)
        self.content=Path(content)
        self.record=self.state/"map-job.json"
        self.log=self.state/"map-job.log"
        self.lock=threading.RLock()
        self.stop=threading.Event()
        self.thread=None

    def read(self):
        return json.loads(self.record.read_text()) if self.record.exists() else {"state":"idle"}

    def write(self,job):
        tmp=self.record.with_suffix(".tmp")
        tmp.write_text(json.dumps(job))
        os.replace(tmp,self.record)

    def start(self):
        with self.lock:
            job=self.read()
            if job["state"] in ACTIVE:
                self.write({**job,"state":"failed","detail":"Interrupted by restart; estimate again"})
        self.stop.clear()

    def close(self):
        self.stop.set()
        if self.thread: self.thread.join(timeout=5)

    def status(self):
        with self.lock:
            job=self.read()
            output=""
            if self.log.exists():
                with self.log.open("rb") as stream:
                    stream.seek(max(0,self.log.stat().st_size-6000))
                    output=stream.read(6000).decode(errors="replace")
            files=[]
            free=None
            if self.content.is_dir():
                free=shutil.disk_usage(self.content).free
                for name in ("region.pmtiles","region.mbtiles"):
                    p=self.content/name
                    if p.is_file() and not p.is_symlink():
                        files.append({"name":name,"size_bytes":p.stat().st_size})
            return {**job,"output":output,"files":files,"free_bytes":free}

    def storage(self):
        if not self.content.is_dir() or not os.access(self.content,os.W_OK):
            raise ValueError("Map storage is not writable; see upgrade guide")
        dest=self.content/"region.pmtiles"
        if dest.exists() or dest.is_symlink():
            raise ValueError("PMTiles slot already occupied; archive it manually before replacing")

    def launch(self,job,phase):
        self.log.write_text("")
        self.write({**job,"state":phase,"detail":phase.capitalize()})
        self.thread=threading.Thread(target=self.execute,args=(job,phase),daemon=True)
        self.thread.start()

    def estimate(self,build,bbox,zoom):
        validate(build,bbox,zoom)
        with self.lock:
            if self.read()["state"] in ACTIVE:
                raise ValueError("A map operation is running")
            self.storage()
            self.launch({"build":build,"bbox":bbox,"zoom":zoom},"estimating")

    def download(self):
        with self.lock:
            job=self.read()
            if job["state"]!="estimated":
                raise ValueError("Complete a size estimate first")
            self.storage()
            self.check_space(job["estimate_bytes"])
            self.launch(job,"downloading")

    def check_space(self,size):
        required=math.ceil(size*1.2)+64*1024**2
        if required>LIMIT:
            raise ValueError("Extract exceeds the development 4 GiB limit; reduce region or zoom")
        if shutil.disk_usage(self.content).free < required+RESERVE:
            raise ValueError("Insufficient map storage including 512 MiB reserve")

    def run(self,args,seconds):
        # Limit file size even when the CLI preallocates the archive.
        with self.log.open("ab") as output:
            proc=subprocess.Popen(["prlimit","--fsize="+str(LIMIT),"--",*args],
                                  stdout=output,stderr=subprocess.STDOUT,
                                  env={**os.environ,"HTTP_PROXY":"","HTTPS_PROXY":"","ALL_PROXY":"","http_proxy":"","https_proxy":"","all_proxy":""})
            deadline=time.monotonic()+seconds
            try:
                while proc.poll() is None:
                    if self.stop.wait(.5) or time.monotonic()>deadline:
                        raise ValueError("Map operation interrupted or timed out")
                    if self.log.stat().st_size>4*1024**2:
                        raise ValueError("Map operation output exceeded limit")
                    if shutil.disk_usage(self.content).free<RESERVE//2:
                        raise ValueError("Map storage reserve reached")
                if proc.returncode:
                    raise ValueError("PMTiles command failed; inspect output")
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait()

    def execute(self,job,phase):
        import tempfile
        try:
            with tempfile.TemporaryDirectory(prefix=".extract-",dir=self.content) as tmp:
                path=Path(tmp)/"archive.pmtiles"
                if phase=="estimating":
                    self.run(command(job,path,True),300)
                    size=estimate_bytes(self.log.read_text(errors="replace"))
                    with self.lock:
                        self.write({**job,"state":"estimated","estimate_bytes":size,"detail":"Approximate archive size; confirm to download"})
                    return
                self.check_space(job["estimate_bytes"])
                self.run(command(job,path),3600)
                with self.lock:
                    self.write({**job,"state":"verifying","detail":"Checking native PMTiles structure"})
                if not path.is_file() or path.is_symlink() or not 0<path.stat().st_size<=LIMIT:
                    raise ValueError("Invalid archive output")
                self.run(["pmtiles","verify",str(path)],300)
                os.chmod(path,0o644)
                os.link(path,self.content/"region.pmtiles")
                with self.lock:
                    self.write({**job,"state":"complete","detail":"Verified archive published; restart Maps to load it"})
        except Exception as exc:
            with self.lock:
                self.write({**job,"state":"failed","detail":str(exc)[:240]})
