"""Unprivileged, persistent Kiwix download queue; curl and kiwix-manage do the work."""
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import threading
import uuid
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from pathlib import Path

HOST = "download.kiwix.org"
KEY = re.compile(r"/zim/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\.zim")
RESERVE = 512 * 1024**2
LIMIT = 512 * 1024**3
ACTIVE = ("queued","downloading","verifying","indexing")

def safe_name(name):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,239}\.zim", name):
        raise ValueError("Use a plain .zim filename (letters, digits, dots, underscores, hyphens)")
    return name

def key_for_url(value):
    u = urllib.parse.urlsplit(value)
    path = u.path.removesuffix(".meta4")
    if u.scheme == "https" and u.netloc in (HOST,"library.kiwix.org","lb.download.kiwix.org") and not u.query and not u.fragment and KEY.fullmatch(path) and "/../" not in path and "/./" not in path:
        return path
    return None

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        return None

def parse_metalink(raw, name):
    if len(raw)>2_000_000 or b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ValueError("Unsafe metadata")
    root=ET.fromstring(raw)
    ns={"m":"urn:ietf:params:xml:ns:metalink"}
    files=root.findall("m:file",ns)
    if len(files)!=1 or files[0].get("name")!=name:
        raise ValueError("Metadata filename mismatch")
    item=files[0]
    size=int(item.findtext("m:size",default="0",namespaces=ns))
    hashes={h.get("type","").lower(): (h.text or "").strip().lower() for h in item.findall("m:hash",ns)}
    digest=hashes.get("sha-256",hashes.get("sha256",""))
    if not 0<size<=LIMIT or not re.fullmatch(r"[a-f0-9]{64}",digest):
        raise ValueError("Official metadata must include a supported size and SHA-256")
    return size,digest

def metadata(key):
    if key_for_url("https://"+HOST+key)!=key:
        raise ValueError("Invalid official archive path")
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    with opener.open("https://"+HOST+key+".meta4",timeout=20) as response:
        return parse_metalink(response.read(2_000_001),Path(key).name)

def checksum(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream,"sha256").hexdigest()

def indexed_books(directory):
    library=directory/"library.xml"
    if library.is_symlink():
        raise ValueError("Unexpected library symlink")
    if not library.exists():
        return []
    return list(ET.parse(library).getroot().iter("book"))

def matching_books(directory,name):
    return [b for b in indexed_books(directory) if b.get("path") in (name,"./"+name)]

def index_archive(directory, name):
    safe_name(name)
    # Work in the same directory so the native tool produces portable relative paths.
    library=directory/"library.xml"
    temp=directory/".library.pending.xml"
    if library.is_symlink() or temp.is_symlink():
        raise ValueError("Unexpected library symlink")
    if matching_books(directory,name):
        return
    if library.exists():
        shutil.copyfile(library,temp)
    else:
        temp.write_text('<?xml version="1.0" encoding="UTF-8"?><library version="20110515"></library>')
    try:
        subprocess.run(["kiwix-manage",temp.name,"add",name],cwd=directory,check=True,timeout=120,capture_output=True)
        parsed=ET.parse(temp)
        previous={b.get("id") for b in indexed_books(directory)}
        current={b.get("id") for b in parsed.getroot().iter("book")}
        if not previous <= current:
            raise ValueError("Native index would replace another entry")
        # Check the native output contains the expected local archive. Relative paths
        # work both here and inside the reader container, which mounts this directory.
        if not any(book.get("path")==name or book.get("path")=="./"+name for book in parsed.getroot().iter("book")):
            raise ValueError("Native index did not produce a portable archive path")
        os.chmod(temp,0o644)
        os.replace(temp,library)
    finally:
        temp.unlink(missing_ok=True)

def unindex_archive(directory,name):
    safe_name(name)
    books=matching_books(directory,name)
    if not books:
        return
    ids=[b.get("id","") for b in books]
    if not all(re.fullmatch(r"[A-Za-z0-9-]{1,80}",i) for i in ids):
        raise ValueError("Invalid native library ID")
    library=directory/"library.xml"
    temp=directory/".library.pending.xml"
    if temp.is_symlink():
        raise ValueError("Unexpected library symlink")
    shutil.copyfile(library,temp)
    try:
        subprocess.run(["kiwix-manage",temp.name,"remove",*ids],cwd=directory,check=True,timeout=120,capture_output=True)
        remaining=list(ET.parse(temp).getroot().iter("book"))
        if any(b.get("id") in ids or b.get("path") in (name,"./"+name) for b in remaining):
            raise ValueError("Native library removal did not succeed")
        expected={b.get("id") for b in indexed_books(directory)}-set(ids)
        if {b.get("id") for b in remaining}!=expected:
            raise ValueError("Native library removal changed unrelated entries")
        os.chmod(temp,0o644)
        os.replace(temp,library)
    finally:
        temp.unlink(missing_ok=True)

