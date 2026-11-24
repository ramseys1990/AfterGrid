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
import stat
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
    return inventory_core_records(json.loads(prep.read_private(inventory,65536)))


def inventory_core_records(value):
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

def capture_steps(modules):
    """Use existing reviewed API jobs; no new snapshot engine."""
    if len(modules)!=len(set(modules)) or any(m not in data.SOURCES for m in modules):
        raise ValueError("Choose distinct supported recovery modules")
    if "tak" in modules:
        raise ValueError("MicroTAK consistent capture is not yet supported")
    steps=[]
    for module in sorted(modules):
        for key,_,_ in data.SOURCES[module]:
            if key.startswith("application/"):
                base="/api/admin/modules/"+module
                steps.append((key,module,"snapshot","verify-snapshot",base+"/snapshot",base+"/verify-snapshot"))
            else:
                base="/api/admin/backups/content/"+module
                steps.append((key,module,"content-snapshot","content-verify",base+"/snapshot",base+"/verify"))
    # Capture worker state last so preceding application/core jobs are recorded.
    for key in ("core","worker"):
        base="/api/admin/backups/"+key
        steps.append((key,"kopia",key+"-snapshot",key+"-verify-snapshot",base+"/snapshot",base+"/verify-snapshot"))
    return steps


def capture_inventory(call,modules,*,job_timeout=7*60*60,progress=print):
    """Run fresh snapshot/verify pairs and pin their exact job IDs.

    Operator-exclusive maintenance, not an atomic snapshot or a global lock.
    Any observed unrelated worker activity refuses publication.
    """
    import time
    steps=capture_steps(modules)
    status=call("/api/status")
    if not status.get("admin") or status.get("recovery_core_only") or status.get("recovery_offline"):
        raise ValueError("Normal authenticated source installation required")
    if call("/api/admin/kopia/status").get("connection")!="connected":
        raise ValueError("Connect native Kopia before capture")
    def jobs():
        rows=call("/api/admin/jobs")
        if not isinstance(rows,list) or any(type(r.get("id")) is not int for r in rows):
            raise ValueError("Invalid job listing")
        return rows
    def idle(rows):
        if any(r.get("state") in {"queued","running"} for r in rows):
            raise ValueError("Worker is busy; exclusive maintenance required")
    rows=jobs()
    idle(rows)
    last=max((r["id"] for r in rows),default=0)
    def run(module,action,path):
        nonlocal last
        rows=jobs()
        idle(rows)
        if max((r["id"] for r in rows),default=0)!=last:
            raise ValueError("Concurrent worker activity detected")
        response=call(path,{"confirmed":True})
        ident=response.get("id")
        if type(ident) is not int or ident<=last:
            raise ValueError("Fresh job ID required")
        progress("Waiting for "+module+"/"+action+" (job "+str(ident)+")",flush=True)
        deadline=time.monotonic()+job_timeout
        while True:
            rows=jobs()
            new=[r for r in rows if r["id"]>last]
            if len(new)!=1 or new[0]["id"]!=ident:
                raise ValueError("Concurrent activity or missing capture job")
            row=new[0]
            if row.get("module")!=module or row.get("action")!=action:
                raise ValueError("Unexpected capture job")
            if any(r["id"]!=ident and r.get("state") in {"queued","running"} for r in rows):
                raise ValueError("Concurrent worker activity detected")
            if row.get("state")=="succeeded":
                if row.get("completed")!=row.get("total"):
                    raise ValueError("Incomplete capture job")
                last=ident
                return ident
            if row.get("state") not in {"queued","running"}:
                raise ValueError("Capture job failed or interrupted: "+module+"/"+action)
            if time.monotonic()>=deadline:
                raise ValueError("Capture job timed out; inspect existing job before retry")
            time.sleep(2)
    expected={}
    for key,module,action,verify,snapshot_path,verify_path in steps:
        expected[key]=(run(module,action,snapshot_path),run(module,verify,verify_path))
    manifest=run("kopia","recovery-manifest","/api/admin/backups/recovery-manifest")
    value=call("/api/admin/backups/recovery-manifest")
    if value.get("manifest_job")!=manifest:
        raise ValueError("Inventory is not from this capture")
    records=inventory_core_records(value)
    for module in modules:data.required_records(records,module)
    for key,(snapshot,verify) in expected.items():
        row=records.get(key,{})
        if row.get("snapshot_job")!=snapshot or row.get("verification_job")!=verify:
            raise ValueError("Inventory does not match fresh snapshot and verification jobs")
    rows=jobs()
    idle(rows)
    if max((r["id"] for r in rows),default=0)!=last:
        raise ValueError("Concurrent worker activity detected")
    return value


