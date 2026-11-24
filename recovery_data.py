#!/usr/bin/env python3
"""Restore exact managed application/content snapshots to a NEW staged root.

Use a trusted independently copied filesystem Kopia repository, read-only,
and the matching captured Kopia image. No live services are started.
"""
import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

import recovery_assets as assets
import recovery_prepare as prep
from worker import worker

SOURCES={
    "grocy":(("application/grocy","/source/data/grocy","data/grocy"),),
    "homebox":(("application/homebox","/source/data/homebox","data/homebox"),),
    "meshmonitor":(("application/meshmonitor","/source/data/meshmonitor","data/meshmonitor"),),
    "tak":(("application/tak","/source/data/tak","data/tak"),),
    "kolibri":(("application/kolibri","/source/data/kolibri","data/kolibri"),),
    "notes":(("application/notes","/source/data/notes","data/notes"),),
    "kiwix":(("content/kiwix","/source/content/kiwix","content/kiwix"),),
    "maps":(("content/maps","/source/content/maps","content/maps"),),
    "routing":(("content/routing","/source/content/routing","content/routing"),),
    "media":(("application/media","/source/data/media/config","data/media/config"),
             ("content/media","/source/content/media","content/media")),
}

def inventory_records(path,plan,metadata):
    value=json.loads(prep.read_private(path,65536))
    if value.get("format")!=1 or value.get("atomic") is not False or not isinstance(value.get("records"),list):
        raise ValueError("Invalid recovery inventory")
    records={}
    for row in value["records"]:
        key=row["key"]
        if key in records:raise ValueError("Duplicate inventory source")
        records[key]=row
    core=records["core"]
    state=records["worker"]
    if (core["snapshot_job"]!=plan["core_job"] or state["snapshot_job"]!=plan["worker_job"]
        or state.get("envelope_sha256")!=metadata["worker_envelope_sha256"]):
        raise ValueError("Inventory does not match staged core/worker exports")
    return records

def required_records(records,module):
    if module not in SOURCES:raise ValueError("Unsupported recovery module")
    result=[]
    for key,source,destination in SOURCES[module]:
        row=records.get(key,{})
        sid=row.get("snapshot_id")
        kind="read-only" if key.startswith("content/") else "isolated"
        if (row.get("source")!=source or row.get("repository_status")!="present"
            or row.get("verification")!=kind or not isinstance(sid,str)
            or not re.fullmatch(r"[a-f0-9]{32,64}",sid)):
            raise ValueError("Missing verified snapshot for requested module")
        result.append((key,source,destination,sid))
    return result

def safe_tree(path):
    path=Path(path)
    if not stat.S_ISDIR(path.lstat().st_mode):raise ValueError("Restore directory invalid")
    for current,dirs,files in os.walk(path,followlinks=False):
        base=Path(current)
        for name in dirs:
            if not stat.S_ISDIR((base/name).lstat().st_mode):raise ValueError("Unexpected restored directory type")
        for name in files:
            mode=(base/name).lstat().st_mode
            if not stat.S_ISREG(mode) or mode&(stat.S_ISUID|stat.S_ISGID):
                raise ValueError("Unexpected restored file type or privileged mode")

def placeholder(root,relative):
    path=root/relative
    # Only exact staged empty placeholders (or the initial Kiwix library)
    # can be replaced. Never overwrite recovered or unrelated data.
    if not path.exists() and not path.is_symlink():return False
    if not stat.S_ISDIR(path.lstat().st_mode):raise ValueError("Unsafe restore destination")
    names={x.name for x in path.iterdir()}
    if relative=="content/kiwix":
        if names!={"library.xml"} or not stat.S_ISREG((path/"library.xml").lstat().st_mode) or (path/"library.xml").read_bytes()!=(root/"modules/kiwix/library.xml").read_bytes():
            raise ValueError("Kiwix destination is not the initial placeholder")
    elif names:raise ValueError("Recovery destination is not empty")
    return True

def native_restore(image,repository,staging,password,source,sid):
    # Repository and output mounts are fixed local directories. The helper
    # has no Docker socket, no network and no writable repository access.
    for path in (repository,staging):
        if not re.fullmatch(r"/[a-zA-Z0-9_./-]+",str(path)):raise ValueError("Unsupported mount path")
    config=staging/"config"
    config.mkdir(mode=0o700)
    env={"PATH":os.environ["PATH"],"HOME":"/root","KOPIA_PASSWORD":password}
    cmd=["docker","run","--rm","--network","none","--pull","never","--user","0:0",
         "--env","KOPIA_PASSWORD","--env","KOPIA_CONFIG_PATH=/work/config/repository.config",
         "--env","KOPIA_CHECK_FOR_UPDATES=false","--env","KOPIA_PERSIST_CREDENTIALS_ON_CONNECT=false",
         "--mount","type=bind,src="+str(repository)+",dst=/repository,readonly",
         "--mount","type=bind,src="+str(staging)+",dst=/work",
         "--entrypoint","/bin/kopia",image]
    def run(*args,timeout=60):
        return subprocess.run([*cmd,*args],env=env,check=True,capture_output=True,timeout=timeout).stdout
    run("repository","connect","filesystem","--path=/repository","--readonly","--no-check-for-updates",timeout=120)
    raw=run("snapshot","list","--all","--json","--json-verbose","--manifest-id",timeout=120)
    if len(raw)>32*1024*1024:raise ValueError("Snapshot list exceeds recovery limit")
    rows=json.loads(raw)
    matches=[row for row in rows if row.get("id")==sid and row.get("source",{}).get("path")==source]
    if len(matches)!=1:raise ValueError("Exact snapshot missing from copied repository")
    row=matches[0]
    worker.snapshot_statistics(row,source)
    obj=row["rootEntry"]["obj"]
    if not isinstance(obj,str) or not re.fullmatch(r"[IZD]{0,8}[a-z]?[a-f0-9]{32,128}",obj):
        raise ValueError("Invalid native object ID")
    run("restore","--no-overwrite-files","--no-overwrite-symlinks","--no-ignore-permission-errors",
        "--write-files-atomically","--flush-files",obj,"/work/data",timeout=6*60*60)
    result=staging/"data"
    safe_tree(result)
    return result

