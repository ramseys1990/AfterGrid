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
import recovery_install as installation
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

BLOCKED_RECOVERY={"tak":"MicroTAK 0.18.1 has no confirmed application-consistent capture and native restore acceptance"}


def required_records(records,module):
    if module in BLOCKED_RECOVERY:raise ValueError(BLOCKED_RECOVERY[module])
    # Kopia uses an independently copied native repository, not a snapshot of itself.
    if module=="kopia":return []
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

def native_repository_command(image,repository,staging,password):
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
    return run

def native_manifest_rows(run):
    raw=run("snapshot","list","--all","--json","--json-verbose","--manifest-id",timeout=120)
    if len(raw)>32*1024*1024:raise ValueError("Snapshot list exceeds recovery limit")
    rows=json.loads(raw)
    if not isinstance(rows,list):raise ValueError("Invalid native snapshot list")
    return rows

def exact_native_manifest(rows,source,sid):
    matches=[row for row in rows if row.get("id")==sid and row.get("source",{}).get("path")==source]
    if len(matches)!=1:raise ValueError("Exact snapshot missing from copied repository")
    row=matches[0]
    worker.snapshot_statistics(row,source)
    obj=row["rootEntry"]["obj"]
    if not isinstance(obj,str) or not re.fullmatch(r"[IZD]{0,8}[a-z]?[a-f0-9]{32,128}",obj):
        raise ValueError("Invalid native object ID")
    return obj

def native_restore(image,repository,staging,password,source,sid):
    run=native_repository_command(image,repository,staging,password)
    obj=exact_native_manifest(native_manifest_rows(run),source,sid)
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
    cache_created=False
    rollback_complete=False
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
            cache_created=True
            os.chown(cache,10001,10001)
        prep.private_write(receipt,json.dumps({"format":1,"module":module,
            "inventory_sha256":assets.sha256_file(inventory),
            "snapshots":{key:sid for key,_,_,sid in required},
            "native_restore":True,"application_started":False},indent=2).encode())
        rollback_complete=True
    except Exception:
        if cache_created:(root/"data/media/cache").rmdir()
        for index,(target,old,had) in enumerate(reversed(published)):
            # Move only the new data we published, then put placeholders back.
            target.rename(workspace/("failed-"+str(index)))
            if had:old.rename(target)
        rollback_complete=True
        raise
    finally:
        # If rollback itself failed, retain the workspace for operator inspection.
        if rollback_complete:shutil.rmtree(workspace)

def module_command(root,module):
    folder=root/"modules"/module
    return ["docker","compose","--project-name","aftergrid-"+module,
            "--project-directory",str(folder),"--file",str(folder/"compose.yaml"),
            "--file",str(root/"recovery-overrides"/("aftergrid-"+module+".json"))]

def validate_module_config(root,module,definition,row):
    if definition.get("image")!=row["recovery_tag"] or definition.get("pull_policy")!="never" or definition.get("build") is not None or definition.get("privileged"):
        raise ValueError("Module image policy or privilege mismatch")
    for port in definition.get("ports",[]):
        if port.get("host_ip")!="127.0.0.1":raise ValueError("Recovery ports must be loopback only")
    for mount in definition.get("volumes",[]):
        if mount.get("type")!="bind":raise ValueError("Unexpected recovery mount")
        path=Path(mount["source"])
        if root not in path.parents or ".." in path.parts:
            raise ValueError("Module mount outside recovery root")
        for parent in path.parents:
            if not stat.S_ISDIR(parent.lstat().st_mode):raise ValueError("Unsafe mount parent")
        if not (stat.S_ISREG(path.lstat().st_mode) or stat.S_ISDIR(path.lstat().st_mode)):
            raise ValueError("Unsafe module mount")
    if set(definition.get("networks",{}))!={"apps"}:raise ValueError("Unexpected recovery network")

