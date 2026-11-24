#!/usr/bin/env python3
"""Prepare a NEW private recovery staging tree from already-restored Kopia exports.
No Docker, network, running AfterGrid service, or live-volume writes.
"""
import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import stat
from pathlib import Path

from worker import worker

def read_private(path,limit):
    path=Path(path)
    # Inputs must be regular files below a real directory; no symlink traversal.
    absolute=path.absolute()
    for parent in absolute.parents:
        if not stat.S_ISDIR(parent.lstat().st_mode):
            raise ValueError("Recovery input parent is not a regular directory")
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,"rb") as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0<info.st_size<=limit:
            raise ValueError("Recovery input is invalid or oversized")
        value=stream.read(limit+1)
        if len(value)!=info.st_size or len(value)>limit:
            raise ValueError("Recovery input changed while reading")
    return value

def private_write(path,data):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,"wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())

def prepare(core_dir,worker_dir,destination,core_job,worker_job,worker_sha256):
    if not all(type(j) is int and 0<j<10**19 for j in (core_job,worker_job)):
        raise ValueError("Invalid original job ID")
    if not re.fullmatch(r"[a-f0-9]{64}",worker_sha256):
        raise ValueError("Expected worker envelope digest required")
    core_dir,worker_dir,destination=map(Path,(core_dir,worker_dir,destination))
    if read_private(core_dir/"job-id",19)!=str(core_job).encode("ascii"):
        raise ValueError("Core export marker mismatch")
    if read_private(worker_dir/"job-id",19)!=str(worker_job).encode("ascii"):
        raise ValueError("Worker export marker mismatch")
    core=read_private(core_dir/"core.sqlite3",64*1024*1024)
    payload=read_private(worker_dir/"worker-recovery.json",worker.WORKER_EXPORT_LIMIT)
    worker.check_restored_core(core)
    count=worker.check_restored_worker(payload,worker_job,worker_sha256)
    envelope=json.loads(payload)
    worker_db=base64.b64decode(envelope["jobs_sqlite3"],validate=True)
    # No recursive creation and no reuse of existing destinations.
    # The caller must choose a trusted, private parent on the replacement host.
    for parent in destination.absolute().parents:
        if not stat.S_ISDIR(parent.lstat().st_mode):
            raise ValueError("Recovery destination parent is not a real directory")
    destination.mkdir(mode=0o700)
    try:
        core_out=destination/"core"
        worker_out=destination/"worker-state"
        secret_out=worker_out/"secrets"
        for d in (core_out,worker_out,secret_out):d.mkdir(mode=0o700)
        private_write(core_out/"core.sqlite3",core)
        private_write(worker_out/"jobs.sqlite3",worker_db)
        for ident,fields in envelope["secrets"].items():
            private_write(secret_out/(ident+".json"),json.dumps(fields,separators=(",",":")).encode("utf-8"))
        metadata={"format":1,"core_source_job":core_job,"worker_source_job":worker_job,
                  "core_sha256":hashlib.sha256(core).hexdigest(),"worker_envelope_sha256":worker_sha256,
                  "secret_set_count":count,"scope":"private staging only; not a complete system restore"}
        private_write(destination/"recovery-metadata.json",json.dumps(metadata,indent=2).encode("utf-8"))
    except Exception:
        # This directory was created exclusively above. Never remove an existing tree.
        shutil.rmtree(destination)
        raise
    return metadata

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core-dir",required=True,type=Path,help="Restored core export directory containing job-id and core.sqlite3")
    parser.add_argument("--worker-dir",required=True,type=Path,help="Restored worker export directory containing job-id and worker-recovery.json")
    parser.add_argument("--destination",required=True,type=Path,help="New private staging directory, must not exist")
    parser.add_argument("--core-job",required=True,type=int)
    parser.add_argument("--worker-job",required=True,type=int)
    parser.add_argument("--worker-sha256",required=True,help="Recorded full worker recovery envelope digest")
    args=parser.parse_args()
    # Use the reviewed manifests from this exact release, not from restored data.
    worker.MODULES=Path(__file__).resolve().parent/"modules"
    try:
        result=prepare(args.core_dir,args.worker_dir,args.destination,args.core_job,args.worker_job,args.worker_sha256)
    except Exception:
        parser.exit(1,"Recovery preparation refused or failed. Check inputs, digest, permissions, release and destination; no live service was changed.\n")
    print("Private recovery staging prepared ("+str(result["secret_set_count"])+" reviewed secret sets). No live service was changed.")

if __name__=="__main__":
    main()