def canonical_inventory_digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":")).encode()).hexdigest()


def guarded_capture(call,modules,*,job_timeout=7*60*60,progress=print):
    capture_steps(modules)
    call("/api/admin/recovery-maintenance/begin",{"confirmed":True,"modules":modules})
    # A failure deliberately leaves maintenance active for inspection.
    value=capture_inventory(call,modules,job_timeout=job_timeout,progress=progress)
    sealed=call("/api/admin/recovery-maintenance/seal",{"confirmed":True})
    if sealed.get("phase")!="sealed" or sealed.get("inventory_sha256")!=canonical_inventory_digest(value):
        raise ValueError("Maintenance seal does not match verified inventory")
    return value


def capture_client(url,origin=None):
    """Authenticate only over loopback HTTP or verified HTTPS; no redirects."""
    import http.cookiejar
    import urllib.error
    import urllib.request
    from urllib.parse import urlsplit
    parsed=urlsplit(url)
    if (parsed.scheme not in {"http","https"} or not parsed.hostname or parsed.username is not None
        or parsed.password is not None or parsed.path not in ("","/") or parsed.query or parsed.fragment
        or (parsed.scheme=="http" and parsed.hostname not in {"127.0.0.1","localhost","::1"})):
        raise ValueError("Use a loopback HTTP or trusted HTTPS portal URL")
    base=parsed.scheme+"://"+parsed.netloc
    origin=origin or base
    origin_parts=urlsplit(origin)
    if (origin_parts.scheme not in {"http","https"} or not origin_parts.hostname
        or origin_parts.username is not None or origin_parts.password is not None
        or origin_parts.path or origin_parts.query or origin_parts.fragment):
        raise ValueError("Use the exact configured portal origin")
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):
            return None
    client=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect(),
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    def call(path,payload=None):
        request=urllib.request.Request(base+path,data=None if payload is None else json.dumps(payload).encode(),
            headers={"Origin":origin,"Content-Type":"application/json"})
        try:
            with client.open(request,timeout=30) as response:
                raw=response.read(8*1024*1024+1)
                if len(raw)>8*1024*1024:raise ValueError("Portal response too large")
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            raise ValueError("Portal refused "+path+" (HTTP "+str(exc.code)+")") from None
    return call


def repository_digest(path):
    """Stream a deterministic digest of all regular repository files."""
    path=assets.real_directory(path)
    data.safe_tree(path)
    digest=hashlib.sha256()
    count=0
    size=0
    for current,dirs,files in os.walk(path,followlinks=False):
        dirs.sort()
        for name in sorted(files):
            p=Path(current)/name
            info=p.lstat()
            if not stat.S_ISREG(info.st_mode):raise ValueError("Unexpected repository file")
            relative=p.relative_to(path).as_posix()
            record=[relative,info.st_size,assets.sha256_file(p)]
            digest.update(json.dumps(record,ensure_ascii=True,separators=(",",":")).encode()+b"\n")
            count+=1
            size+=info.st_size
    if not count:raise ValueError("Empty repository")
    return {"sha256":digest.hexdigest(),"files":count,"bytes":size}

def require_quiescent():
    # Inspect only AfterGrid-labelled containers, never stop anything here.
    raw=assets.docker("ps","--format",'{{.Label "com.docker.compose.project"}}')
    if any(name.startswith("aftergrid-") for name in raw.splitlines()):
        raise ValueError("Stop all AfterGrid services and external repository writers first")

def package_handoff(root,inventory_bytes,modules,required=False):
    marker=root/"data/core/recovery-maintenance.json"
    if not marker.exists() and not marker.is_symlink():
        if required:raise ValueError("Sealed recovery maintenance required")
        return None
    raw=prep.read_private(marker,8192)
    value=json.loads(raw)
    inventory=json.loads(inventory_bytes)
    if (value.get("format")!=1 or value.get("phase")!="sealed" or value.get("modules")!=sorted(modules)
        or value.get("inventory_sha256")!=canonical_inventory_digest(inventory)
        or value.get("manifest_job")!=inventory.get("manifest_job")):
        raise ValueError("Maintenance seal differs from selected recovery inventory")
    return raw