def start_module(root,assets_dir,inventory,module):
    """Explicitly start a restored module while the recovered core is guarded."""
    if os.geteuid()!=0:raise ValueError("Root required")
    root,assets_dir=map(assets.real_directory,(root,assets_dir))
    value,plan,metadata,rows=load_plan(root,assets_dir)
    if assets.local_docker()!=value["platform"]:raise ValueError("Architecture mismatch")
    required=required_records(inventory_records(inventory,plan,metadata),module)
    receipt=root/"recovery-restored"/(module+".json")
    record=json.loads(prep.read_private(receipt,65536))
    if (record.get("format")!=1 or record.get("module")!=module or record.get("native_restore") is not True
        or record.get("application_started") is not False
        or record.get("inventory_sha256")!=assets.sha256_file(inventory)
        or record.get("snapshots")!={key:sid for key,_,_,sid in required}):
        raise ValueError("Matching unused restoration receipt required")
    for _,_,relative,_ in required:safe_tree(root/relative)
    if module=="kopia":
        if record.get("repository_copy_connected_readonly") is not True:raise ValueError("Kopia read-only working copy required")
        for relative in ("backups","data/kopia/config","data/kopia/cache","data/kopia/logs","restore"):assets.real_directory(root/relative)
    row=next((r for r in rows if r["project"]=="aftergrid-"+module),None)
    if row is None or json.loads(assets.docker("image","inspect","--format","{{json .Id}}",row["recovery_tag"]))!=row["image_id"]:
        raise ValueError("Exact imported module image missing")
    if assets.docker("ps","--all","--quiet","--filter","label=com.docker.compose.project=aftergrid-"+module):
        raise ValueError("Existing module container; inspect before retrying")
    # Verify the running core/worker are the guarded replacement installation.
    core_cmd=installation.compose_command(root)
    env={"PATH":os.environ["PATH"],"HOME":"/root","DOCKER_HOST":"unix:///var/run/docker.sock"}
    def run(cmd,*args,timeout=30,environment=env):
        return subprocess.run([*cmd,*args],env=environment,check=True,capture_output=True,text=True,timeout=timeout).stdout.strip()
    core_ids={}
    for core in (r for r in rows if r["project"]=="aftergrid-core"):
        cid=run(core_cmd,"ps","-q",core["service"])
        if not re.fullmatch(r"[a-f0-9]{12,64}",cid):raise ValueError("Recovered core not running")
        info=json.loads(assets.docker("container","inspect","--format","{{json .}}",cid))
        if (info["Image"]!=core["image_id"] or info["State"]["Running"] is not True
            or info["Config"]["Labels"].get("com.docker.compose.project.working_dir")!=str(root)
            or "AFTERGRID_RECOVERY_CORE_ONLY=1" not in info["Config"]["Env"]):
            raise ValueError("Guarded recovered core not confirmed")
        core_ids[core["service"]]=cid
    # Match the worker's reviewed interpolation rules. No missing secret may
    # be substituted with a placeholder or regenerated.
    old=(worker.MODULES,worker.STATE,worker.ROOT,worker.BIND,worker.LAN_BIND,worker.LAN_DOMAIN)
    worker.MODULES=root/"modules"
    worker.STATE=root/"recovery-worker-state"
    worker.ROOT=str(root)
    worker.BIND=worker.LAN_BIND="127.0.0.1"
    worker.LAN_DOMAIN=""
    try:
        names=worker.catalog()[module].get("generated_secrets",[])
        if names:
            secret=json.loads(prep.read_private(worker.STATE/"secrets"/(module+".json"),16384))
            if set(secret)!=set(names) or not all(isinstance(v,str) and re.fullmatch(r"[a-f0-9]{64}",v) for v in secret.values()):
                raise ValueError("Recovered module credentials required")
        module_env=worker.compose_env(module)
    finally:worker.MODULES,worker.STATE,worker.ROOT,worker.BIND,worker.LAN_BIND,worker.LAN_DOMAIN=old
    cmd=module_command(root,module)
    config=json.loads(run(cmd,"config","--format","json",environment=module_env))
    if set(config["services"])!={row["service"]}:raise ValueError("Unexpected module service")
    validate_module_config(root,module,config["services"][row["service"]],row)
    if config.get("networks",{}).get("apps",{}).get("name")!="aftergrid-apps":
        raise ValueError("Unexpected shared network")
    run(cmd,"up","-d","--no-build","--pull","never","--wait","--wait-timeout","90",timeout=120,environment=module_env)
    cid=run(cmd,"ps","-q",row["service"],environment=module_env)
    if not re.fullmatch(r"[a-f0-9]{12,64}",cid) or json.loads(assets.docker("container","inspect","--format","{{json .Image}}",cid))!=row["image_id"]:
        raise ValueError("Recovered module container image mismatch")
    run(["docker","exec",core_ids["worker"],"python3","-c",
         "import worker,sys; worker.wait_ready(sys.argv[1])",module],timeout=110)
    if module=="kopia":
        run(["docker","exec",core_ids["worker"],"python3","-c",
             "import worker; s=worker.kopia_status(); assert s['connection']=='connected' and s['storage_type']=='filesystem'"],timeout=30)
    record.update(application_started=True,image_id=row["image_id"],readiness="native readiness probe passed")
    fd,tmp=tempfile.mkstemp(prefix=".receipt-",dir=receipt.parent)
    try:
        with os.fdopen(fd,"w") as stream:
            json.dump(record,stream,indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp,receipt)
    finally:Path(tmp).unlink(missing_ok=True)
    return record

