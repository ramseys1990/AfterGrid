#!/usr/bin/env python3
"""One replacement-only recovery command using native Docker and Kopia.

Creates a guarded local installation. A separate explicit completion command
enables restricted offline lifecycle administration; neither proves full recovery.
"""
import argparse
import getpass
import hashlib
import hmac
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import recovery_assets as assets
import recovery_data as data
import recovery_install as install
import recovery_prepare as prep

CORE_SOURCE="/source/data/core/recovery-export"
WORKER_SOURCE="/tmp/aftergrid-worker-export"

def core_records(inventory):
    value=json.loads(prep.read_private(inventory,65536))
    if value.get("format")!=1 or value.get("atomic") is not False:raise ValueError("Unsupported recovery inventory")
    records={}
    for row in value["records"]:
        if row["key"] in records:raise ValueError("Duplicate inventory source")
        records[row["key"]]=row
    for key,source in (("core",CORE_SOURCE),("worker",WORKER_SOURCE)):
        row=records[key]
        if (row.get("source")!=source or row.get("repository_status")!="present" or row.get("verification")!="isolated"
            or not isinstance(row.get("snapshot_id"),str) or not re.fullmatch(r"[a-f0-9]{32,64}",row["snapshot_id"])
            or type(row.get("snapshot_job")) is not int or not 0<row["snapshot_job"]<10**19):
            raise ValueError("Verified exact core and worker snapshots required")
    if not re.fullmatch(r"[a-f0-9]{64}",records["worker"].get("envelope_sha256") or ""):
        raise ValueError("Worker envelope digest required")
    return records

def copy_and_connect_kopia(root,assets_dir,repository,inventory):
    """Use a separate working copy; no mutation of original repository."""
    root,assets_dir,repository=map(assets.real_directory,(root,assets_dir,repository))
    if root==repository or root in repository.parents or repository in root.parents:
        raise ValueError("Repository must be separate")
    if assets.docker("ps","--all","--quiet"):raise ValueError("Prepare Kopia before startup")
    value,plan,metadata,rows=data.load_plan(root,assets_dir)
    data.inventory_records(inventory,plan,metadata)
    row=next(r for r in rows if r["project"]=="aftergrid-kopia")
    if assets.local_docker()!=value["platform"] or json.loads(assets.docker("image","inspect","--format","{{json .Id}}",row["recovery_tag"]))!=row["image_id"]:
        raise ValueError("Exact local Kopia image required")
    password=json.loads(prep.read_private(root/"recovery-worker-state/secrets/kopia.json",16384))["KOPIA_PASSWORD"]
    if not re.fullmatch(r"[a-f0-9]{64}",password):raise ValueError("Invalid repository password")
    data.safe_tree(repository)
    target=root/"backups"
    cfg=root/"data/kopia"
    restore=root/"restore"
    for p in (target,cfg,restore):
        if p.exists() or p.is_symlink():raise ValueError("Kopia destination exists")
    created=[]
    try:
        for p in (target,cfg,restore):
            p.mkdir(mode=0o700)
            created.append(p)
        for name in ("config","cache","logs"):(cfg/name).mkdir(mode=0o700)
        # Native filesystem copy preserves permissions; reflink where possible.
        subprocess.run(["cp","-a","--reflink=auto",str(repository)+"/.",str(target)],
                       check=True,capture_output=True,timeout=6*60*60)
        data.safe_tree(target)
        env={"PATH":os.environ["PATH"],"HOME":"/root","KOPIA_PASSWORD":password}
        cmd=["docker","run","--rm","--network","none","--pull","never","--user","0:0","--hostname","aftergrid-kopia",
             "--env","USER=aftergrid","--env","KOPIA_PASSWORD","--env","KOPIA_CHECK_FOR_UPDATES=false",
             "--env","KOPIA_PERSIST_CREDENTIALS_ON_CONNECT=false"]
        for source,dest in ((target,"/repository"),(cfg/"config","/app/config"),(cfg/"cache","/app/cache"),(cfg/"logs","/app/logs")):
            if not re.fullmatch(r"/[a-zA-Z0-9_./-]+",str(source)):raise ValueError("Invalid mount path")
            cmd.extend(("--mount","type=bind,src="+str(source)+",dst="+dest+(",readonly" if source==target else "")))
        cmd.extend(("--entrypoint","/bin/kopia",row["recovery_tag"]))
        subprocess.run([*cmd,"repository","connect","filesystem","--path=/repository","--readonly","--no-check-for-updates"],
                       env=env,check=True,capture_output=True,timeout=120)
        if not (cfg/"config/repository.config").is_file():raise ValueError("Native configuration missing")
        receipts=root/"recovery-restored"
        receipts.mkdir(mode=0o700,exist_ok=True)
        assets.real_directory(receipts)
        prep.private_write(receipts/"kopia.json",json.dumps({"format":1,"module":"kopia","native_restore":True,
            "inventory_sha256":assets.sha256_file(inventory),"snapshots":{},"application_started":False,
            "repository_copy_connected_readonly":True}).encode())
    except Exception:
        for p in reversed(created):shutil.rmtree(p)
        raise

