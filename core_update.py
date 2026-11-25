#!/usr/bin/env python3
"""Prepare an exact, core-only update candidate without activating it."""
import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
import time
import uuid
from pathlib import Path, PurePosixPath

import recovery_assets as assets

ROOT=Path("/opt/aftergrid")
STAGING=Path("/opt/aftergrid-updates")
SOURCE_LIMIT=128*1024*1024
FILE_LIMIT=16*1024*1024
SHA=re.compile(r"[a-f0-9]{64}")
COMMIT=re.compile(r"[a-f0-9]{40}")
IMAGE=re.compile(r"sha256:[a-f0-9]{64}")


def extract_candidate(archive, destination, commit, checksum):
    if not COMMIT.fullmatch(commit) or not SHA.fullmatch(checksum):
        raise ValueError("Exact commit and reviewed SHA-256 required")
    if archive.is_symlink() or not archive.is_file() or archive.stat().st_size>SOURCE_LIMIT:
        raise ValueError("Invalid or oversized source archive")
    destination.mkdir(mode=0o700)
    total=0
    seen=set()
    # Hash and extract from the same opened descriptor; do not extract links,
    # special files, traversal paths, duplicate entries or mutable runtime data.
    with archive.open("rb") as stream:
        if hashlib.file_digest(stream,"sha256").hexdigest()!=checksum:
            raise ValueError("Source archive checksum mismatch")
        stream.seek(0)
        with tarfile.open(fileobj=stream,mode="r:gz") as tar:
            for number,member in enumerate(tar):
                if number>=10000:raise ValueError("Too many source entries")
                path=PurePosixPath(member.name)
                if (path.is_absolute() or ".." in path.parts or not path.parts
                    or path.parts[0].lower()!="aftergrid-"+commit):
                    raise ValueError("Unexpected source archive path")
                if len(path.parts)==1:
                    if not member.isdir():raise ValueError("Invalid archive root")
                    continue
                relative=PurePosixPath(*path.parts[1:])
                if relative.parts[0] not in {"core","worker","modules","compose.yaml"}:continue
                if relative in seen:raise ValueError("Duplicate source path")
                seen.add(relative)
                target=destination.joinpath(*relative.parts)
                if member.isdir():
                    target.mkdir(parents=True,exist_ok=True)
                    continue
                if not member.isfile() or not 0<=member.size<=FILE_LIMIT:
                    raise ValueError("Unsafe candidate source entry")
                total+=member.size
                if total>SOURCE_LIMIT:raise ValueError("Candidate source exceeds size limit")
                target.parent.mkdir(parents=True,exist_ok=True)
                with tar.extractfile(member) as src,target.open("xb") as dst:
                    shutil.copyfileobj(src,dst)
                target.chmod(0o700 if member.mode&0o111 else 0o600)
    for name in ("compose.yaml","core/Dockerfile","worker/Dockerfile"):
        if not (destination/name).is_file():raise ValueError("Incomplete core candidate")


def tree_hashes(root):
    assets.real_directory(root)
    result={}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():raise ValueError("Unexpected symlink in reviewed source")
        if path.is_dir():continue
        if not path.is_file() or path.stat().st_size>FILE_LIMIT:
            raise ValueError("Unexpected reviewed source file")
        result[path.relative_to(root).as_posix()]={
            "sha256":assets.sha256_file(path),"executable":bool(path.stat().st_mode&0o111)}
    return result


def check_scope(root,candidate):
    # This pilot replaces only core/worker images; no changes to Compose
    # topology, modules, application versions, or existing bind mounts.
    for path in (root/"compose.yaml",root/".env"):
        if path.is_symlink() or not path.is_file():raise ValueError("Invalid installed configuration")
    if (root/"compose.yaml").read_bytes()!=(candidate/"compose.yaml").read_bytes():
        raise ValueError("Compose changes require a separately reviewed upgrade")
    if tree_hashes(root/"modules")!=tree_hashes(candidate/"modules"):
        raise ValueError("Module changes require a separately reviewed upgrade")
    return {"compose_sha256":assets.sha256_file(root/"compose.yaml"),
            "env_sha256":assets.sha256_file(root/".env"),
            "modules_sha256":hashlib.sha256(json.dumps(tree_hashes(root/"modules"),sort_keys=True).encode()).hexdigest()}