def validate_package_scope(captured,modules,acknowledge_blocked=False):
    if "kopia" not in captured or len(modules)!=len(set(modules)) or any(m not in data.SOURCES or m not in captured for m in modules):
        raise ValueError("Choose captured verified applications; Kopia must exist")
    blocked={m:data.BLOCKED_RECOVERY[m] for m in sorted(captured & data.BLOCKED_RECOVERY.keys())}
    if set(modules)&blocked.keys():
        raise ValueError("Selected module has an unaccepted recovery path")
    if blocked and not acknowledge_blocked:
        raise ValueError("Explicitly acknowledge excluded MicroTAK recovery before packaging")
    return blocked


def pack(root,inventory,destination,modules,password,*,require_sealed=False,acknowledge_blocked=False):
    """Bundle a quiescent source installation and verified independent captures."""
    if os.geteuid()!=0:raise ValueError("Root required")
    root=assets.real_directory(root)
    destination=install.validate_root(destination)
    if root in destination.parents or destination in root.parents:raise ValueError("Package must be outside installation")
    inventory=Path(inventory).absolute()
    inventory_bytes=prep.read_private(inventory,65536)
    handoff=package_handoff(root,inventory_bytes,modules,require_sealed)
    if not password or len(password)>1024:raise ValueError("Repository password required")
    require_quiescent()
    repository=assets.real_directory(root/"backups")
    # Reject unsupported selection or unacknowledged omission before archiving images.
    source_rows=assets.image_inventory()
    source_modules={r["service"] for r in source_rows if r["project"]!="aftergrid-core"}
    blocked=validate_package_scope(source_modules,modules,acknowledge_blocked)
    destination.mkdir(mode=0o700)
    try:
        # Parse exactly the bytes being packaged, not a second read of a mutable input.
        prep.private_write(destination/"inventory.json",inventory_bytes)
        records=core_records(destination/"inventory.json")
        value=assets.capture(root,destination/"assets")
        rows=assets.recovery_image_rows(value)
        captured={r["service"] for r in rows if r["project"]!="aftergrid-core"}
        if captured!=source_modules or validate_package_scope(captured,modules,acknowledge_blocked)!=blocked:
            raise ValueError("Source module inventory changed during capture")
        omitted=sorted(captured-{"kopia"}-set(modules))
        checks=[(key,source,records[key]["snapshot_id"]) for key,source in (("core",CORE_SOURCE),("worker",WORKER_SOURCE))]
        for m in modules:
            checks.extend((key,source,sid) for key,source,_,sid in data.required_records(records,m))
        before=repository_digest(repository)
        target=destination/"repository"
        target.mkdir(mode=0o700)
        subprocess.run(["cp","-a","--reflink=auto",str(repository)+"/.",str(target)],check=True,capture_output=True,timeout=6*60*60)
        require_quiescent()
        kopia=next(r for r in rows if r["project"]=="aftergrid-kopia")
        with tempfile.TemporaryDirectory(prefix=".verify-package-",dir=destination) as tmp:
            run=data.native_repository_command(kopia["image_id"],target,Path(tmp),password)
            native=data.native_manifest_rows(run)
            for _,source,sid in checks:data.exact_native_manifest(native,source,sid)
        require_quiescent()
        # Check both copies after native manifest inspection, immediately before publishing.
        if repository_digest(target)!=before or repository_digest(repository)!=before:
            raise ValueError("Repository changed during package assembly")
        require_quiescent()
        if package_handoff(root,inventory_bytes,modules,require_sealed)!=handoff:
            raise ValueError("Maintenance seal changed during package assembly")
        report={"format":1,"selected":sorted(modules),"omitted_captured":omitted,"blocked_recovery":blocked,
                "assets_manifest_sha256":assets.sha256_file(destination/"assets/assets-manifest.json"),
                "inventory_sha256":assets.sha256_file(destination/"inventory.json"),"repository":before,
                "checked_snapshots":{key:sid for key,_,sid in checks},
                "atomic":False,"complete_recovery":False}
        prep.private_write(destination/"package.json",json.dumps(report,indent=2).encode())
        return report
    except Exception:
        # Only this exclusively created output tree; never source data.
        shutil.rmtree(destination)
        raise