def recover(root,assets_dir,repository,inventory,modules,password):
    if os.geteuid()!=0:raise ValueError("Root required")
    root=install.validate_root(root)
    assets_dir,repository=map(assets.real_directory,(assets_dir,repository))
    if any(root==p or root in p.parents or p in root.parents for p in (assets_dir,repository)):
        raise ValueError("Separate installation, assets and repository directories required")
    if not password or len(password)>1024:raise ValueError("Repository password required")
    records=core_records(inventory)
    value=assets.verify(assets_dir)
    rows=assets.recovery_image_rows(value)
    captured={row["service"] for row in rows if row["project"]!="aftergrid-core"}
    if "kopia" not in captured:raise ValueError("Kopia image must be captured")
    if len(modules)!=len(set(modules)) or any(m not in data.SOURCES or m not in captured for m in modules):
        raise ValueError("Choose distinct captured applications")
    for m in modules:data.required_records(records,m)
    # Require a deliberate selection; never silently omit a captured app.
    omitted=sorted(captured-{"kopia"}-set(modules))
    print("Selected modules: "+(", ".join(modules) or "core only")+"; omitted captured modules: "+(", ".join(omitted) or "none"),flush=True)
    assets.import_images(assets_dir,True)
    kopia=next(r for r in rows if r["project"]=="aftergrid-kopia")
    with tempfile.TemporaryDirectory(prefix=".aftergrid-exports-",dir=root.parent) as tmp:
        tmp=Path(tmp)
        exports={}
        for key,source in (("core",CORE_SOURCE),("worker",WORKER_SOURCE)):
            workspace=tmp/key
            workspace.mkdir(mode=0o700)
            exports[key]=data.native_restore(kopia["recovery_tag"],repository,workspace,password,source,records[key]["snapshot_id"])
        install.stage(assets_dir,exports["core"],exports["worker"],root,records["core"]["snapshot_job"],
                      records["worker"]["snapshot_job"],records["worker"]["envelope_sha256"])
    saved=json.loads(prep.read_private(root/"recovery-worker-state/secrets/kopia.json",16384))["KOPIA_PASSWORD"]
    if not hmac.compare_digest(saved,password):raise ValueError("Repository password differs from recovered credential; inspect before continuing")
    for m in modules:
        print("Restoring "+m,flush=True)
        data.restore_module(root,assets_dir,repository,inventory,m)
    print("Preparing independent Kopia working copy",flush=True)
    copy_and_connect_kopia(root,assets_dir,repository,inventory)
    install.start_core(root,assets_dir,True)
    for m in ["kopia",*modules]:
        print("Starting "+m+" with exact local image",flush=True)
        data.start_module(root,assets_dir,inventory,m)
    data.prepare_offline_policy(root,assets_dir,inventory,["kopia",*modules])
    report={"format":1,"selected":modules,"omitted_captured":omitted,"inventory_sha256":assets.sha256_file(inventory),
            "guarded":True,"repository_readonly":True,"complete_recovery":False}
    prep.private_write(root/"recovery-guided-report.json",json.dumps(report,indent=2).encode())
    return report