def load_plan(root,assets_dir):
    value=assets.verify(assets_dir)
    plan=json.loads(prep.read_private(root/"recovery-install-plan.json",65536))
    metadata=json.loads(prep.read_private(root/"recovery-metadata.json",65536))
    rows=assets.recovery_image_rows(value)
    if (plan.get("format")!=1 or plan.get("root")!=str(root) or plan.get("core_only") is not True
        or plan.get("images")!=rows or plan.get("assets_manifest_sha256")!=assets.sha256_file(assets_dir/"assets-manifest.json")):
        raise ValueError("Recovery plan mismatch")
    return value,plan,metadata,rows

def restore_module(root,assets_dir,repository,inventory,module):
    if os.geteuid()!=0:raise ValueError("Root required for native ownership restoration")
    root,assets_dir,repository=map(assets.real_directory,(root,assets_dir,repository))
    if any(p==root or root in p.parents or p in root.parents for p in (assets_dir,repository)):
        raise ValueError("Keep archive and repository separate from installation")
    value,plan,metadata,rows=load_plan(root,assets_dir)
    if assets.local_docker()!=value["platform"] or assets.docker("ps","--all","--quiet"):
        raise ValueError("Restore before starting services on an empty replacement host")
    if module not in SOURCES or not any(r["project"]=="aftergrid-"+module for r in rows):
        raise ValueError("Requested module image is not captured")
    kopia=next((r for r in rows if r["project"]=="aftergrid-kopia"),None)
    if kopia is None or json.loads(assets.docker("image","inspect","--format","{{json .Id}}",kopia["recovery_tag"]))!=kopia["image_id"]:
        raise ValueError("Imported Kopia image required")
    records=inventory_records(inventory,plan,metadata)
    required=required_records(records,module)
    secret=json.loads(prep.read_private(root/"recovery-worker-state/secrets/kopia.json",16384))
    password=secret["KOPIA_PASSWORD"]
    if not isinstance(password,str) or not re.fullmatch(r"[a-f0-9]{64}",password):raise ValueError("Invalid recovered repository password")
    receipt_dir=root/"recovery-restored"
    receipt_dir.mkdir(mode=0o700,exist_ok=True)
    assets.real_directory(receipt_dir)
    receipt=receipt_dir/(module+".json")
    if receipt.exists() or receipt.is_symlink():raise ValueError("Module already restored")
    for _,_,relative,_ in required:
        target=root/relative
        # Create only fixed reviewed parent directories under the staged root.
        target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        assets.real_directory(target.parent)
        placeholder(root,relative)
    workspace=Path(tempfile.mkdtemp(prefix=".restore-"+module+"-",dir=root))
    published=[]
    try:
        for index,(_,source,relative,sid) in enumerate(required):
            current=workspace/str(index)
            current.mkdir(mode=0o700)
            result=native_restore(kopia["recovery_tag"],repository,current,password,source,sid)
            target=root/relative
            old=current/"placeholder"
            had=placeholder(root,relative)
            if had:target.rename(old)
            try:result.rename(target)
            except Exception:
                if had:old.rename(target)
                raise
            published.append((target,old,had))
        if module=="media":
            cache=root/"data/media/cache"
            cache.mkdir(mode=0o700)
            os.chown(cache,10001,10001)
        prep.private_write(receipt,json.dumps({"format":1,"module":module,
            "inventory_sha256":assets.sha256_file(inventory),
            "snapshots":{key:sid for key,_,_,sid in required},
            "native_restore":True,"application_started":False},indent=2).encode())
    except Exception:
        for target,old,had in reversed(published):
            # Move only the new data we published, then put placeholders back.
            target.rename(workspace/("failed-"+str(len(published))+"-"+target.name))
            if had:old.rename(target)
        raise
    finally:
        shutil.rmtree(workspace)

def main():
    os.umask(0o077)
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("root","assets","repository","inventory"):p.add_argument("--"+name,required=True,type=Path)
    p.add_argument("--module",required=True,choices=sorted(SOURCES))
    p.add_argument("--confirm-replacement",action="store_true")
    args=p.parse_args()
    try:
        if not args.confirm_replacement:raise ValueError("Confirm replacement-only restoration")
        restore_module(args.root,args.assets,args.repository,args.inventory,args.module)
    except Exception:
        p.exit(1,"Native data restoration refused or failed. Check exact verified snapshot, copied repository, local images, destination and space. No application was started.\n")
    print("Exact native data restored for "+args.module+". Application startup remains separate.")

if __name__=="__main__":
    main()