def source_containers(root):
    """Identify exact reviewed containers bound to this source installation."""
    root=assets.real_directory(root)
    assets.local_docker()
    projects={"aftergrid-core":{"core","worker"},**{"aftergrid-"+m:{m} for m in assets.MODULES}}
    result={}
    raw=assets.docker("ps","--all","--no-trunc","--filter","label=com.docker.compose.project",
                      "--format",'{{json .ID}} {{json (.Label "com.docker.compose.project")}}')
    for line in raw.splitlines():
        decoder=json.JSONDecoder()
        cid,end=decoder.raw_decode(line)
        project=json.loads(line[end:].strip())
        if not project.startswith("aftergrid-"):continue
        if project not in projects or not re.fullmatch(r"[a-f0-9]{64}",cid):
            raise ValueError("Unexpected AfterGrid project or container")
        obj=json.loads(assets.docker("container","inspect","--format","{{json .}}",cid))
        labels=obj["Config"]["Labels"]
        service=labels.get("com.docker.compose.service")
        state=obj["State"]["Status"]
        if (obj["Id"]!=cid or labels.get("com.docker.compose.project")!=project
            or service not in projects[project] or service in result
            or str(labels.get("com.docker.compose.oneoff","false")).lower()=="true"
            or state not in {"running","exited","created"}
            or not assets.IMAGE_ID.fullmatch(obj["Image"])):
            raise ValueError("Unexpected or ambiguous AfterGrid container")
        binds={m["Destination"]:Path(m["Source"]) for m in obj["Mounts"] if m["Type"]=="bind"}
        # Every reviewed module has at least one installation bind. The worker
        # also has the known Docker socket; never accept arbitrary host mounts.
        expected={"core":("/data",root/"data/core"),"worker":("/modules",root/"modules"),
                  "kopia":("/repository",root/"backups")}.get(service)
        if expected and binds.get(expected[0])!=expected[1]:raise ValueError("Source root mismatch")
        local=[p for dest,p in binds.items() if not (service=="worker" and dest=="/var/run/docker.sock" and p==Path("/var/run/docker.sock"))]
        if not local or any(root not in p.parents or ".." in p.parts for p in local):
            raise ValueError("Container bind outside source root")
        result[service]={"id":cid,"image_id":obj["Image"],"project":project,"state":state}
    if not {"core","worker","kopia"}<=result.keys():raise ValueError("Core, worker and Kopia containers required")
    return result


def source_identity(rows):
    return {k:{n:v[n] for n in ("id","image_id","project")} for k,v in rows.items()}


def resume_source(root):
    """Restart only containers recorded as running; never recreate or pull."""
    if os.geteuid()!=0:raise ValueError("Root required")
    root=assets.real_directory(root)
    journal=root/"recovery-source-restart.json"
    saved=json.loads(prep.read_private(journal,65536))
    if saved.get("format")!=1 or saved.get("root")!=str(root):
        raise ValueError("Invalid source restart journal")
    expected=saved["containers"]
    current=source_containers(root)
    if source_identity(current)!=source_identity(expected):raise ValueError("Source container identities changed; inspect manually")
    if any(row["state"]!="running" and current[k]["state"]=="running" for k,row in expected.items()):
        raise ValueError("Previously inactive container is running; inspect manually")
    order=["kopia",*sorted(set(expected)-{"kopia","core","worker"}),"worker","core"]
    for name in order:
        row=expected[name]
        if row["state"]=="running" and current[name]["state"]!="running":
            assets.docker("start",row["id"],timeout=90)
    final=source_containers(root)
    if source_identity(final)!=source_identity(expected) or any(
        (row["state"]=="running")!=(final[name]["state"]=="running") for name,row in expected.items()):
        raise ValueError("Prior source running state not restored")
    journal.unlink()