def enable_backups(root,assets_dir,inventory):
    """Opt in to native writes on the independent copy, before activation."""
    if os.geteuid()!=0:raise ValueError("Root required")
    root,assets_dir=map(assets.real_directory,(root,assets_dir))
    value,plan,metadata,rows=data.load_plan(root,assets_dir)
    data.inventory_records(inventory,plan,metadata)
    report=json.loads(prep.read_private(root/"recovery-guided-report.json",65536))
    if report.get("guarded") is not True or report.get("repository_readonly") is not True or report.get("inventory_sha256")!=assets.sha256_file(inventory):
        raise ValueError("Guided recovery report mismatch")
    receipt=json.loads(prep.read_private(root/"recovery-restored/kopia.json",65536))
    if receipt.get("repository_copy_connected_readonly") is not True or receipt.get("application_started") is not True or receipt.get("inventory_sha256")!=report["inventory_sha256"]:
        raise ValueError("Read-only working copy receipt required")
    marker=root/"recovery-worker-state/offline-kopia-writable.json"
    if marker.exists() or marker.is_symlink():raise ValueError("Writable backup opt-in already exists")
    if assets.local_docker()!=value["platform"]:raise ValueError("Architecture mismatch")
    row=next(r for r in rows if r["project"]=="aftergrid-kopia")
    env={"PATH":os.environ["PATH"],"HOME":"/root","DOCKER_HOST":"unix:///var/run/docker.sock"}
    cmd=install.compose_command(root)
    def run(argv,*args,timeout=30,environment=env):
        return subprocess.run([*argv,*args],env=environment,check=True,capture_output=True,text=True,timeout=timeout).stdout.strip()
    for core in (r for r in rows if r["project"]=="aftergrid-core"):
        cid=run(cmd,"ps","-q",core["service"])
        if not re.fullmatch(r"[a-f0-9]{12,64}",cid):raise ValueError("Guarded core required")
        info=json.loads(assets.docker("container","inspect","--format","{{json .}}",cid))
        if (info["Image"]!=core["image_id"] or not info["State"]["Running"]
            or info["Config"]["Labels"].get("com.docker.compose.project.working_dir")!=str(root)
            or "AFTERGRID_RECOVERY_CORE_ONLY=1" not in info["Config"]["Env"]):
            raise ValueError("Guarded core mismatch; enable backups before activation")
    ids=assets.docker("ps","--quiet","--filter","label=com.docker.compose.project=aftergrid-kopia").splitlines()
    if len(ids)!=1:raise ValueError("Exactly one recovered Kopia container required")
    cid=ids[0]
    info=json.loads(assets.docker("container","inspect","--format","{{json .}}",cid))
    repository=assets.real_directory(root/"backups")
    cfg=assets.real_directory(root/"data/kopia/config")
    mounts={m["Destination"]:m for m in info["Mounts"]}
    if (info["Image"]!=row["image_id"] or not info["State"]["Running"]
        or mounts.get("/repository",{}).get("Source")!=str(repository)
        or mounts.get("/app/config",{}).get("Source")!=str(cfg)
        or json.loads(assets.docker("image","inspect","--format","{{json .Id}}",row["recovery_tag"]))!=row["image_id"]):
        raise ValueError("Recovered Kopia copy or image mismatch")
    current=cfg/"repository.config"
    original=prep.read_private(current,65536)
    old=json.loads(original)
    if old.get("readonly") is not True or old.get("storage",{}).get("type")!="filesystem" or old["storage"].get("config",{}).get("path")!="/repository":
        raise ValueError("Expected native read-only filesystem connection")
    next_path=cfg/"repository-next.config"
    if next_path.exists() or next_path.is_symlink():raise ValueError("Inspect existing recovery config candidate")
    password=json.loads(prep.read_private(root/"recovery-worker-state/secrets/kopia.json",16384))["KOPIA_PASSWORD"]
    if not re.fullmatch(r"[a-f0-9]{64}",password):raise ValueError("Invalid recovered repository password")
    helper_env={**env,"KOPIA_PASSWORD":password}
    helper=["docker","run","--rm","--network","none","--pull","never","--user","0:0","--hostname","aftergrid-kopia",
            "--env","USER=aftergrid","--env","KOPIA_PASSWORD","--env","KOPIA_CHECK_FOR_UPDATES=false",
            "--env","KOPIA_PERSIST_CREDENTIALS_ON_CONNECT=false","--env","KOPIA_CONFIG_PATH=/app/config/repository-next.config"]
    for source,dest in ((repository,"/repository"),(cfg,"/app/config"),(root/"data/kopia/cache","/app/cache"),(root/"data/kopia/logs","/app/logs")):
        assets.real_directory(source)
        if not re.fullmatch(r"/[a-zA-Z0-9_./-]+",str(source)):raise ValueError("Invalid mount path")
        helper.extend(("--mount","type=bind,src="+str(source)+",dst="+dest))
    helper.extend(("--entrypoint","/bin/kopia",row["recovery_tag"]))
    swapped=False
    run(["docker"],"stop","--time","30",cid,timeout=45)
    try:
        run(helper,"repository","connect","filesystem","--path=/repository","--no-check-for-updates",timeout=120,environment=helper_env)
        candidate=json.loads(prep.read_private(next_path,65536))
        if candidate.get("readonly",False) is not False or candidate.get("storage",{}).get("type")!="filesystem" or candidate["storage"].get("config",{}).get("path")!="/repository":
            raise ValueError("Native writable connection not confirmed")
        os.replace(next_path,current)
        swapped=True
        run(["docker"],"start",cid)
        import time
        deadline=time.monotonic()+60
        while True:
            try:
                status=json.loads(run(["docker","exec",cid,"/bin/kopia"],"repository","status","--json",timeout=10))
                if status["clientOptions"].get("readonly",False) is not False or status["storage"]["type"]!="filesystem":
                    raise ValueError("Writable repository not confirmed")
                break
            except (subprocess.SubprocessError,ValueError,KeyError):
                if time.monotonic()>deadline:raise
                time.sleep(2)
        prep.private_write(marker,b'{"format":1,"repository":"/repository"}')
    except Exception:
        # Restore the prior guarded connection. The copy may contain native
        # maintenance writes; the original repository remains untouched.
        if swapped:
            run(["docker"],"stop","--time","30",cid,timeout=45)
            fd,tmp=tempfile.mkstemp(prefix=".readonly-",dir=cfg)
            with os.fdopen(fd,"wb") as out:out.write(original)
            os.replace(tmp,current)
        next_path.unlink(missing_ok=True)
        run(["docker"],"start",cid)
        raise