def prepare_offline_policy(root,assets_dir,inventory,modules):
    """Stage mappings for explicitly selected, started recovered modules.

    Do not remove the core-only guard or recreate containers here.
    """
    if os.geteuid()!=0:raise ValueError("Root required")
    root,assets_dir=map(assets.real_directory,(root,assets_dir))
    value,plan,metadata,rows=load_plan(root,assets_dir)
    records=inventory_records(inventory,plan,metadata)
    if not modules or len(modules)!=len(set(modules)):raise ValueError("Choose distinct recovered modules")
    if assets.local_docker()!=value["platform"]:raise ValueError("Architecture mismatch")
    mapping={}
    for module in sorted(modules):
        required=required_records(records,module)
        receipt=json.loads(prep.read_private(root/"recovery-restored"/(module+".json"),65536))
        row=next((r for r in rows if r["project"]=="aftergrid-"+module),None)
        if (row is None or receipt.get("module")!=module or receipt.get("native_restore") is not True
            or receipt.get("application_started") is not True or receipt.get("image_id")!=row["image_id"]
            or receipt.get("inventory_sha256")!=assets.sha256_file(inventory)
            or receipt.get("snapshots")!={key:sid for key,_,_,sid in required}):
            raise ValueError("Matching restored and started module required")
        if module=="kopia" and receipt.get("repository_copy_connected_readonly") is not True:raise ValueError("Read-only repository receipt required")
        if json.loads(assets.docker("image","inspect","--format","{{json .Id}}",row["recovery_tag"]))!=row["image_id"]:
            raise ValueError("Recovered image changed")
        mapping[module]={"image_id":row["image_id"],"recovery_tag":row["recovery_tag"]}
    state=assets.real_directory(root/"recovery-worker-state")
    target=state/"offline-images"
    target.mkdir(mode=0o700)
    try:
        for ident,row in mapping.items():
            prep.private_write(target/(ident+".json"),json.dumps({"services":{ident:{"image":row["recovery_tag"],"pull_policy":"never"}}}).encode())
        prep.private_write(target/"mapping.json",json.dumps(mapping,indent=2).encode())
    except Exception:
        shutil.rmtree(target)
        raise
    return mapping

def main():
    os.umask(0o077)
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("root","assets","inventory"):p.add_argument("--"+name,required=True,type=Path)
    p.add_argument("--repository",type=Path)
    p.add_argument("--start",action="store_true",help="Start a previously restored module after guarded core startup")
    p.add_argument("--module",choices=sorted(SOURCES))
    p.add_argument("--prepare-offline-module",action="append",choices=sorted(SOURCES),help="Stage offline policy for selected already-started modules; repeat for each")
    p.add_argument("--confirm-replacement",action="store_true")
    args=p.parse_args()
    try:
        if not args.confirm_replacement:raise ValueError("Confirm replacement-only restoration")
        if args.prepare_offline_module:
            if args.start or args.module or args.repository:raise ValueError("Choose one recovery operation")
            mapping=prepare_offline_policy(args.root,args.assets,args.inventory,args.prepare_offline_module)
            print("Offline worker image policy prepared for "+str(len(mapping))+" modules. Guard remains active; not enabled.")
            return
        if not args.module:raise ValueError("Select module")
        if args.start:
            start_module(args.root,args.assets,args.inventory,args.module)
            print("Recovered "+args.module+" started using its exact local image; readiness passed. Core-only guard remains active.")
        else:
            if args.repository is None:raise ValueError("Copied repository required")
            restore_module(args.root,args.assets,args.repository,args.inventory,args.module)
            print("Exact native data restored for "+args.module+". Application startup remains separate.")
    except Exception:
        p.exit(1,"Recovery operation refused or failed. Check exact verified snapshot, copied repository, local images, destination and space. A failed startup may leave containers; inspect manually.\n")

if __name__=="__main__":
    main()
