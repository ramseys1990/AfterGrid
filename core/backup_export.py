"""Private, bounded SQLite recovery export. Invoked only by the reviewed worker."""
import os
import re
import sqlite3
import stat
import sys
import time
from pathlib import Path

MAX_DB=64*1024*1024
REQUIRED={"admin","sessions","first_run","households","inventory_locations",
          "inventory_connections","map_waypoints","map_routes","comm_devices","comm_plans"}

def export_database(data,job):
    data=Path(data)
    if not re.fullmatch(r"[1-9][0-9]{0,18}",str(job)):
        raise ValueError("Invalid recovery job")
    source=data/"core.sqlite3"
    if not stat.S_ISREG(source.lstat().st_mode):
        raise RuntimeError("Core database unavailable")
    target=data/"recovery-export"
    # Never reuse an interrupted export or overwrite an unknown directory.
    target.mkdir(mode=0o700)
    dbpath=target/"core.sqlite3"
    marker=target/"job-id"
    try:
        marker.write_text(str(job),encoding="ascii")
        marker.chmod(0o600)
        fd=os.open(dbpath,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        os.close(fd)
        deadline=time.monotonic()+30
        src=sqlite3.connect(source.absolute().as_uri()+"?mode=ro",uri=True,timeout=2)
        try:
            if src.execute("PRAGMA page_count").fetchone()[0]*src.execute("PRAGMA page_size").fetchone()[0]>MAX_DB:
                raise RuntimeError("Core database exceeds export limit")
            dst=sqlite3.connect(dbpath,timeout=2)
            try:
                def progress(status,remaining,total):
                    if time.monotonic()>deadline or total*src_page_size>MAX_DB:
                        raise RuntimeError("Core database export limit exceeded")
                src_page_size=src.execute("PRAGMA page_size").fetchone()[0]
                src.backup(dst,pages=128,progress=progress,sleep=0.05)
                dst.execute("PRAGMA journal_mode=DELETE")
                dst.execute("PRAGMA secure_delete=ON")
                dst.execute("DELETE FROM sessions")
                dst.commit()
                dst.set_progress_handler(lambda: int(time.monotonic()>deadline),10000)
                if dst.execute("PRAGMA integrity_check").fetchmany(2)!=[("ok",)]:
                    raise RuntimeError("Core export integrity check failed")
                tables={r[0] for r in dst.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not REQUIRED<=tables or dst.execute("SELECT COUNT(*) FROM admin").fetchone()[0]!=1:
                    raise RuntimeError("Core export schema or administrator missing")
            finally:dst.close()
        finally:src.close()
        if dbpath.stat().st_size>MAX_DB:
            raise RuntimeError("Core database exceeds export limit")
        return target
    except Exception:
        # Remove only files belonging to this newly created directory.
        for name in ("core.sqlite3","core.sqlite3-journal","core.sqlite3-wal","core.sqlite3-shm","job-id"):
            (target/name).unlink(missing_ok=True)
        target.rmdir()
        raise

def clear_export(data,job):
    target=Path(data)/"recovery-export"
    if not stat.S_ISDIR(target.lstat().st_mode):
        raise RuntimeError("Unexpected export directory")
    marker=target/"job-id"
    if not stat.S_ISREG(marker.lstat().st_mode) or marker.read_text(encoding="ascii")!=str(job):
        raise RuntimeError("Export ownership not confirmed")
    if {p.name for p in target.iterdir()}!={"job-id","core.sqlite3"}:
        raise RuntimeError("Unexpected export contents; inspect manually")
    (target/"core.sqlite3").unlink()
    marker.unlink()
    target.rmdir()

if __name__=="__main__":
    try:
        if len(sys.argv)!=3 or not re.fullmatch(r"[1-9][0-9]{0,18}",sys.argv[2]):
            raise ValueError("Invalid action")
        if sys.argv[1]=="create":export_database("/data",sys.argv[2])
        elif sys.argv[1]=="clear":clear_export("/data",sys.argv[2])
        else:raise ValueError("Invalid action")
    except Exception:
        # Never emit paths, SQL data, credentials, or traceback.
        print("Private core recovery export operation failed",file=sys.stderr)
        sys.exit(1)