class Downloads:
    def __init__(self,state,content):
        self.state=Path(state)
        self.content=Path(content)
        self.stop=threading.Event()
        self.thread=None
        self.operation=threading.Lock()
        self.admission=threading.Lock()

    @contextmanager
    def db(self):
        con=sqlite3.connect(self.state/"downloads.sqlite3",timeout=10)
        con.row_factory=sqlite3.Row
        try:
            with con: yield con
        finally: con.close()

    def start(self):
        with self.db() as con:
            con.executescript("""CREATE TABLE IF NOT EXISTS downloads (
                key TEXT PRIMARY KEY, name TEXT UNIQUE NOT NULL, state TEXT NOT NULL,
                size INTEGER, digest TEXT, detail TEXT NOT NULL DEFAULT '', updated INTEGER NOT NULL);
                UPDATE downloads SET state='queued',detail='Resuming after restart' WHERE state IN ('downloading','verifying','indexing');""")
        self.stop.clear()
        self.thread=threading.Thread(target=self.loop,daemon=True)
        self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread: self.thread.join(timeout=5)

    def enqueue(self,key):
        if not self.admission.acquire(blocking=False):
            raise ValueError("Local library maintenance in progress; retry shortly")
        try:
            return self._enqueue(key)
        finally:
            self.admission.release()

    def _enqueue(self,key):
        if key_for_url("https://"+HOST+key)!=key:
            raise ValueError("Choose an official Kiwix archive")
        name=safe_name(Path(key).name)
        if (self.content/".removed"/name).exists():
            raise ValueError("Restore or purge the removed archive before downloading again")
        if not self.content.is_dir() or not os.access(self.content,os.W_OK):
            raise ValueError("Content storage is not writable; see upgrade guide")
        with self.db() as con:
            con.execute("BEGIN IMMEDIATE")
            row=con.execute("SELECT * FROM downloads WHERE key=?",(key,)).fetchone()
            if row and row["state"] in ("queued","downloading","verifying","indexing","complete"):
                return
            if not row and (self.content/name).exists():
                raise ValueError("Archive already exists; refusing overwrite")
            if con.execute("SELECT COUNT(*) FROM downloads WHERE state IN ('queued','downloading','verifying','indexing')").fetchone()[0]>=12:
                raise ValueError("Download queue is full")
            con.execute("""INSERT INTO downloads(key,name,state,updated) VALUES (?,?,'queued',?)
                ON CONFLICT(key) DO UPDATE SET state='queued',detail='',updated=excluded.updated""",(key,name,int(time.time())))

    def local_action(self,name,action):
        safe_name(name)
        if action not in ("index","remove","restore","purge"):
            raise ValueError("Unsupported library action")
        if not self.admission.acquire(blocking=False):
            raise ValueError("Local library maintenance already in progress")
        try:
            if not self.operation.acquire(blocking=False):
                raise ValueError("A download is running; retry after it completes")
            try:
                with self.db() as con:
                    if con.execute("SELECT 1 FROM downloads WHERE name=? AND state IN ('queued','downloading','verifying','indexing')",(name,)).fetchone():
                        raise ValueError("Archive has an active download")
                source=self.content/name
                trash=self.content/".removed"
                removed=trash/name
                if trash.is_symlink() or source.is_symlink() or removed.is_symlink():
                    raise ValueError("Refusing symlink archive")
                if action in ("index","remove"):
                    if not source.is_file():
                        raise ValueError("Local archive not found")
                if action=="index":
                    index_archive(self.content,name)
                elif action=="remove":
                    trash.mkdir(mode=0o700,exist_ok=True)
                    if removed.exists():
                        raise ValueError("A removed copy already exists; restore or purge it first")
                    # Preserve a recoverable copy before changing the index.
                    os.link(source,removed)
                    try:
                        unindex_archive(self.content,name)
                    except Exception:
                        removed.unlink()
                        raise
                    source.unlink()
                    with self.db() as con:
                        con.execute("UPDATE downloads SET state='removed',detail='Moved to removed content',updated=? WHERE name=?",(int(time.time()),name))
                elif action=="restore":
                    if not removed.is_file() or source.exists():
                        raise ValueError("Removed file missing or destination already exists")
                    os.link(removed,source)
                    try:
                        index_archive(self.content,name)
                    except Exception:
                        source.unlink()
                        raise
                    removed.unlink()
                    with self.db() as con:
                        con.execute("UPDATE downloads SET state='complete',detail='Restored local archive',updated=? WHERE name=? AND state='removed'",(int(time.time()),name))
                else:
                    if not removed.is_file():
                        raise ValueError("Removed archive not found")
                    if source.exists():
                        raise ValueError("Active copy exists; inspect storage before purging")
                    removed.unlink()
                return {"ok":True}
            finally:
                self.operation.release()
        finally:
            self.admission.release()

    def list(self):
        with self.db() as con:
            rows=[dict(row) for row in con.execute("SELECT key,name,state,size,detail,updated FROM downloads ORDER BY updated DESC LIMIT 30")]
        for row in rows:
            part=self.content/(row["name"]+".part")
            final=self.content/row["name"]
            path=final if final.is_file() and not final.is_symlink() else part
            try:
                row["bytes"]=path.stat().st_size if path.is_file() and not path.is_symlink() else 0
            except FileNotFoundError:
                row["bytes"]=0
        return rows

    def update(self,key,state,detail="",size=None,digest=None):
        with self.db() as con:
            con.execute("UPDATE downloads SET state=?,detail=?,size=COALESCE(?,size),digest=COALESCE(?,digest),updated=? WHERE key=?",
                        (state,detail,size,digest,int(time.time()),key))

    def loop(self):
        while not self.stop.is_set():
            with self.operation:
                with self.db() as con:
                    row=con.execute("SELECT * FROM downloads WHERE state='queued' ORDER BY updated LIMIT 1").fetchone()
                if row:
                    try: self.execute(row)
                    except Exception as exc:
                        self.update(row["key"],"failed",str(exc)[:240])
            if not row: self.stop.wait(1)

    def execute(self,row):
        key,name=row["key"],row["name"]
        if key_for_url("https://"+HOST+key)!=key or Path(key).name!=name:
            raise ValueError("Invalid saved archive")
        part=self.content/(name+".part")
        final=self.content/name
        if part.is_symlink() or final.is_symlink():
            raise ValueError("Refusing symlink destination")
        self.update(key,"downloading","Checking official metadata")
        size,digest=metadata(key)
        if row["digest"] and row["digest"]!=digest:
            raise ValueError("Official checksum changed; remove stale partial manually")
        self.update(key,"downloading","Downloading; progress measured from partial file",size,digest)
        if not final.exists():
            already=part.stat().st_size if part.exists() else 0
            if already>size: raise ValueError("Partial exceeds expected size")
            if shutil.disk_usage(self.content).free < size-already+RESERVE:
                raise ValueError("Insufficient free space (512 MiB reserve)")
            if already<size:
                # Only the official origin is accepted from the browser. Mirrors are
                # selected by that upstream HTTPS service, never by browser input.
                args=["curl","--disable","--fail","--silent","--show-error","--location","--max-redirs","5",
                      "--proto","=https","--proto-redir","=https","--noproxy","*","--connect-timeout","20",
                      "--speed-time","60","--speed-limit","1024","--max-filesize",str(size),
                      "--continue-at","-","--output",str(part),"https://"+HOST+key]
                proc=subprocess.Popen(args,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                try:
                    while proc.poll() is None:
                        if self.stop.wait(1):
                            proc.terminate();proc.wait(timeout=5)
                            self.update(key,"queued","Paused on shutdown");return
                        if shutil.disk_usage(self.content).free < RESERVE//2:
                            raise ValueError("Storage reserve reached")
                    if proc.returncode: raise ValueError("Transfer interrupted; retry to resume")
                finally:
                    if proc.poll() is None: proc.kill();proc.wait()
            self.update(key,"verifying","Checking SHA-256")
            if part.stat().st_size!=size or checksum(part)!=digest:
                raise ValueError("Size or SHA-256 mismatch; remove bad partial manually")
            # Link rather than replace: never overwrite an archive supplied by the operator.
            os.link(part,final)
            part.unlink()
        else:
            self.update(key,"verifying","Checking previously downloaded archive")
            if final.stat().st_size!=size or checksum(final)!=digest:
                raise ValueError("Existing archive does not match official checksum")
        self.update(key,"indexing","Updating native Kiwix library")
        index_archive(self.content,name)
        self.update(key,"complete","Verified and indexed")