def pack_and_resume(root,inventory,destination,modules,password,*,acknowledge_blocked=False):
    """Host-only sealed handoff. Preserve exact source container running state."""
    if os.geteuid()!=0:raise ValueError("Root required")
    root=assets.real_directory(root)
    destination=install.validate_root(destination)
    if root in destination.parents or destination in root.parents:raise ValueError("Package must be outside installation")
    raw=prep.read_private(inventory,65536)
    package_handoff(root,raw,modules,True)
    records=inventory_core_records(json.loads(raw))
    for module in modules:data.required_records(records,module)
    if not password or len(password)>1024:raise ValueError("Repository password required")
    rows=source_containers(root)
    validate_package_scope(set(rows)-{"core","worker"},modules,acknowledge_blocked)
    if any(rows[k]["state"]!="running" for k in ("core","worker","kopia")):
        raise ValueError("Source core, worker and Kopia must be running before handoff")
    journal=root/"recovery-source-restart.json"
    prep.private_write(journal,json.dumps({"format":1,"root":str(root),"containers":rows},indent=2).encode())
    try:
        # Stop portal and worker first; sealed admission has already checked
        # idle work. Then stop app containers and the repository last.
        for name in ["core","worker",*sorted(set(rows)-{"core","worker","kopia"}),"kopia"]:
            if rows[name]["state"]=="running":
                current=source_containers(root)
                if source_identity(current)!=source_identity(rows):raise ValueError("Source container identities changed")
                if current[name]["state"]!="running":raise ValueError("Source running state changed")
                assets.docker("stop","--time","60",rows[name]["id"],timeout=90)
        require_quiescent()
        if source_identity(source_containers(root))!=source_identity(rows):raise ValueError("Source container identities changed")
        report=pack(root,inventory,destination,modules,password,require_sealed=True,acknowledge_blocked=acknowledge_blocked)
        if verify_package(destination)!=report:raise ValueError("Package verification mismatch")
        return report
    finally:
        # On ordinary failure, restore prior running state where identities
        # still match. If restart fails, journal remains for explicit resume.
        # Maintenance remains sealed until the administrator releases it.
        resume_source(root)


def create_package(call,root,destination,modules,password,*,acknowledge_blocked=False,job_timeout=7*60*60):
    """Fresh guarded capture -> sealed host package -> prior running state."""
    if os.geteuid()!=0:raise ValueError("Root required")
    root=assets.real_directory(root)
    destination=install.validate_root(destination)
    if root in destination.parents or destination in root.parents:raise ValueError("Package must be outside installation")
    if (root/"recovery-source-restart.json").exists() or (root/"recovery-source-restart.json").is_symlink():
        raise ValueError("Existing restart journal; inspect before new capture")
    capture_steps(modules)
    rows=source_containers(root)
    validate_package_scope(set(rows)-{"core","worker"},modules,acknowledge_blocked)
    if any(rows[k]["state"]!="running" for k in ("core","worker","kopia")):
        raise ValueError("Source core, worker and Kopia must be running")
    if not password or len(password)>1024:raise ValueError("Repository password required")
    # Use a private temporary inventory on the destination filesystem. The
    # published package contains its exact bytes; on failure the persistent
    # portal seal and native worker inventory remain available for inspection.
    with tempfile.TemporaryDirectory(prefix=".aftergrid-capture-",dir=destination.parent) as tmp:
        value=guarded_capture(call,modules,job_timeout=job_timeout)
        inventory=Path(tmp)/"inventory.json"
        payload=json.dumps(value,indent=2).encode()
        if len(payload)>65536:raise ValueError("Recovery inventory too large")
        prep.private_write(inventory,payload)
        if source_containers(root)!=rows:raise ValueError("Source container state changed during capture")
        return pack_and_resume(root,inventory,destination,modules,password,acknowledge_blocked=acknowledge_blocked)


