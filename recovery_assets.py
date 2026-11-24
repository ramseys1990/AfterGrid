#!/usr/bin/env python3
"""Capture private offline installation assets from an existing AfterGrid host.

No pulls, builds, tag changes, service restarts, or live data backup.
Run in an exclusive administration window on the local Linux Docker host.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import time
from pathlib import Path

IMAGE_ID=re.compile(r"sha256:[a-f0-9]{64}")
MODULES={"grocy","homebox","kiwix","kolibri","kopia","maps","media","meshmonitor","notes","routing","tak"}
TOP_FILES={"compose.yaml","install.sh","README.md","CHANGELOG.md","LICENSE","AGENTS.md","recovery_prepare.py","recovery_assets.py"}
SOURCE_DIRS={"core","worker","modules","docs"}
SOURCE_SUFFIXES={".py",".js",".css",".html",".txt",".md",".yaml",".json",".sh",".xml"}
FILE_LIMIT=16*1024*1024
SOURCE_LIMIT=128*1024*1024

def docker(*args,timeout=15):
    return subprocess.run(["docker",*args],check=True,capture_output=True,text=True,timeout=timeout).stdout.strip()

def local_docker():
    if os.environ.get("DOCKER_HOST") or os.environ.get("DOCKER_CONTEXT") or docker("context","show")!="default":
        raise ValueError("Local default Docker context required")
    endpoint=json.loads(docker("context","inspect","default","--format","{{json .Endpoints.docker.Host}}"))
    if endpoint!="unix:///var/run/docker.sock":
        raise ValueError("Local Docker socket required")
    platform=docker("version","--format","{{.Server.Os}}/{{.Server.Arch}}")
    if platform not in {"linux/amd64","linux/arm64"}:
        raise ValueError("Unsupported recovery platform")
    return platform

def image_inventory():
    """Only exact Compose project/service labels; never include unrelated images."""
    projects={"aftergrid-core":{"core","worker"},**{"aftergrid-"+m:{m} for m in MODULES}}
    result=[]
    for project,services in sorted(projects.items()):
        rows=docker("ps","--all","--no-trunc","--filter","label=com.docker.compose.project="+project,
                    "--format",'{{json .ID}}').splitlines()
        seen=set()
        for row in rows:
            cid=json.loads(row)
            if not re.fullmatch(r"[a-f0-9]{64}",cid):raise ValueError("Invalid container identifier")
            raw=docker("container","inspect","--format",
                       '{{json .Config.Labels}} {{json .Image}} {{json .Config.Image}} {{json .State.Status}}',cid)
            decoder=json.JSONDecoder()
            values=[]
            for _ in range(4):
                value,end=decoder.raw_decode(raw.lstrip())
                values.append(value)
                raw=raw.lstrip()[end:]
            labels,ident,ref,status=values
            service=labels.get("com.docker.compose.service")
            if labels.get("com.docker.compose.project")!=project:raise ValueError("Unexpected project")
            if str(labels.get("com.docker.compose.oneoff","false")).lower()=="true":continue
            if service not in services or service in seen or not IMAGE_ID.fullmatch(ident) or status not in {"running","exited","created"}:
                raise ValueError("Ambiguous or unsupported AfterGrid container state")
            if not isinstance(ref,str) or not ref or len(ref)>512:raise ValueError("Invalid configured image")
            seen.add(service)
            info=json.loads(docker("image","inspect","--format","{{json .Id}}",ident))
            if info!=ident:raise ValueError("Local image missing")
            result.append({"project":project,"service":service,"image_id":ident,"original_reference":ref,"state":status})
        if project=="aftergrid-core" and seen!=services:
            raise ValueError("Both core containers must exist")
    return sorted(result,key=lambda x:(x["project"],x["service"]))

def sha256_file(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream,"sha256").hexdigest()

def real_directory(path):
    path=Path(path).absolute()
    for parent in (path,*path.parents):
        if not stat.S_ISDIR(parent.lstat().st_mode):raise ValueError("Expected real directory")
    return path

def copy_file(src,dst,limit=FILE_LIMIT):
    info=src.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_size>limit:raise ValueError("Unsafe or oversized release file")
    dst.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd=os.open(src,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,"rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):raise ValueError("Unsafe release file")
        data=stream.read(limit+1)
    if len(data)>limit:raise ValueError("Oversized release file")
    with dst.open("xb") as out:out.write(data)
    dst.chmod(0o700 if info.st_mode&0o111 else 0o600)
    return len(data)

def copy_release(root,target):
    """Copy installed source/configuration, not the mutable data or Git history."""
    total=0
    for name in sorted(TOP_FILES):
        path=root/name
        if path.exists() or path.is_symlink():total+=copy_file(path,target/name)
    for name in sorted(SOURCE_DIRS):
        base=real_directory(root/name)
        for directory,dirs,files in os.walk(base,followlinks=False):
            current=Path(directory)
            dirs[:]=[d for d in dirs if d not in {"__pycache__",".pytest_cache",".venv","node_modules"} and not d.startswith(".")]
            if any((current/d).is_symlink() for d in dirs):raise ValueError("Symlink in release source")
            for filename in sorted(files):
                path=current/filename
                if filename.startswith("."):continue
                if filename!="Dockerfile" and path.suffix not in SOURCE_SUFFIXES:continue
                total+=copy_file(path,target/path.relative_to(root))
                if total>SOURCE_LIMIT:raise ValueError("Release exceeds source limit")
    for name in ("compose.yaml","install.sh","core/Dockerfile","worker/Dockerfile","recovery_prepare.py"):
        if not (target/name).is_file():raise ValueError("Incomplete installed release")
    for ident in MODULES:
        for name in ("compose.yaml","module.yaml"):
            if not (target/"modules"/ident/name).is_file():raise ValueError("Incomplete module release")
    # Copy raw environment separately; do not evaluate, expand or expose values.
    copy_file(root/".env",target/".env",65536)

def save_images(rows,path):
    ids=sorted({r["image_id"] for r in rows})
    if not ids or any(not IMAGE_ID.fullmatch(i) for i in ids):raise ValueError("Invalid image selection")
    subprocess.run(["docker","image","save","--output",str(path),*ids],check=True,
                   stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=6*60*60)
    if not stat.S_ISREG(path.lstat().st_mode) or not path.stat().st_size:raise ValueError("Empty image archive")
    path.chmod(0o600)

def capture(root,destination):
    root=real_directory(root)
    destination=Path(destination).absolute()
    parent=real_directory(destination.parent)
    if destination==root or root in destination.parents or destination.exists() or destination.is_symlink():
        raise ValueError("Choose a new destination outside the installed root")
    platform=local_docker()
    before=image_inventory()
    # A private staging directory on the destination filesystem, never the live root.
    stage=Path(tempfile.mkdtemp(prefix=".aftergrid-assets-",dir=parent))
    try:
        release=stage/"release"
        release.mkdir(mode=0o700)
        copy_release(root,release)
        save_images(before,stage/"images.tar")
        if image_inventory()!=before or local_docker()!=platform:
            raise ValueError("Container state changed during capture; retry during maintenance")
        files={}
        for path in sorted(stage.rglob("*")):
            if path.is_file():
                files[path.relative_to(stage).as_posix()]={"sha256":sha256_file(path),"bytes":path.stat().st_size}
        metadata={"format":1,"captured_at":int(time.time()),"platform":platform,"images":before,"files":files,
                  "scope":"installation assets only; no application data or repository",
                  "complete_recovery":False}
        with (stage/"assets-manifest.json").open("x") as out:json.dump(metadata,out,indent=2)
        (stage/"assets-manifest.json").chmod(0o600)
        # Publish only into a destination created exclusively by this call.
        destination.mkdir(mode=0o700)
        try:
            for path in stage.iterdir():path.rename(destination/path.name)
        except Exception:
            shutil.rmtree(destination)
            raise
        return metadata
    finally:shutil.rmtree(stage)

def verify(directory):
    directory=real_directory(directory)
    manifest=directory/"assets-manifest.json"
    if not stat.S_ISREG(manifest.lstat().st_mode) or not 0<manifest.stat().st_size<=1024*1024:
        raise ValueError("Invalid asset manifest")
    value=json.loads(manifest.read_text())
    if value.get("format")!=1 or value.get("platform") not in {"linux/amd64","linux/arm64"} or value.get("complete_recovery") is not False:
        raise ValueError("Unsupported asset manifest")
    expected=value["files"]
    if not isinstance(expected,dict) or "images.tar" not in expected or "release/.env" not in expected or "release/compose.yaml" not in expected:
        raise ValueError("Required assets missing")
    actual=set()
    for directory_path,dirs,files in os.walk(directory,followlinks=False):
        current=Path(directory_path)
        if any((current/d).is_symlink() for d in dirs):raise ValueError("Symlink in assets")
        for name in files:
            path=current/name
            info=path.lstat()
            if not stat.S_ISREG(info.st_mode):raise ValueError("Unexpected asset type")
            relative=path.relative_to(directory).as_posix()
            if relative=="assets-manifest.json":continue
            actual.add(relative)
            entry=expected.get(relative)
            if not isinstance(entry,dict) or info.st_size!=entry.get("bytes") or sha256_file(path)!=entry.get("sha256"):
                raise ValueError("Asset checksum or size mismatch")
    if actual!=set(expected):raise ValueError("Asset file set mismatch")
    images=value["images"]
    if not isinstance(images,list) or not images or any(not isinstance(x,dict) or not isinstance(x.get("image_id"),str) or not IMAGE_ID.fullmatch(x["image_id"]) for x in images):
        raise ValueError("Invalid image inventory")
    return value

def main():
    os.umask(0o077)
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="action",required=True)
    create=sub.add_parser("capture")
    create.add_argument("--root",type=Path,default=Path("/opt/aftergrid"))
    create.add_argument("--destination",type=Path,required=True)
    check=sub.add_parser("verify")
    check.add_argument("directory",type=Path)
    args=parser.parse_args()
    try:
        value=capture(args.root,args.destination) if args.action=="capture" else verify(args.directory)
    except Exception:
        parser.exit(1,"Offline asset operation refused or failed. Check local Docker, maintenance window, release files, destination, storage and checksums. No live services were modified.\n")
    print("Offline installation assets "+("captured" if args.action=="capture" else "verified")+": "+str(len(value["images"]))+" service images. Not a complete recovery package.")

if __name__=="__main__":
    main()
