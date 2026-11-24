"""Fail-closed content admission during a managed snapshot. Linux only."""
import fcntl
import json
import os
import re
import sqlite3
import sys
from pathlib import Path
from contextlib import contextmanager

@contextmanager
def locked(data):
    data=Path(data)
    fd=os.open(data/"content-admission.lock",os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX)
        yield data/"content-backup-job"
    finally:os.close(fd)

@contextmanager
def content_admission(data):
    with locked(data) as marker:
        if marker.exists() or marker.is_symlink():
            raise ValueError("Content backup maintenance active; retry after it completes")
        yield

def guard(data,action,job):
    data=Path(data)
    if not re.fullmatch(r"[1-9][0-9]{0,18}",str(job)):raise ValueError("Invalid job")
    with locked(data) as marker:
        if action=="begin":
            if marker.exists() or marker.is_symlink():raise ValueError("Existing content maintenance")
            # Admission lock prevents a new request from queueing while checking.
            with sqlite3.connect((data/"downloads.sqlite3").absolute().as_uri()+"?mode=ro",uri=True,timeout=3) as con:
                if con.execute("SELECT 1 FROM downloads WHERE state IN ('queued','downloading','verifying','indexing') LIMIT 1").fetchone():
                    raise ValueError("Knowledge download active")
            for name in ("map-job.json","routing-download.json"):
                record=data/name
                if record.exists() and json.loads(record.read_text())["state"] in {"estimating","downloading","verifying"}:
                    raise ValueError("Regional content operation active")
            fd=os.open(marker,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,"w") as out:
                out.write(str(job))
                out.flush()
                os.fsync(out.fileno())
        elif action=="end":
            if marker.is_symlink() or marker.read_text()!=str(job):raise ValueError("Maintenance ownership mismatch")
            marker.unlink()
        else:raise ValueError("Invalid maintenance action")

if __name__=="__main__":
    try:
        if len(sys.argv)!=3:raise ValueError("Invalid arguments")
        guard("/data",sys.argv[1],sys.argv[2])
    except Exception:
        print("Content maintenance operation refused",file=sys.stderr)
        sys.exit(1)