def verify_package(directory):
    directory=assets.real_directory(directory)
    if {p.name for p in directory.iterdir()}!={"assets","inventory.json","repository","package.json"}:
        raise ValueError("Unexpected package file set")
    report=json.loads(prep.read_private(directory/"package.json",65536))
    if report.get("format")!=1 or report.get("atomic") is not False or report.get("complete_recovery") is not False:
        raise ValueError("Unsupported package format")
    value=assets.verify(directory/"assets")
    if (assets.sha256_file(directory/"assets/assets-manifest.json")!=report["assets_manifest_sha256"]
        or assets.sha256_file(directory/"inventory.json")!=report["inventory_sha256"]
        or repository_digest(directory/"repository")!=report["repository"]):
        raise ValueError("Package checksum mismatch")
    records=core_records(directory/"inventory.json")
    selected=report["selected"]
    captured={r["service"] for r in assets.recovery_image_rows(value) if r["project"]!="aftergrid-core"}
    if not isinstance(selected,list) or len(selected)!=len(set(selected)) or "kopia" not in captured or any(m not in captured or m not in data.SOURCES for m in selected):
        raise ValueError("Invalid package module selection")
    if report["omitted_captured"]!=sorted(captured-{"kopia"}-set(selected)):raise ValueError("Package selection mismatch")
    blocked=validate_package_scope(captured,selected,True)
    if "blocked_recovery" in report and report["blocked_recovery"]!=blocked:raise ValueError("Package blocked recovery scope mismatch")
    checks={k:records[k]["snapshot_id"] for k in ("core","worker")}
    for m in selected:checks.update({k:sid for k,_,_,sid in data.required_records(records,m)})
    if checks!=report["checked_snapshots"]:raise ValueError("Package snapshot selection mismatch")
    return report