def live_core(root):
    result={}
    rows=assets.docker("ps","-a","-q","--no-trunc","--filter","label=com.docker.compose.project=aftergrid-core").splitlines()
    for cid in rows:
        if not SHA.fullmatch(cid):raise ValueError("Invalid container identity")
        fmt='{{json .Config.Labels}}|{{json .Image}}|{{json .State.Status}}|{{json .State.Health.Status}}'
        fields=assets.docker("container","inspect","--format",fmt,cid).split("|")
        if len(fields)!=4:raise ValueError("Unexpected core inspection response")
        labels,image,state,health=map(json.loads,fields)
        name=labels.get("com.docker.compose.service")
        if (name not in {"core","worker"} or name in result or not IMAGE.fullmatch(image)
            or state!="running" or health!="healthy"
            or labels.get("com.docker.compose.project")!="aftergrid-core"
            or labels.get("com.docker.compose.project.working_dir")!=str(root)
            or labels.get("com.docker.compose.project.config_files")!=str(root/"compose.yaml")):
            raise ValueError("Expected healthy normal AfterGrid core and worker")
        result[name]={"container":cid,"image":image}
    if set(result)!={"core","worker"}:raise ValueError("Both core services must be healthy")
    return result


def build_candidate(source, commit, suffix):
    result={}
    env={"PATH":os.environ["PATH"],"HOME":"/root","DOCKER_HOST":"unix:///var/run/docker.sock"}
    for name in ("core","worker"):
        tag="aftergrid-candidate/"+name+":"+commit+"-"+suffix
        subprocess.run(["docker","build","--tag",tag,str(source/name)],
                       env=env,check=True,timeout=1800)
        image=assets.docker("image","inspect","--format","{{.Id}}",tag)
        if not IMAGE.fullmatch(image):raise ValueError("Candidate image identity unavailable")
        result[name]={"tag":tag,"image":image}
    return result


def prepare(root, staging, archive, commit, checksum):
    root=assets.real_directory(root)
    if (root/".install-pending").exists() or (root/"recovery-install-plan.json").exists():
        raise ValueError("Finish installation or recovery before preparing an update")
    if not COMMIT.fullmatch(commit) or not SHA.fullmatch(checksum):
        raise ValueError("Exact commit and reviewed SHA-256 required")
    platform=assets.local_docker()
    prior=live_core(root)
    staging.mkdir(mode=0o700,exist_ok=True)
    staging=assets.real_directory(staging)
    info=staging.stat()
    if info.st_uid!=os.geteuid() or stat.S_IMODE(info.st_mode)!=0o700:
        raise ValueError("Update staging must be privately owned")
    if staging==root or root in staging.parents:raise ValueError("Staging must be outside the installation")
    suffix=uuid.uuid4().hex[:12]
    destination=staging/(commit+"-"+suffix)
    stage=Path(tempfile.mkdtemp(prefix=".prepare-",dir=staging))
    try:
        source=stage/"source"
        extract_candidate(archive,source,commit,checksum)
        before=check_scope(root,source)
        candidate=build_candidate(source,commit,suffix)
        if live_core(root)!=prior or check_scope(root,source)!=before or assets.local_docker()!=platform:
            raise ValueError("Installed core changed during preparation")
        plan={"format":1,"commit":commit,"archive_sha256":checksum,"platform":platform,
              "root":str(root),"previous":prior,"candidate":candidate,"configuration":before,
              "prepared_at":int(time.time()),"activated":False,"rollback_ready":False}
        with (stage/"candidate.json").open("x") as out:json.dump(plan,out,indent=2)
        (stage/"candidate.json").chmod(0o600)
        stage.rename(destination)
        return destination
    finally:
        if stage.exists():shutil.rmtree(stage)