def activate(root,assets_dir,inventory):
    """Enable restricted local lifecycle mode after operator native checks."""
    if os.geteuid()!=0:raise ValueError("Root required")
    root,assets_dir=map(assets.real_directory,(root,assets_dir))
    value,plan,metadata,rows=data.load_plan(root,assets_dir)
    report=json.loads(prep.read_private(root/"recovery-guided-report.json",65536))
    if report.get("format")!=1 or report.get("guarded") is not True or report.get("inventory_sha256")!=assets.sha256_file(inventory):
        raise ValueError("Guided recovery report mismatch")
    mapping=json.loads(prep.read_private(root/"recovery-worker-state/offline-images/mapping.json",65536))
    if set(mapping)!={"kopia",*report["selected"]}:raise ValueError("Offline module selection mismatch")
    if assets.local_docker()!=value["platform"]:raise ValueError("Architecture mismatch")
    env={"PATH":os.environ["PATH"],"HOME":"/root","DOCKER_HOST":"unix:///var/run/docker.sock"}
    cmd=install.compose_command(root)
    def run(*args,timeout=30):
        return subprocess.run([*cmd,*args],env=env,check=True,capture_output=True,text=True,timeout=timeout).stdout.strip()
    expected={r["service"]:r for r in rows if r["project"]=="aftergrid-core"}
    for name,row in expected.items():
        cid=run("ps","-q",name)
        if not re.fullmatch(r"[a-f0-9]{12,64}",cid):raise ValueError("Guarded core not running")
        obj=json.loads(assets.docker("container","inspect","--format","{{json .}}",cid))
        if (obj["Image"]!=row["image_id"] or not obj["State"]["Running"] or
            obj["Config"]["Labels"].get("com.docker.compose.project.working_dir")!=str(root)
            or "AFTERGRID_RECOVERY_CORE_ONLY=1" not in obj["Config"]["Env"]):
            raise ValueError("Guarded replacement core mismatch")
        if json.loads(assets.docker("image","inspect","--format","{{json .Id}}",row["recovery_tag"]))!=row["image_id"]:
            raise ValueError("Core image changed")
    if assets.docker("image","inspect","--format",'{{index .Config.Labels "org.aftergrid.recovery-offline"}}',expected["worker"]["recovery_tag"])!="1":
        raise ValueError("Captured worker lacks offline policy support")
    records=core_records(inventory)
    for m,entry in mapping.items():
        row=next(r for r in rows if r["project"]=="aftergrid-"+m)
        if entry!={"image_id":row["image_id"],"recovery_tag":row["recovery_tag"]}:
            raise ValueError("Offline image policy differs from capture")
        if json.loads(assets.docker("image","inspect","--format","{{json .Id}}",row["recovery_tag"]))!=row["image_id"]:
            raise ValueError("Module image changed")
        rec=json.loads(prep.read_private(root/"recovery-restored"/(m+".json"),65536))
        if (rec.get("application_started") is not True or rec.get("image_id")!=row["image_id"] or rec.get("inventory_sha256")!=report["inventory_sha256"]
            or rec.get("snapshots")!={k:sid for k,_,_,sid in data.required_records(records,m)}):
            raise ValueError("Started module receipt missing")
        # Verify the expected override rather than trusting a mutable tag alone.
        override=json.loads(prep.read_private(root/"recovery-worker-state/offline-images"/(m+".json"),4096))
        if override!={"services":{m:{"image":row["recovery_tag"],"pull_policy":"never"}}}:raise ValueError("Unexpected policy override")
        ids=assets.docker("ps","--quiet","--filter","label=com.docker.compose.project=aftergrid-"+m).splitlines()
        if len(ids)!=1 or json.loads(assets.docker("container","inspect","--format","{{json .Image}}",ids[0]))!=row["image_id"]:
            raise ValueError("Recovered module no longer running with exact image")
    path=root/"recovery-overrides/aftergrid-core.json"
    original=prep.read_private(path,65536)
    config=json.loads(original)
    for name in ("core","worker"):
        config["services"][name]["environment"]={"AFTERGRID_RECOVERY_CORE_ONLY":"0","AFTERGRID_RECOVERY_OFFLINE":"1"}
    # Write atomically; if recreation fails, restore guarded override and try
    # guarded recreation. Never claim successful activation after failure.
    def replace(payload):
        fd,tmp=tempfile.mkstemp(prefix=".core-override-",dir=path.parent)
        try:
            with os.fdopen(fd,"wb") as stream:stream.write(payload)
            os.replace(tmp,path)
        finally:Path(tmp).unlink(missing_ok=True)
    try:
        replace(json.dumps(config,indent=2).encode())
        resolved=json.loads(run("config","--format","json"))["services"]
        for name,row in expected.items():
            d=resolved[name]
            if d["image"]!=row["recovery_tag"] or d["pull_policy"]!="never" or d["environment"].get("AFTERGRID_RECOVERY_OFFLINE")!="1":
                raise ValueError("Resolved offline mode mismatch")
        run("up","-d","--no-build","--pull","never","--wait","--wait-timeout","120",timeout=180)
        for name,row in expected.items():
            cid=run("ps","-q",name)
            info=json.loads(assets.docker("container","inspect","--format","{{json .}}",cid))
            if info["Image"]!=row["image_id"] or "AFTERGRID_RECOVERY_OFFLINE=1" not in info["Config"]["Env"] or not info["State"]["Running"]:
                raise ValueError("Offline mode not confirmed")
    except Exception:
        replace(original)
        run("up","-d","--no-build","--pull","never","--wait","--wait-timeout","120",timeout=180)
        raise
    prep.private_write(root/"recovery-offline-activated.json",json.dumps({"format":1,"inventory_sha256":report["inventory_sha256"],
        "restricted_offline_administration":True,"complete_recovery":False}).encode())