def restore_package(root,directory,password):
    directory=assets.real_directory(directory)
    root=install.validate_root(root)
    if root==directory or directory in root.parents or root in directory.parents:
        raise ValueError("Replacement root must be outside the recovery package")
    report=verify_package(directory)
    return recover(root,directory/"assets",directory/"repository",directory/"inventory.json",report["selected"],password)


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
    capture=sub.add_parser("capture-inventory")
    capture.add_argument("--url",required=True)
    capture.add_argument("--origin",help="Exact configured portal origin, if different from URL")
    capture.add_argument("--username",default="admin")
    capture.add_argument("--destination",required=True,type=Path)
    capture.add_argument("--module",action="append",choices=sorted(data.SOURCES),default=[])
    capture.add_argument("--core-only",action="store_true")
    capture.add_argument("--confirm-maintenance",action="store_true")
    bundle=sub.add_parser("pack")
    bundle.add_argument("--root",required=True,type=Path)
    bundle.add_argument("--inventory",required=True,type=Path)
    bundle.add_argument("--destination",required=True,type=Path)
    bundle.add_argument("--module",action="append",choices=sorted(data.SOURCES),default=[])
    bundle.add_argument("--confirm-quiescent",action="store_true")
    bundle.add_argument("--require-sealed",action="store_true")
    bundle.add_argument("--acknowledge-blocked",action="store_true",help="Acknowledge that captured MicroTAK data is excluded from recovery")
    combined=sub.add_parser("create-package")
    for name in ("root","destination"):combined.add_argument("--"+name,required=True,type=Path)
    combined.add_argument("--url",required=True)
    combined.add_argument("--origin")
    combined.add_argument("--username",default="admin")
    combined.add_argument("--module",action="append",choices=sorted(data.SOURCES),default=[])
    combined.add_argument("--core-only",action="store_true")
    combined.add_argument("--confirm-maintenance-downtime",action="store_true")
    combined.add_argument("--acknowledge-blocked",action="store_true")
    handoff=sub.add_parser("pack-and-resume")
    for name in ("root","inventory","destination"):handoff.add_argument("--"+name,required=True,type=Path)
    handoff.add_argument("--module",action="append",choices=sorted(data.SOURCES),default=[])
    handoff.add_argument("--confirm-maintenance-downtime",action="store_true")
    handoff.add_argument("--acknowledge-blocked",action="store_true")
    resume=sub.add_parser("resume-source")
    resume.add_argument("--root",required=True,type=Path)
    resume.add_argument("--confirm-resume",action="store_true")
    release=sub.add_parser("release-maintenance")
    release.add_argument("--url",required=True)
    release.add_argument("--origin")
    release.add_argument("--username",default="admin")
    release.add_argument("--confirm-release",action="store_true")
    verify=sub.add_parser("verify-package")
    verify.add_argument("--package",required=True,type=Path)
    restore_pack=sub.add_parser("restore-package")
    restore_pack.add_argument("--package",required=True,type=Path)
    restore_pack.add_argument("--root",required=True,type=Path)
    restore_pack.add_argument("--confirm-empty-replacement",action="store_true")
    backups=sub.add_parser("enable-backups")
    backups.add_argument("--confirm-working-copy-writes",action="store_true")
    finish=sub.add_parser("activate-offline")
    finish.add_argument("--confirm-native-checks",action="store_true")
    for cmd in (run,finish,backups):
        for name in ("root","assets","inventory"):cmd.add_argument("--"+name,required=True,type=Path)
    args=parser.parse_args()
    try:
        if args.action=="capture-inventory":
            if not args.confirm_maintenance or bool(args.module)==args.core_only:
                raise ValueError("Confirm exclusive maintenance and explicitly select modules or core-only")
            capture_steps(args.module)
            destination=install.validate_root(args.destination)
            call=capture_client(args.url,args.origin)
            call("/api/login",{"username":args.username,"password":getpass.getpass("AfterGrid administrator password: ")})
            try:
                value=guarded_capture(call,args.module)
                payload=json.dumps(value,indent=2).encode()
                if len(payload)>65536:raise ValueError("Recovery inventory too large")
                prep.private_write(destination,payload)
            finally:
                try:call("/api/logout",{})
                except Exception:print("Portal logout not confirmed; session will expire.",flush=True)
            print("Fresh verified inventory sealed. Stop source services before pack --require-sealed. Maintenance remains active until explicit release.")
        elif args.action=="release-maintenance":
            if not args.confirm_release:raise ValueError("Confirm maintenance release after inspecting jobs and source state")
            call=capture_client(args.url,args.origin)
            call("/api/login",{"username":args.username,"password":getpass.getpass("AfterGrid administrator password: ")})
            try:call("/api/admin/recovery-maintenance/release",{"confirmed":True})
            finally:
                try:call("/api/logout",{})
                except Exception:print("Portal logout not confirmed; session will expire.",flush=True)
            print("Recovery maintenance released.")
        elif args.action=="create-package":
            if not args.confirm_maintenance_downtime or bool(args.module)==args.core_only:
                raise ValueError("Confirm downtime and explicitly select modules or core-only")
            capture_steps(args.module)
            call=capture_client(args.url,args.origin)
            call("/api/login",{"username":args.username,"password":getpass.getpass("AfterGrid administrator password: ")})
            try:
                report=create_package(call,args.root,args.destination,args.module,getpass.getpass("Original Kopia repository password: "),acknowledge_blocked=args.acknowledge_blocked)
                print("Package verified; original container running state restored. Inspect native readiness and explicitly release maintenance.")
                print("Omitted captured modules: "+(", ".join(report["omitted_captured"]) or "none"))
            finally:
                try:call("/api/logout",{})
                except Exception:print("Portal logout not confirmed; session will expire.",flush=True)
        elif args.action=="pack-and-resume":
            if not args.confirm_maintenance_downtime:raise ValueError("Confirm source service downtime")
            report=pack_and_resume(args.root,args.inventory,args.destination,args.module,getpass.getpass("Original Kopia repository password: "),acknowledge_blocked=args.acknowledge_blocked)
            print("Package verified; original container running state restored. Inspect native readiness and explicitly release maintenance.")
            print("Omitted captured modules: "+(", ".join(report["omitted_captured"]) or "none"))
        elif args.action=="resume-source":
            if not args.confirm_resume:raise ValueError("Confirm source restart journal and source inspection")
            resume_source(args.root)
            print("Original container running state restored. Inspect native readiness before releasing maintenance.")
        elif args.action=="pack":
            if not args.confirm_quiescent:raise ValueError("Confirm source maintenance and quiescent repository")
            report=pack(args.root,args.inventory,args.destination,args.module,getpass.getpass("Original Kopia repository password: "),require_sealed=args.require_sealed,acknowledge_blocked=args.acknowledge_blocked)
            print("Package created. Omitted captured modules: "+(", ".join(report["omitted_captured"]) or "none")+". Independent snapshots, not atomic recovery.")
            if report["blocked_recovery"]:print("Excluded unsupported recovery: "+", ".join(report["blocked_recovery"]))
        elif args.action=="verify-package":
            verify_package(args.package)
            print("Recovery package file checksums and selected inventory verified; native recovery remains separate.")
        elif args.action=="restore-package":
            if not args.confirm_empty_replacement:raise ValueError("Replacement-only confirmation required")
            restore_package(args.root,args.package,getpass.getpass("Original Kopia repository password: "))
            print("Guarded package recovery started. Native acceptance and activation remain separate.")
        elif args.action=="restore":
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