def read_json_private(path, limit=65536):
    info=path.lstat()
    if not stat.S_ISREG(info.st_mode) or not 0<info.st_size<=limit or info.st_mode&0o077:
        raise ValueError("Invalid private update or maintenance evidence")
    return json.loads(path.read_text())


def validate_backup_evidence(plan, seal, inventory, now):
    if (seal.get("format")!=1 or seal.get("phase")!="sealed" or seal.get("modules")!=[]
        or inventory.get("format")!=1 or seal.get("manifest_job")!=inventory.get("manifest_job")):
        raise ValueError("Seal a core-only recovery maintenance capture first")
    checksum=hashlib.sha256(json.dumps(inventory,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    if seal.get("inventory_sha256")!=checksum:
        raise ValueError("Sealed recovery inventory changed")
    stamp=inventory.get("created")
    prepared=plan.get("prepared_at")
    manifest=inventory.get("manifest_job")
    if (type(stamp) is not int or type(prepared) is not int or type(manifest) is not int
        or not prepared<=stamp<=now or now-stamp>1800):
        raise ValueError("Fresh recovery inventory required after candidate preparation")
    rows=inventory.get("records")
    if not isinstance(rows,list):raise ValueError("Invalid recovery records")
    result={}
    for key in ("core","worker"):
        matches=[row for row in rows if isinstance(row,dict) and row.get("key")==key]
        if len(matches)!=1:raise ValueError("Missing or duplicate recovery source")
        row=matches[0]
        source_job,verify_job,captured=(row.get(k) for k in ("snapshot_job","verification_job","captured_at"))
        sid=row.get("snapshot_id")
        if (any(type(n) is not int for n in (source_job,verify_job,captured))
            or not 0<source_job<verify_job<manifest or not prepared<=captured<=stamp
            or not isinstance(sid,str) or not re.fullmatch(r"[a-f0-9]{32,64}",sid)
            or row.get("verification")!="isolated" or row.get("repository_status")!="present"
            or row.get("aftergrid_pinned") is not True):
            raise ValueError("Fresh protected and restore-verified "+key+" snapshot required")
        proof={"snapshot_job":source_job,"verification_job":verify_job,"snapshot_id":sid}
        if key=="core" and row.get("content_metadata_included") is not True:
            raise ValueError("Core content metadata coverage required")
        if key=="worker":
            digest=row.get("envelope_sha256")
            if not isinstance(digest,str) or not SHA.fullmatch(digest):raise ValueError("Worker export digest required")
            proof["envelope_sha256"]=digest
        result[key]=proof
    return result


# Fixed read-only program uses the already installed worker's native Kopia
# manifest reader and existing persistent job evidence; no new remote API.
LIVE_EVIDENCE=r"""
import json
import sys
import worker as w
if w.RECOVERY_CORE_ONLY or w.RECOVERY_OFFLINE:
    raise RuntimeError("Normal operation required")
inventory=w.load_recovery_manifest()
if w.kopia_status()["connection"]!="connected":
    raise RuntimeError("Repository unavailable")
with w.db() as con:
    if con.execute("SELECT 1 FROM jobs WHERE state IN ('queued','running') LIMIT 1").fetchone():
        raise RuntimeError("Worker busy")
    if con.execute("SELECT max(id) FROM jobs").fetchone()[0]!=inventory["manifest_job"]:
        raise RuntimeError("Inventory is not the last worker job")
    for key in ("core","worker"):
        row=next(r for r in inventory["records"] if r["key"]==key)
        if not con.execute("SELECT 1 FROM protected_snapshots WHERE job=?",(row["snapshot_job"],)).fetchone():
            raise RuntimeError("Capture was not protected at creation")
        if w.managed_snapshot_record(key,row["snapshot_job"])[1]!=row["snapshot_id"]:
            raise RuntimeError("Snapshot identity changed")
        proof=con.execute("SELECT module,action,state,log FROM jobs WHERE id=?",(row["verification_job"],)).fetchone()
        if not proof or (proof["module"],proof["action"],proof["state"])!=("kopia",key+"-verify-snapshot","succeeded") or "Snapshot "+row["snapshot_id"]+" restored;" not in proof["log"]:
            raise RuntimeError("Exact verification unavailable")
        if key=="worker" and w.worker_export_checksum(row["snapshot_job"])!=row["envelope_sha256"]:
            raise RuntimeError("Worker export digest changed")
        _,stats=w.read_snapshot_manifest(w.CORE_SNAPSHOT_SOURCE if key=="core" else w.WORKER_EXPORT_SOURCE,row["snapshot_id"])
        if stats.get("aftergrid_pinned") is not True:
            raise RuntimeError("Native pin missing")
print(json.dumps(inventory))
"""


def live_backup_inventory(worker_id):
    if not SHA.fullmatch(worker_id):raise ValueError("Invalid worker container")
    raw=assets.docker("exec",worker_id,"python3","-c",LIVE_EVIDENCE,timeout=130)
    if len(raw)>65536:raise ValueError("Oversized recovery inventory")
    return json.loads(raw)


def check_backups(root, candidate):
    root=assets.real_directory(root)
    candidate=assets.real_directory(candidate)
    plan=read_json_private(candidate/"candidate.json")
    if plan.get("format")!=1 or plan.get("root")!=str(root) or plan.get("activated") is not False:
        raise ValueError("Invalid candidate")
    before=live_core(root)
    if before!=plan["previous"] or check_scope(root,candidate/"source")!=plan["configuration"] or assets.local_docker()!=plan["platform"]:
        raise ValueError("Installed configuration or core identity changed")
    marker=root/"data/core/recovery-maintenance.json"
    seal=read_json_private(marker,8192)
    inventory=live_backup_inventory(before["worker"]["container"])
    proof=validate_backup_evidence(plan,seal,inventory,int(time.time()))
    if read_json_private(marker,8192)!=seal or live_core(root)!=before:
        raise ValueError("Maintenance or core changed during evidence check")
    # Advisory only: a seal can subsequently be released. Activation must
    # repeat this check under a durable admission boundary.
    return {"backup_evidence_checked":True,"manifest_job":inventory["manifest_job"],
            "inventory_sha256":seal["inventory_sha256"],"sources":proof,
            "activation_enabled":False,"rollback_ready":False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive",type=Path,nargs="?",help="Local reviewed GitHub commit tar.gz")
    parser.add_argument("--commit")
    parser.add_argument("--sha256",help="Independently reviewed archive SHA-256")
    parser.add_argument("--check-backups",type=Path,metavar="CANDIDATE",help="Read-only live recovery evidence check")
    args=parser.parse_args()
    if os.geteuid()!=0:parser.error("Run as root on the installed Linux guest")
    if Path("/etc/pve").exists() or shutil.which("pveversion"):parser.error("Do not run on the Proxmox hypervisor")
    try:
        if args.check_backups is not None:
            if any((args.archive,args.commit,args.sha256)):parser.error("Use check-backups separately")
            print(json.dumps(check_backups(ROOT,args.check_backups),indent=2))
            return
        if not all((args.archive,args.commit,args.sha256)):parser.error("Archive, exact commit and checksum required")
        destination=prepare(ROOT,STAGING,args.archive,args.commit,args.sha256)
    except (OSError,ValueError,TypeError,KeyError,subprocess.SubprocessError,tarfile.TarError) as exc:
        parser.exit(1,"Core update preparation failed: "+str(exc)+"\n")
    print("Candidate prepared:",destination)
    print("No live containers replaced. Activation and rollback are not yet enabled.")


if __name__=="__main__":main()