def main():
    os.umask(0o077)
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="action",required=True)
    run=sub.add_parser("restore")
    run.add_argument("--repository",required=True,type=Path)
    run.add_argument("--module",action="append",choices=sorted(data.SOURCES),default=[])
    run.add_argument("--confirm-empty-replacement",action="store_true")
    backups=sub.add_parser("enable-backups")
    backups.add_argument("--confirm-working-copy-writes",action="store_true")
    finish=sub.add_parser("activate-offline")
    finish.add_argument("--confirm-native-checks",action="store_true")
    for cmd in (run,finish,backups):
        for name in ("root","assets","inventory"):cmd.add_argument("--"+name,required=True,type=Path)
    args=parser.parse_args()
    try:
        if args.action=="restore":
            if not args.confirm_empty_replacement:raise ValueError("Replacement-only confirmation required")
            password=getpass.getpass("Original Kopia repository password: ")
            recover(args.root,args.assets,args.repository,args.inventory,args.module,password)
            print("Guarded recovery staged and started. Verify native accounts and content before activate-offline. Not complete recovery.")
        elif args.action=="enable-backups":
            if not args.confirm_working_copy_writes:raise ValueError("Confirm writable independent copy")
            enable_backups(args.root,args.assets,args.inventory)
            print("Native working copy connected writable. Core-only guard remains active; verify a new managed backup after activation.")
        else:
            if not args.confirm_native_checks:raise ValueError("Explicit native account and content checks required")
            activate(args.root,args.assets,args.inventory)
            print("Restricted offline lifecycle mode enabled on localhost. Full recovery remains unverified; writable backups require prior opt-in and a new successful backup test.")
    except Exception:
        parser.exit(1,"Recovery stopped or refused. Inspect the replacement root, Docker and recovery receipts before retrying. No automatic cleanup of imported images or running services.\n")

if __name__=="__main__":
    main()
