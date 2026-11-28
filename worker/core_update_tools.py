#!/usr/bin/env python3
"""Prepare exact core updates and execute only separately released candidates."""
import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
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

# Compiled-in release policy. A separately reviewed release must supply both
# exact archive and source digests; neither an environment variable nor a
# browser-provided checksum can authorize a release.
PRODUCTION_EXECUTION_ENABLED=False
APPROVED_CORE_RELEASES={}


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
                # Docker COPY preserves source modes. These are reviewed build
                # inputs, not runtime secrets; the unprivileged core must read
                # them in the resulting image. Keep only the executable bit.
                target.chmod(0o755 if member.mode&0o111 else 0o644)
    # Include implicit parents and ignore the caller's restrictive umask.
    # The enclosing source root stays private (0700) on the build host.
    for directory in destination.rglob("*"):
        if directory.is_dir():directory.chmod(0o755)
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


def live_core(root,override=None):
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
            or labels.get("com.docker.compose.project.config_files")!=(str(root/"compose.yaml")+(","+str(override) if override else ""))):
            raise ValueError("Expected healthy normal AfterGrid core and worker")
        result[name]={"container":cid,"image":image}
    if set(result)!={"core","worker"}:raise ValueError("Both core services must be healthy")
    return result


def build_candidate(source, commit, suffix):
    if not COMMIT.fullmatch(commit) or not re.fullmatch(r"[a-f0-9]{12}",suffix):
        raise ValueError("Exact commit and private candidate suffix required")
    result={}
    # The preparation container is read-only except for its existing /tmp
    # tmpfs. Docker/Buildx write client metadata even for local builds; keep
    # that state private and temporary rather than granting /root writes.
    with tempfile.TemporaryDirectory(prefix="aftergrid-docker-") as config:
        env={"PATH":os.environ["PATH"],"HOME":"/root",
             "DOCKER_CONFIG":config,"DOCKER_HOST":"unix:///var/run/docker.sock"}
        for name in ("core","worker"):
            tag="aftergrid-candidate/"+name+":"+commit+"-"+suffix
            labels={"org.opencontainers.image.revision":commit,
                    "org.opencontainers.image.source":"https://github.com/ramseys1990/AfterGrid",
                    "org.aftergrid.component":name}
            label_args=[arg for key,value in labels.items() for arg in ("--label",key+"="+value)]
            subprocess.run(["docker","build",*label_args,"--tag",tag,str(source/name)],
                           env=env,check=True,timeout=1800)
            image=assets.docker("image","inspect","--format","{{.Id}}",tag)
            if not IMAGE.fullmatch(image):raise ValueError("Candidate image identity unavailable")
            actual=json.loads(assets.docker("image","inspect","--format","{{json .Config.Labels}}",image))
            if not isinstance(actual,dict) or any(actual.get(key)!=value for key,value in labels.items()):
                raise ValueError("Built candidate source metadata mismatch")
            result[name]={"tag":tag,"image":image}
    return result


def candidate_source_digest(source):
    # Bind the reviewed build context to the plan, not merely the unchanged
    # module catalog. This does not attest that a Docker build is reproducible.
    trees={name:tree_hashes(source/name) for name in ("core","worker","modules")}
    trees["compose_sha256"]=assets.sha256_file(source/"compose.yaml")
    return hashlib.sha256(json.dumps(trees,sort_keys=True,separators=(",",":")).encode()).hexdigest()


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
        source_digest=candidate_source_digest(source)
        candidate=build_candidate(source,commit,suffix)
        if candidate_source_digest(source)!=source_digest:
            raise ValueError("Candidate source changed during build")
        if live_core(root)!=prior or check_scope(root,source)!=before or assets.local_docker()!=platform:
            raise ValueError("Installed core changed during preparation")
        plan={"format":1,"commit":commit,"archive_sha256":checksum,"platform":platform,
              "root":str(root),"previous":prior,"candidate":candidate,"configuration":before,
              "source_sha256":source_digest,"prepared_at":int(time.time()),"activated":False,"rollback_ready":False}
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
    if (seal.get("format")!=1 or seal.get("phase") not in {"sealed","updating"} or seal.get("modules")!=[]
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


def check_candidate_source(candidate,plan):
    if plan.get("source_sha256")!=candidate_source_digest(candidate/"source"):
        raise ValueError("Candidate source digest changed or unavailable; prepare again")


def check_backups(root, candidate):
    root=assets.real_directory(root)
    candidate=assets.real_directory(candidate)
    plan=read_json_private(candidate/"candidate.json")
    if plan.get("format")!=1 or plan.get("root")!=str(root) or plan.get("activated") is not False:
        raise ValueError("Invalid candidate")
    check_candidate_source(candidate,plan)
    before=live_core(root)
    if before!=plan["previous"] or check_scope(root,candidate/"source")!=plan["configuration"] or assets.local_docker()!=plan["platform"]:
        raise ValueError("Installed configuration or core identity changed")
    marker=root/"data/core/recovery-maintenance.json"
    seal=read_json_private(marker,8192)
    if seal.get("phase")=="updating" and seal.get("candidate_sha256")!=assets.sha256_file(candidate/"candidate.json"):
        raise ValueError("Maintenance claim belongs to another candidate")
    inventory=live_backup_inventory(before["worker"]["container"])
    proof=validate_backup_evidence(plan,seal,inventory,int(time.time()))
    if read_json_private(marker,8192)!=seal or live_core(root)!=before:
        raise ValueError("Maintenance or core changed during evidence check")
    # Advisory only: a seal can subsequently be released. Activation must
    # repeat this check under a durable admission boundary.
    return {"backup_evidence_checked":True,"manifest_job":inventory["manifest_job"],
            "inventory_sha256":seal["inventory_sha256"],"sources":proof,
            "activation_enabled":False,"rollback_ready":False}


def image_archive_identities(path):
    """Verify the image configuration identities in a Docker save archive."""
    with tarfile.open(path,mode="r:") as tar:
        member=tar.getmember("manifest.json")
        if not member.isfile() or not 0<member.size<=65536:raise ValueError("Invalid Docker archive manifest")
        rows=json.load(tar.extractfile(member))
        if not isinstance(rows,list) or not 1<=len(rows)<=2:raise ValueError("Unexpected archived image count")
        ids=set()
        for row in rows:
            name=row["Config"]
            if not isinstance(name,str) or not re.fullmatch(r"(?:blobs/sha256/[a-f0-9]{64}|[a-f0-9]{64}\.json)",name):
                raise ValueError("Invalid Docker image configuration path")
            config=tar.getmember(name)
            if not config.isfile() or not 0<config.size<=16*1024*1024:
                raise ValueError("Invalid archived image configuration")
            digest=hashlib.sha256(tar.extractfile(config).read()).hexdigest()
            if digest!=name.rsplit("/",1)[-1].removesuffix(".json"):raise ValueError("Archived image identity mismatch")
            ids.add("sha256:"+digest)
        return ids


def image_ref_matches(tag,expected):
    if not IMAGE.fullmatch(expected) or assets.docker("image","inspect","--format","{{.Id}}",tag)!=expected:
        raise ValueError("Exact local image missing or changed")


def write_private_json(path,value):
    with path.open("x") as out:
        os.fchmod(out.fileno(),0o600)
        json.dump(value,out,indent=2)
        out.flush()
        os.fsync(out.fileno())


def retain_previous(root,candidate):
    root=assets.real_directory(root)
    candidate=assets.real_directory(candidate)
    if candidate.stat().st_uid!=os.geteuid() or stat.S_IMODE(candidate.stat().st_mode)!=0o700:
        raise ValueError("Private candidate directory required")
    plan=read_json_private(candidate/"candidate.json")
    if plan.get("format")!=1 or plan.get("root")!=str(root) or plan.get("activated") is not False:
        raise ValueError("Invalid candidate")
    if assets.local_docker()!=plan["platform"] or live_core(root)!=plan["previous"]:
        raise ValueError("Installed core changed")
    check_candidate_source(candidate,plan)
    if check_scope(root,candidate/"source")!=plan["configuration"]:raise ValueError("Configuration changed")
    destination=candidate/"previous"
    if destination.exists() or destination.is_symlink():raise ValueError("Previous image retention already exists; inspect it")
    stage=Path(tempfile.mkdtemp(prefix=".retain-",dir=candidate))
    try:
        rows=[]
        prior={}
        for service in ("core","worker"):
            expected=plan["previous"][service]["image"]
            target=plan["candidate"][service]
            if not re.fullmatch(r"aftergrid-candidate/"+service+r":[a-f0-9]{40}-[a-f0-9]{12}",target["tag"]):
                raise ValueError("Invalid candidate tag")
            image_ref_matches(target["tag"],target["image"])
            image_ref_matches(expected,expected)
            tag="aftergrid-previous/"+service+":"+expected.removeprefix("sha256:")
            # A dedicated immutable-by-convention local reference protects the
            # exact image from ordinary dangling-image cleanup. Never prune.
            assets.docker("image","tag",expected,tag)
            image_ref_matches(tag,expected)
            rows.append({"image_id":expected})
            prior[service]={"tag":tag,"image":expected}
        archive=stage/"images.tar"
        assets.save_images(rows,archive)
        if image_archive_identities(archive)!={r["image_id"] for r in rows}:
            raise ValueError("Prior image archive identity mismatch")
        archive_hash=assets.sha256_file(archive)
        if live_core(root)!=plan["previous"] or check_scope(root,candidate/"source")!=plan["configuration"]:
            raise ValueError("Live core or configuration changed during retention")
        # Construct only reviewed Compose image overrides; activation remains
        # unavailable until the consistent data rollback boundary is proven.
        for name,images in (("candidate",plan["candidate"]),("previous",prior)):
            write_private_json(stage/(name+".json"),{"services":{
                service:{"image":images[service]["tag"],"pull_policy":"never"}
                for service in ("core","worker")}})
        report={"format":1,"candidate_sha256":assets.sha256_file(candidate/"candidate.json"),
                "previous":prior,"archive_sha256":archive_hash,"archive_bytes":archive.stat().st_size,
                "retained_at":int(time.time()),"image_archive_verified":True,
                "activation_enabled":False,"rollback_ready":False}
        write_private_json(stage/"retention.json",report)
        stage.rename(destination)
        return report
    finally:
        if stage.exists():shutil.rmtree(stage)


def verify_retention(candidate,plan):
    directory=assets.real_directory(candidate/"previous")
    record=read_json_private(directory/"retention.json")
    if (record.get("format")!=1 or record.get("candidate_sha256")!=assets.sha256_file(candidate/"candidate.json")
        or record.get("image_archive_verified") is not True):
        raise ValueError("Previous image retention record does not match candidate")
    archive=directory/"images.tar"
    if archive.is_symlink() or not archive.is_file() or archive.stat().st_size!=record.get("archive_bytes"):
        raise ValueError("Prior image archive missing or changed")
    if assets.sha256_file(archive)!=record.get("archive_sha256"):
        raise ValueError("Prior image archive checksum mismatch")
    if image_archive_identities(archive)!={plan["previous"][name]["image"] for name in ("core","worker")}:
        raise ValueError("Prior archive identity mismatch")
    for name,images in (("previous",record["previous"]),("candidate",plan["candidate"])):
        expected={}
        if set(images)!={"core","worker"}:raise ValueError("Unexpected update services")
        for service in ("core","worker"):
            image=images[service]
            if name=="previous":
                ident=plan["previous"][service]["image"]
                if image!={"image":ident,"tag":"aftergrid-previous/"+service+":"+ident.removeprefix("sha256:")}:
                    raise ValueError("Unexpected previous image reference")
            elif not re.fullmatch(r"aftergrid-candidate/"+service+r":[a-f0-9]{40}-[a-f0-9]{12}",image["tag"]):
                raise ValueError("Unexpected candidate image reference")
            image_ref_matches(image["tag"],image["image"])
            expected[service]={"image":image["tag"],"pull_policy":"never"}
        if read_json_private(directory/(name+".json"))!={"services":expected}:
            raise ValueError("Update Compose override changed")
    return record


def check_activation(root,candidate):
    root=assets.real_directory(root)
    candidate=assets.real_directory(candidate)
    plan=read_json_private(candidate/"candidate.json")
    retained=verify_retention(candidate,plan)
    # Hashing an image archive can be slow. Check fresh backups last.
    backups=check_backups(root,candidate)
    seal=read_json_private(root/"data/core/recovery-maintenance.json",8192)
    if (seal.get("phase")!="updating" or seal.get("candidate_sha256")!=retained["candidate_sha256"]
        or seal.get("inventory_sha256")!=backups["inventory_sha256"]):
        raise ValueError("Acquire matching durable update maintenance claim first")
    return {"candidate_sha256":retained["candidate_sha256"],"image_archive_verified":True,
            "backup_evidence":backups,"maintenance_claimed":True,
            "consistent_local_state_checkpoint":False,"activation_enabled":False}


def cancel_claim(root,candidate):
    """Host-only cancellation before any activation journal or replacement."""
    root=assets.real_directory(root)
    candidate=assets.real_directory(candidate)
    plan=read_json_private(candidate/"candidate.json")
    if plan.get("root")!=str(root) or assets.local_docker()!=plan["platform"] or live_core(root)!=plan["previous"]:
        raise ValueError("Original healthy services not confirmed; inspect manually")
    if (candidate/"activation.json").exists() or (root/".core-update-active").exists():
        raise ValueError("Activation journal exists; manual reconciliation required")
    path=root/"data/core/recovery-maintenance.json"
    seal=read_json_private(path,8192)
    if seal.get("phase")!="updating" or seal.get("candidate_sha256")!=assets.sha256_file(candidate/"candidate.json"):
        raise ValueError("Matching update hold required")
    value={key:seal[key] for key in ("format","modules","inventory_sha256","manifest_job")}
    value["phase"]="sealed"
    info=path.stat()
    fd,tmp=tempfile.mkstemp(prefix=".core-update-cancel-",dir=path.parent)
    try:
        with os.fdopen(fd,"w") as out:
            os.fchown(out.fileno(),info.st_uid,info.st_gid)
            os.fchmod(out.fileno(),0o600)
            json.dump(value,out)
            out.flush()
            os.fsync(out.fileno())
        if read_json_private(path,8192)!=seal:raise ValueError("Maintenance marker changed")
        os.replace(tmp,path)
        directory_fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(directory_fd)
        finally:os.close(directory_fd)
    finally:Path(tmp).unlink(missing_ok=True)
    return {"phase":"sealed","activation_enabled":False}


CHECKPOINT_LIMIT=32*1024**3


def checkpoint_archive(path,database,required_tables):
    """Validate a private stopped-state tar without extracting arbitrary paths."""
    seen=set()
    total=0
    with tarfile.open(path,"r:") as tar:
        for member in tar:
            name=PurePosixPath(member.name)
            if name.is_absolute() or ".." in name.parts or name in seen:
                raise ValueError("Invalid checkpoint member path")
            seen.add(name)
            if not (member.isdir() or member.isfile()):
                raise ValueError("Checkpoint contains a link or special file")
            total+=member.size
            if total>CHECKPOINT_LIMIT or len(seen)>100000:
                raise ValueError("Checkpoint exceeds local safety limit")
            if member.isfile() and name.name.endswith(("-wal","-journal")) and member.size:
                raise ValueError("Nonempty SQLite journal in stopped checkpoint")
        with tempfile.TemporaryDirectory(prefix="aftergrid-checkpoint-db-") as tmp:
            db=Path(tmp)/"check.sqlite3"
            member=next((m for m in tar.getmembers() if PurePosixPath(m.name)==PurePosixPath(database)),None)
            if member is None or not member.isfile() or not 0<member.size<=128*1024**2:
                raise ValueError("Required checkpoint database missing or oversized")
            with tar.extractfile(member) as source,db.open("xb") as out:shutil.copyfileobj(source,out)
            with sqlite3.connect(db.as_uri()+"?mode=ro&immutable=1",uri=True) as con:
                con.execute("PRAGMA trusted_schema=OFF")
                if con.execute("PRAGMA integrity_check").fetchmany(2)!=[("ok",)]:
                    raise ValueError("Checkpoint database integrity check failed")
                tables={row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not required_tables<=tables:raise ValueError("Checkpoint database schema missing")
    return {"sha256":assets.sha256_file(path),"bytes":path.stat().st_size,"database_integrity":True}


def stopped_core_mounts(root,prior):
    """Confirm exact stopped containers and expected storage, not other projects."""
    if set(prior)!={"core","worker"}:raise ValueError("Unexpected checkpoint services")
    for service in ("core","worker"):
        row=prior[service]
        cid=row["container"]
        if not SHA.fullmatch(cid) or not IMAGE.fullmatch(row["image"]):raise ValueError("Invalid prior identity")
        fmt='{{json .Config.Labels}}|{{json .Image}}|{{json .State.Status}}|{{json .Mounts}}'
        labels,image,status,mounts=map(json.loads,assets.docker("container","inspect","--format",fmt,cid).split("|"))
        if (image!=row["image"] or status!="exited"
            or labels.get("com.docker.compose.project")!="aftergrid-core"
            or labels.get("com.docker.compose.service")!=service
            or labels.get("com.docker.compose.project.working_dir")!=str(root)
            or labels.get("com.docker.compose.project.config_files")!=str(root/"compose.yaml")):
            raise ValueError("Expected exact stopped core services")
        target="/data" if service=="core" else "/worker-state"
        matches=[m for m in mounts if m["Destination"]==target]
        if len(matches)!=1:raise ValueError("Unexpected checkpoint storage")
        mount=matches[0]
        if service=="core":
            if mount.get("Type")!="bind" or mount.get("Source")!=str(root/"data/core"):
                raise ValueError("Unexpected core data bind")
        elif mount.get("Type")!="volume" or mount.get("Name")!="aftergrid-core_worker_state":
            raise ValueError("Unexpected worker state volume")
    return "aftergrid-core_worker_state"


def capture_stopped_checkpoint(root,destination,prior):
    """Internal preparation primitive; no stop/start or activation CLI yet.

    The transaction caller must hold maintenance and stop exactly the reviewed
    core services before calling. Only their persistent state is archived.
    """
    root=assets.real_directory(root)
    destination=Path(destination).absolute()
    parent=assets.real_directory(destination.parent)
    if destination.exists() or destination.is_symlink() or root==destination or root in destination.parents:
        raise ValueError("Choose a new private checkpoint outside the installation")
    assets.local_docker()
    volume=stopped_core_mounts(root,prior)
    # A running container sharing the state volume would invalidate consistency.
    if assets.docker("ps","-q","--filter","volume="+volume):
        raise ValueError("Worker state volume still in use")
    source=assets.real_directory(root/"data/core")
    # Refuse overlapping writable Docker binds; Kopia's read-only source is fine.
    for cid in assets.docker("ps","-q","--no-trunc").splitlines():
        if not SHA.fullmatch(cid):raise ValueError("Unexpected container identity")
        for mount in json.loads(assets.docker("container","inspect","--format","{{json .Mounts}}",cid)):
            if mount.get("Type")=="bind" and mount.get("RW"):
                other=Path(mount["Source"])
                if other==source or other in source.parents or source in other.parents:
                    raise ValueError("Core state still mounted writable by a running container")
    stage=Path(tempfile.mkdtemp(prefix=".checkpoint-",dir=parent))
    try:
        core=stage/"core.tar"
        with tarfile.open(core,"w",dereference=False) as tar:
            tar.add(source,arcname=".")
        core.chmod(0o600)
        worker=stage/"worker.tar"
        # Native Docker volume backup: existing local worker image, no network,
        # Docker socket, writable volume mount or image pull.
        with worker.open("xb") as out:
            os.fchmod(out.fileno(),0o600)
            subprocess.run(["docker","run","--rm","--pull","never","--network","none",
                            "--read-only","--cap-drop","ALL","--cap-add","DAC_OVERRIDE",
                            "--security-opt","no-new-privileges",
                            "--mount","type=volume,src="+volume+",dst=/state,readonly,volume-nocopy",
                            "--entrypoint","tar",prior["worker"]["image"],"-C","/state","-cf","-","."],
                           stdout=out,stderr=subprocess.PIPE,check=True,timeout=180)
        reports={"core":checkpoint_archive(core,"core.sqlite3",{"admin","sessions","first_run"}),
                 "worker":checkpoint_archive(worker,"jobs.sqlite3",{"jobs","sharing","batches"})}
        stopped_core_mounts(root,prior)
        report={"format":1,"previous":prior,"created":int(time.time()),"archives":reports,
                "scope":"core and worker state only","activation_enabled":False}
        write_private_json(stage/"checkpoint.json",report)
        for path in (core,worker):
            with path.open("rb") as stream:os.fsync(stream.fileno())
        stage.rename(destination)
        return report
    finally:
        if stage.exists():shutil.rmtree(stage)


def scoped_compose(root,*args,override=None):
    cmd=["docker","compose","--project-name","aftergrid-core","--project-directory",str(root),
         "--env-file",str(root/".env"),"--file",str(root/"compose.yaml")]
    if override is not None:cmd.extend(("--file",str(override)))
    env={"PATH":os.environ["PATH"],"HOME":"/root","DOCKER_HOST":"unix:///var/run/docker.sock"}
    return subprocess.run([*cmd,*args],env=env,capture_output=True,text=True,check=True,timeout=180).stdout


def replace_core(root,images,override=None):
    if set(images)!={"core","worker"}:raise ValueError("Unexpected replacement services")
    for name in ("core","worker"):
        row=images[name]
        image_ref_matches(row["tag"],row["image"])
        if override is None:
            assets.docker("image","tag",row["image"],"aftergrid-core-"+name)
    scoped_compose(root,"up","-d","--no-deps","--force-recreate","--no-build","--pull","never",
                   "--wait","--wait-timeout","120","worker","core",override=override)
    actual=live_core(root,override)
    if any(actual[name]["image"]!=images[name]["image"] for name in images):
        raise ValueError("Replacement image identity mismatch")
    return actual


def unpack_checkpoint(archive,destination,expected,database,tables):
    if checkpoint_archive(archive,database,tables)!=expected:
        raise ValueError("Checkpoint archive changed")
    destination.mkdir(mode=0o700)
    # Validation rejects links, special files and traversal. Preserve numeric
    # ownership of the private application state on this disposable host.
    with tarfile.open(archive,"r:") as tar:
        tar.extractall(destination,numeric_owner=True,filter="fully_trusted")


def journal(path,value):
    fd,tmp=tempfile.mkstemp(prefix=".update-journal-",dir=path.parent)
    try:
        with os.fdopen(fd,"w") as out:
            json.dump(value,out,indent=2)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp,path)
        directory_fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(directory_fd)
        finally:os.close(directory_fd)
    finally:Path(tmp).unlink(missing_ok=True)


def trial_replacement(root,candidate,plan,retained,probe):
    state={"format":1,"candidate_sha256":retained["candidate_sha256"],"phase":"stopping",
           "previous":plan["previous"],"trial_only":True}
    transaction=candidate/"activation.json"
    write_private_json(transaction,state)
    def phase(value):
        state["phase"]=value
        journal(transaction,state)
    override=candidate/"trial-compose.json"
    attempted=False
    verified=False
    try:
        scoped_compose(root,"stop","core","worker")
        phase("checkpointing")
        checkpoint=capture_stopped_checkpoint(root,candidate/"checkpoint",plan["previous"])
        state["checkpoint"]=checkpoint["archives"]
        for service,database,tables in (("core","core.sqlite3",{"admin","sessions","first_run"}),
                                        ("worker","jobs.sqlite3",{"jobs","sharing","batches"})):
            unpack_checkpoint(candidate/"checkpoint"/(service+".tar"),candidate/(service+"-trial"),
                              checkpoint["archives"][service],database,tables)
        write_private_json(override,{"services":{
            service:{"image":plan["candidate"][service]["tag"],"pull_policy":"never","volumes":[
                {"type":"bind","source":str(candidate/(service+"-trial")),
                 "target":"/data" if service=="core" else "/worker-state","bind":{"create_host_path":False}}]}
            for service in ("core","worker")}})
        config=json.loads(scoped_compose(root,"config","--format","json",override=override))
        if set(config["services"])!={"core","worker"}:raise ValueError("Unexpected trial configuration")
        for service,target in (("core","/data"),("worker","/worker-state")):
            definition=config["services"][service]
            mounts=[m for m in definition["volumes"] if m["target"]==target]
            if (definition["image"]!=plan["candidate"][service]["tag"] or definition["pull_policy"]!="never"
                or len(mounts)!=1 or mounts[0]["type"]!="bind" or mounts[0]["source"]!=str(candidate/(service+"-trial"))):
                raise ValueError("Trial state isolation mismatch")
        phase("replacing")
        attempted=True
        state["trial_containers"]=replace_core(root,plan["candidate"],override)
        phase("verifying")
        probe()
        verified=True
        phase("trial_verified")
    finally:
        # The candidate ran on copies; never restore over or delete original
        # state. The original bind and named volume remain authoritative.
        phase("returning_to_previous")
        try:
            if attempted:scoped_compose(root,"stop","core","worker",override=override)
            state["returned_containers"]=replace_core(root,retained["previous"])
            state["trial_verified"]=verified
            phase("returned_to_previous")
        except Exception:
            phase("rollback_requires_inspection")
            raise
    return state


def inspect_trial(candidate):
    """Read-only durable trial status; never infer success from a journal alone."""
    candidate=assets.real_directory(candidate)
    plan=read_json_private(candidate/"candidate.json")
    path=candidate/"activation.json"
    if not path.exists() and not path.is_symlink():
        return {"phase":"not_started","production_activation":False}
    state=read_json_private(path)
    if (state.get("format")!=1 or state.get("trial_only") is not True
        or state.get("candidate_sha256")!=assets.sha256_file(candidate/"candidate.json")
        or state.get("previous")!=plan.get("previous")):
        raise ValueError("Trial journal does not match candidate")
    phase=state.get("phase")
    if phase not in {"stopping","checkpointing","replacing","verifying","trial_verified",
                     "returning_to_previous","returned_to_previous","rollback_requires_inspection"}:
        raise ValueError("Invalid update journal phase")
    return {"phase":phase,"trial_verified":state.get("trial_verified") is True,
            "requires_inspection":phase!="returned_to_previous",
            "production_activation":False}


def disposable_trial_scope(root,candidate):
    if os.geteuid()!=0 or os.environ.get("AFTERGRID_DISPOSABLE_RECOVERY_TEST")!="1":
        raise ValueError("Disposable core update acceptance only")
    root=assets.real_directory(root)
    candidate=assets.real_directory(candidate)
    if not root.parent.name.startswith("aftergrid-guided-ci-") or root.name!="original" or candidate.parent!=root.parent:
        raise ValueError("Expected disposable guided fixture")
    return root,candidate


def production_scope(root,candidate):
    """Release admission before any Docker operation, including rollback."""
    if PRODUCTION_EXECUTION_ENABLED is not True:
        raise ValueError("Production core updates are not released")
    if os.geteuid()!=0 or Path("/etc/pve").exists() or shutil.which("pveversion"):
        raise ValueError("Use the installed Linux guest, not the hypervisor")
    root=assets.real_directory(root)
    candidate=assets.real_directory(candidate)
    staging=assets.real_directory(STAGING)
    if root!=ROOT or candidate.parent!=staging or root in candidate.parents or candidate in root.parents:
        raise ValueError("Expected the normal installation and private update staging")
    for directory in (staging,candidate):
        info=directory.stat()
        if info.st_uid!=0 or stat.S_IMODE(info.st_mode)!=0o700:
            raise ValueError("Private root-owned update staging required")
    if (root/".install-pending").exists() or (root/"recovery-install-plan.json").exists():
        raise ValueError("Complete installation or recovery first")
    plan=read_json_private(candidate/"candidate.json")
    commit=plan.get("commit")
    if not isinstance(commit,str) or not COMMIT.fullmatch(commit):
        raise ValueError("Exact approved release required")
    if (plan.get("format")!=1 or plan.get("activated") is not False or plan.get("root")!=str(root)
        or not re.fullmatch(re.escape(commit)+r"-[a-f0-9]{12}",candidate.name)):
        raise ValueError("Candidate does not match installed release scope")
    approved=APPROVED_CORE_RELEASES.get(commit)
    if (not isinstance(approved,dict) or set(approved)!={"archive_sha256","source_sha256"}
        or any(not isinstance(approved[k],str) or not SHA.fullmatch(approved[k]) or plan.get(k)!=approved[k]
               for k in ("archive_sha256","source_sha256"))):
        raise ValueError("Release is not approved for production execution")
    check_candidate_source(candidate,plan)
    return root,candidate


def transaction_scope(root,candidate,production):
    return production_scope(root,candidate) if production else disposable_trial_scope(root,candidate)


def candidate_trial(root,candidate,probe,*,production=False):
    """Isolated state-copy trial; production additionally requires release approval."""
    root,candidate=transaction_scope(root,candidate,production)
    plan=read_json_private(candidate/"candidate.json")
    retained=verify_retention(candidate,plan)
    check_activation(root,candidate)
    if (candidate/"activation.json").exists() or (candidate/"activation.json").is_symlink():
        raise ValueError("Update journal already exists")
    return trial_replacement(root,candidate,plan,retained,probe)


def trial_container_inventory(root,candidate,plan,canonical_candidate=False):
    """Inspect only the core project, including partially replaced services."""
    rows={}
    base=str(root/"compose.yaml")
    allowed_files={base,base+","+str(candidate/"trial-compose.json")}
    for cid in assets.docker("ps","-a","-q","--no-trunc","--filter","label=com.docker.compose.project=aftergrid-core").splitlines():
        if not SHA.fullmatch(cid):raise ValueError("Invalid core container identity")
        fmt='{{json .Config.Labels}}|{{json .Image}}|{{json .State.Status}}|{{json .Mounts}}'
        labels,image,status,mounts=map(json.loads,assets.docker("container","inspect","--format",fmt,cid).split("|"))
        service=labels.get("com.docker.compose.service")
        files=labels.get("com.docker.compose.project.config_files")
        if (service not in {"core","worker"} or service in rows
            or labels.get("com.docker.compose.project")!="aftergrid-core"
            or labels.get("com.docker.compose.project.working_dir")!=str(root)
            or files not in allowed_files or status not in {"running","exited","created","restarting"}):
            raise ValueError("Unexpected container in core project; inspect manually")
        trial=files!=base
        expected=plan["candidate" if trial else "previous"][service]["image"]
        if image!=expected and not (canonical_candidate and not trial and image==plan["candidate"][service]["image"]):
            raise ValueError("Unexpected core image; inspect manually")
        target="/data" if service=="core" else "/worker-state"
        selected=[m for m in mounts if m["Destination"]==target]
        if len(selected)!=1:raise ValueError("Unexpected state mount")
        mount=selected[0]
        if trial or service=="core":
            source=candidate/(service+"-trial") if trial else root/"data/core"
            if mount.get("Type")!="bind" or mount.get("Source")!=str(source):
                raise ValueError("Unexpected core state bind")
        elif mount.get("Type")!="volume" or mount.get("Name")!="aftergrid-core_worker_state":
            raise ValueError("Unexpected worker state volume")
        rows[service]={"container":cid,"state":status,"trial":trial}
    return rows


def reconcile_trial(root,candidate):
    """Return an interrupted disposable trial to untouched original state.

    Never promote trial state. Require the original persistent maintenance
    marker and exact project ownership before stopping any container.
    """
    root,candidate=disposable_trial_scope(root,candidate)
    plan=read_json_private(candidate/"candidate.json")
    if plan.get("root")!=str(root) or assets.local_docker()!=plan.get("platform"):
        raise ValueError("Trial root or platform changed")
    check_candidate_source(candidate,plan)
    if check_scope(root,candidate/"source")!=plan["configuration"]:
        raise ValueError("Installed configuration changed")
    retained=verify_retention(candidate,plan)
    status=inspect_trial(candidate)
    if status["phase"] in {"not_started","returned_to_previous"}:
        raise ValueError("No interrupted trial to reconcile")
    marker=root/"data/core/recovery-maintenance.json"
    seal=read_json_private(marker,8192)
    if (seal.get("phase")!="updating" or seal.get("candidate_sha256")!=retained["candidate_sha256"]):
        raise ValueError("Original maintenance hold changed")
    rows=trial_container_inventory(root,candidate,plan)
    path=candidate/"activation.json"
    state=read_json_private(path)
    state["phase"]="returning_to_previous"
    journal(path,state)
    try:
        # Only the exact inspected core project containers. Never stop app
        # projects, remove volumes or bring down the shared network.
        for row in rows.values():
            if row["state"] in {"running","restarting"}:
                assets.docker("stop",row["container"],timeout=90)
        actual=replace_core(root,retained["previous"])
        state["returned_containers"]=actual
        state["trial_verified"]=False
        state["reconciled_interruption"]=True
        state["phase"]="returned_to_previous"
        journal(path,state)
    except Exception:
        state["phase"]="rollback_requires_inspection"
        journal(path,state)
        raise
    return state


def source_tree_digest(path):
    return hashlib.sha256(json.dumps(tree_hashes(path),sort_keys=True,separators=(",",":")).encode()).hexdigest()


def stage_source_transition(root,candidate):
    """Prepare same-filesystem source moves. Never stage runtime data."""
    plan=read_json_private(candidate/"candidate.json")
    check_candidate_source(candidate,plan)
    if plan["root"]!=str(root) or check_scope(root,candidate/"source")!=plan["configuration"]:
        raise ValueError("Installed configuration changed")
    digest=assets.sha256_file(candidate/"candidate.json")
    stage=root/(".core-update-source-"+digest[:20])
    stage.mkdir(mode=0o700)
    new=stage/"new"
    old=stage/"old"
    new.mkdir(mode=0o700)
    old.mkdir(mode=0o700)
    sources={}
    for name in ("core","worker"):
        previous=source_tree_digest(root/name)
        expected=source_tree_digest(candidate/"source"/name)
        shutil.copytree(candidate/"source"/name,new/name)
        if source_tree_digest(new/name)!=expected:raise ValueError("Staged source changed")
        sources[name]={"previous":previous,"candidate":expected}
    write_private_json(stage/"source-transition.json",{"format":1,"root":str(root),
                       "candidate_sha256":digest,"sources":sources,"phase":"staged"})
    return stage


def sync_directory(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


def source_transition(root,stage,forward):
    """Idempotent source-only reconciliation using known directory identities.

    Caller must first stop the exact core/worker containers and hold admission.
    Retain both source trees, never overwrite or remove an unknown directory.
    """
    root=assets.real_directory(root)
    stage=assets.real_directory(stage)
    record=read_json_private(stage/"source-transition.json")
    if (stage.parent!=root or not stage.name.startswith(".core-update-source-")
        or record.get("root")!=str(root) or record.get("format")!=1
        or set(record.get("sources",{}))!={"core","worker"}
        or record.get("phase") not in {"staged","promoting","promoted","restoring","restored"}):
        raise ValueError("Invalid source transition")
    for name in ("new","old"):assets.real_directory(stage/name)
    def identity(path):
        if not path.exists() and not path.is_symlink():return None
        return source_tree_digest(path)
    def move(src,dst):
        if dst.exists() or dst.is_symlink():raise ValueError("Unexpected source destination")
        src.rename(dst)
        sync_directory(src.parent)
        sync_directory(dst.parent)
    # Check both services before changing either one. An interruption after
    # either rename is represented by one of three exact path arrangements.
    for name,row in record["sources"].items():
        if not all(isinstance(row.get(k),str) and SHA.fullmatch(row[k]) for k in ("previous","candidate")):
            raise ValueError("Invalid source identity")
        p,n,o=identity(root/name),identity(stage/"new"/name),identity(stage/"old"/name)
        before=(row["previous"],row["candidate"],None)
        middle=(None,row["candidate"],row["previous"])
        after=(row["candidate"],None,row["previous"])
        if (p,n,o) not in {before,middle,after}:raise ValueError("Unknown source arrangement; inspect manually")
    record["phase"]="promoting" if forward else "restoring"
    journal(stage/"source-transition.json",record)
    for name,row in record["sources"].items():
        live=root/name
        new=stage/"new"/name
        old=stage/"old"/name
        if forward:
            if not old.exists():move(live,old)
            if not live.exists():move(new,live)
        else:
            if old.exists() and live.exists():move(live,new)
            if old.exists():move(old,live)
        expected=row["candidate" if forward else "previous"]
        if identity(live)!=expected:raise ValueError("Source transition verification failed")
    record["phase"]="promoted" if forward else "restored"
    journal(stage/"source-transition.json",record)
    return record


SOURCE_MUTATION = r'''
import json, sys
from pathlib import Path
sys.path.insert(0, "/app")
import core_update_tools as update
operation, root, candidate = sys.argv[1:]
root = update.assets.real_directory(Path(root))
candidate = update.assets.real_directory(Path(candidate))
plan = update.read_json_private(candidate / "candidate.json")
digest = update.assets.sha256_file(candidate / "candidate.json")
if plan["root"] != str(root):
    raise ValueError("Candidate installation mismatch")
marker = root / "data/core/recovery-maintenance.json"
if operation == "restore-core" and not marker.exists():
    marker = root / "data" / (".core-failed-" + digest[:20]) / "recovery-maintenance.json"
seal = update.read_json_private(marker, 8192)
if seal.get("phase") != "updating" or seal.get("candidate_sha256") != digest:
    raise ValueError("Matching update hold required")
stage = root / (".core-update-source-" + digest[:20])
if operation == "stage":
    result = str(update.stage_source_transition(root, candidate))
else:
    state = update.read_json_private(candidate / "promotion.json")
    if state.get("candidate_sha256") != digest or state.get("source_stage") != str(stage):
        raise ValueError("Promotion journal mismatch")
    if operation in {"promote-source", "restore-source"}:
        result = update.source_transition(root, stage, operation == "promote-source")
    elif operation == "restore-core":
        checkpoint = candidate / "promotion-checkpoint"
        report = update.read_json_private(checkpoint / "checkpoint.json")
        if report["archives"] != state.get("checkpoint"):
            raise ValueError("Promotion checkpoint mismatch")
        result = str(update.restore_core_bind(root, checkpoint,
            report["archives"]["core"], digest[:20], digest))
    else:
        raise ValueError("Unsupported fixed update operation")
print(json.dumps(result))
'''


def container_mutation(root, candidate, image, operation):
    """Fixed short-lived filesystem operation; no socket or network in helper.

    Source operations protect runtime data with a nested read-only bind. Core
    restoration instead grants only the data parent, after services are stopped.
    The transaction executor can keep its installation bind read-only throughout.
    """
    if operation not in {"stage", "promote-source", "restore-source", "restore-core"}:
        raise ValueError("Unsupported fixed update operation")
    if not isinstance(image, str) or not IMAGE.fullmatch(image):
        raise ValueError("Exact retained worker image required")
    root = assets.real_directory(root)
    candidate = assets.real_directory(candidate)
    data = assets.real_directory(root / "data")
    if root == candidate or root in candidate.parents or candidate in root.parents:
        raise ValueError("Candidate must be outside the installation")
    for path in (root, candidate, data):
        if "," in str(path) or any(ord(c) < 32 for c in str(path)):
            raise ValueError("Unsafe update mount path")
    plan = read_json_private(candidate / "candidate.json")
    if plan["root"] != str(root) or plan["previous"]["worker"]["image"] != image:
        raise ValueError("Retained worker identity mismatch")
    image_ref_matches(image, image)
    restore = operation == "restore-core"
    argv = ["run", "--rm", "--pull", "never", "--network", "none", "--read-only",
        "--cap-drop", "ALL", "--cap-add", "DAC_OVERRIDE", "--cap-add", "CHOWN",
        "--cap-add", "FOWNER", "--security-opt", "no-new-privileges",
        # SQLite checkpoint validation extracts a bounded database into a
        # private temporary directory. Keep scratch off persistent mounts.
        *(["--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=160m,mode=0700"] if restore else []),
        "--mount", "type=bind,src=" + str(root) + ",dst=" + str(root) + (",readonly" if restore else ""),
        "--mount", "type=bind,src=" + str(data) + ",dst=" + str(data) + ("" if restore else ",readonly"),
        "--mount", "type=bind,src=" + str(candidate) + ",dst=" + str(candidate) + ",readonly",
        "--entrypoint", "python3", image, "-I", "-c", SOURCE_MUTATION,
        operation, str(root), str(candidate)]
    try:
        return json.loads(assets.docker(*argv, timeout=180))
    except subprocess.CalledProcessError as exc:
        # The helper runs a fixed program, not user commands. Preserve a
        # bounded diagnostic rather than dumping the full Docker argv.
        detail = (exc.stderr or "").strip()[-2000:]
        raise RuntimeError(f"Fixed update helper {operation} failed (exit {exc.returncode}): {detail}") from None


# Fixed helper executed in the retained local worker image. The named volume
# is never removed. Save failed files by rename before restoring; the
# quarantine is intentionally retained for inspection.
RESTORE_WORKER=r"""
import hashlib,json,os,stat,sys,tarfile,uuid
from pathlib import Path,PurePosixPath
root=Path("/state")
archive=Path("/checkpoint/worker.tar")
quarantine=root/sys.argv[1]
if hashlib.file_digest(archive.open("rb"),"sha256").hexdigest()!=sys.argv[2]:
    raise RuntimeError("Worker checkpoint digest changed")
with tarfile.open(archive,"r:") as tar:
    members=tar.getmembers()
    for m in members:
        p=PurePosixPath(m.name)
        if p.is_absolute() or ".." in p.parts or not (m.isdir() or m.isfile()) or quarantine.name in p.parts:
            raise RuntimeError("Unsafe worker checkpoint")
    # Durable phases distinguish moving original state from extracting a copy.
    quarantine.mkdir(mode=0o700,exist_ok=True)
    if quarantine.is_symlink() or not quarantine.is_dir():raise RuntimeError("Invalid worker quarantine")
    original=quarantine/"original"
    original.mkdir(mode=0o700,exist_ok=True)
    phase=quarantine/"phase"
    def mark(value):
        tmp=quarantine/(".phase-"+uuid.uuid4().hex)
        with tmp.open("x") as out:
            out.write(value)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp,phase)
        os.sync()
    current=phase.read_text() if phase.exists() else "moving"
    if current not in {"moving","extracting","done"}:raise RuntimeError("Invalid worker restore phase")
    if current=="moving":
        for child in root.iterdir():
            if child==quarantine:continue
            if (original/child.name).exists() or (original/child.name).is_symlink():
                raise RuntimeError("Worker quarantine collision")
            child.rename(original/child.name)
        mark("extracting")
    if current!="done":
        remaining=[child for child in root.iterdir() if child!=quarantine]
        if remaining:
            partial=quarantine/("partial-"+uuid.uuid4().hex)
            partial.mkdir(mode=0o700)
            for child in remaining:child.rename(partial/child.name)
            os.sync()
        tar.extractall(root,numeric_owner=True,filter="fully_trusted")
    for m in members:
        p=root/m.name
        info=p.lstat()
        if m.isfile():
            if not stat.S_ISREG(info.st_mode) or hashlib.file_digest(p.open("rb"),"sha256").digest()!=hashlib.file_digest(tar.extractfile(m),"sha256").digest():
                raise RuntimeError("Restored worker file mismatch")
        elif not stat.S_ISDIR(info.st_mode):
            raise RuntimeError("Restored worker directory mismatch")
        if (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))!=(m.uid,m.gid,m.mode):
            raise RuntimeError("Restored worker ownership or mode mismatch")
    os.sync()
    mark("done")
"""


def verify_restored_tree(archive,directory):
    directory=assets.real_directory(directory)
    actual={PurePosixPath(p.relative_to(directory).as_posix()) for p in directory.rglob("*")}
    with tarfile.open(archive,"r:") as tar:
        expected={PurePosixPath(m.name) for m in tar.getmembers()}-{PurePosixPath(".")}
        if actual!=expected:raise ValueError("Restored tree contents differ")
        for m in tar.getmembers():
            path=directory/m.name
            info=path.lstat()
            if (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))!=(m.uid,m.gid,m.mode):
                raise ValueError("Restored ownership or mode differs")
            if m.isdir():
                if not stat.S_ISDIR(info.st_mode):raise ValueError("Restored directory differs")
            elif not stat.S_ISREG(info.st_mode) or assets.sha256_file(path)!=hashlib.file_digest(tar.extractfile(m),"sha256").hexdigest():
                raise ValueError("Restored file differs")


def restore_core_bind(root,checkpoint,report,suffix,seal_digest):
    if not re.fullmatch(r"[a-f0-9]{20}",suffix):raise ValueError("Invalid rollback identity")
    parent=assets.real_directory(root/"data")
    live=parent/"core"
    new=parent/(".core-restore-"+suffix)
    failed=parent/(".core-failed-"+suffix)
    for path in (live,new,failed):
        if path.exists() or path.is_symlink():assets.real_directory(path)
    archive=checkpoint/"core.tar"
    if checkpoint_archive(archive,"core.sqlite3",{"admin","sessions","first_run"})!=report:
        raise ValueError("Core checkpoint changed")
    if failed.exists() and live.exists():
        if new.exists():raise ValueError("Ambiguous core restore arrangement")
        verify_restored_tree(archive,live)
        return failed
    if not live.exists() and not failed.exists():raise ValueError("Original core state missing")
    if new.exists():
        try:verify_restored_tree(archive,new)
        except ValueError:
            # A partial extraction is never destroyed; retry into a fresh path.
            new.rename(parent/(".core-partial-"+suffix+"-"+uuid.uuid4().hex))
            sync_directory(parent)
    if not new.exists():unpack_checkpoint(archive,new,report,"core.sqlite3",{"admin","sessions","first_run"})
    verify_restored_tree(archive,new)
    marker=read_json_private(new/"recovery-maintenance.json",8192)
    if marker.get("phase")!="updating" or marker.get("candidate_sha256")!=seal_digest:
        raise ValueError("Checkpoint maintenance hold mismatch")
    if live.exists():
        live.rename(failed)
        sync_directory(parent)
    new.rename(live)
    sync_directory(parent)
    return failed


def rollback_disposable_promotion(root,candidate,state,plan,retained,*,production=False):
    root,candidate=transaction_scope(root,candidate,production)
    if state.get("phase") not in {"starting_candidate","verifying","restoring_canonical_state","restoring_worker_state","restoring_source"} or not state.get("checkpoint"):
        raise ValueError("Canonical checkpoint and attempted startup required")
    digest=retained["candidate_sha256"]
    marker_path=root/"data/core/recovery-maintenance.json"
    if not marker_path.exists() and state["phase"]=="restoring_canonical_state":
        marker_path=root/"data"/(".core-failed-"+digest[:20])/"recovery-maintenance.json"
    marker=read_json_private(marker_path,8192)
    if marker.get("phase")!="updating" or marker.get("candidate_sha256")!=digest:
        raise ValueError("Maintenance hold changed")
    checkpoint=assets.real_directory(candidate/"promotion-checkpoint")
    report=read_json_private(checkpoint/"checkpoint.json")
    if report.get("archives")!=state["checkpoint"] or report.get("previous")!=state["previous"]:
        raise ValueError("Canonical checkpoint identity changed")
    for name,database,tables in (("core","core.sqlite3",{"admin","sessions","first_run"}),
                                 ("worker","jobs.sqlite3",{"jobs","sharing","batches"})):
        if checkpoint_archive(checkpoint/(name+".tar"),database,tables)!=report["archives"][name]:
            raise ValueError("Canonical checkpoint archive changed")
    rows=trial_container_inventory(root,candidate,plan,canonical_candidate=True)
    if any(row["trial"] for row in rows.values()):raise ValueError("Unexpected trial state")
    path=candidate/"promotion.json"
    state["phase"]="restoring_canonical_state"
    journal(path,state)
    for row in rows.values():
        if row["state"] in {"running","restarting"}:
            assets.docker("stop",row["container"],timeout=90)
    volume="aftergrid-core_worker_state"
    if assets.docker("ps","-q","--filter","volume="+volume):
        raise ValueError("Worker state still in use")
    # Scope was checked before mutation; real installs require explicit release policy.
    # Keep the failed core directory and worker quarantine for investigation.
    if state.get("container_mutations") is True:
        failed=Path(container_mutation(root,candidate,retained["previous"]["worker"]["image"],"restore-core"))
    else:
        failed=restore_core_bind(root,checkpoint,report["archives"]["core"],digest[:20],digest)
    state["failed_core"]=str(failed)
    state["phase"]="restoring_worker_state"
    journal(path,state)
    quarantine=".aftergrid-failed-"+digest[:20]
    assets.docker("run","--rm","--pull","never","--network","none","--read-only",
                  "--cap-drop","ALL","--cap-add","DAC_OVERRIDE","--cap-add","CHOWN","--cap-add","FOWNER",
                  "--security-opt","no-new-privileges",
                  "--mount","type=volume,src="+volume+",dst=/state,volume-nocopy",
                  "--mount","type=bind,src="+str(checkpoint)+",dst=/checkpoint,readonly",
                  "--entrypoint","python3",retained["previous"]["worker"]["image"],
                  "-c",RESTORE_WORKER,quarantine,report["archives"]["worker"]["sha256"],timeout=180)
    state["failed_worker_quarantine"]=quarantine
    state["phase"]="restoring_source"
    journal(path,state)
    if state.get("container_mutations") is True:
        container_mutation(root,candidate,retained["previous"]["worker"]["image"],"restore-source")
    else:
        source_transition(root,Path(state["source_stage"]),False)
    state["phase"]="starting_previous"
    journal(path,state)
    state["returned_containers"]=replace_core(root,retained["previous"])
    state["phase"]="rolled_back"
    journal(path,state)
    return state


def promote_disposable(root,candidate,probe,*,container_mutations=False,production=False):
    """Canonical-mount activation under disposable or reviewed release scope.

    A successful isolated trial is mandatory. The original local state is
    captured again before the candidate is started on canonical mounts.
    Canonical startup or probe failure attempts checkpoint restoration.
    An interrupted or unsuccessful restore remains held for inspection.
    """
    root,candidate=transaction_scope(root,candidate,production)
    plan=read_json_private(candidate/"candidate.json")
    retained=verify_retention(candidate,plan)
    check_candidate_source(candidate,plan)
    if check_scope(root,candidate/"source")!=plan["configuration"] or assets.local_docker()!=plan["platform"]:
        raise ValueError("Installed configuration or platform changed")
    status=inspect_trial(candidate)
    if status["phase"]!="returned_to_previous" or not status["trial_verified"]:
        raise ValueError("Successful completed trial required")
    trial=read_json_private(candidate/"activation.json")
    current=live_core(root)
    if current!=trial["returned_containers"]:raise ValueError("Returned core identity changed")
    marker=root/"data/core/recovery-maintenance.json"
    seal=read_json_private(marker,8192)
    if seal.get("phase")!="updating" or seal.get("candidate_sha256")!=retained["candidate_sha256"]:
        raise ValueError("Matching maintenance hold required")
    proof=validate_backup_evidence(plan,seal,live_backup_inventory(current["worker"]["container"]),int(time.time()))
    stage=(Path(container_mutation(root,candidate,retained["previous"]["worker"]["image"],"stage"))
           if container_mutations else stage_source_transition(root,candidate))
    path=candidate/"promotion.json"
    state={"format":1,"phase":"stopping","candidate_sha256":retained["candidate_sha256"],
           "source_stage":str(stage),"previous":current,"backup_evidence":proof,"disposable_only":not production,
           "container_mutations":container_mutations}
    write_private_json(path,state)
    try:
        scoped_compose(root,"stop","core","worker")
        state["phase"]="checkpointing"
        journal(path,state)
        state["checkpoint"]=capture_stopped_checkpoint(root,candidate/"promotion-checkpoint",current)["archives"]
        state["phase"]="promoting_source"
        journal(path,state)
        if container_mutations:
            container_mutation(root,candidate,retained["previous"]["worker"]["image"],"promote-source")
        else:
            source_transition(root,stage,True)
        state["phase"]="starting_candidate"
        journal(path,state)
        state["active"]=replace_core(root,plan["candidate"])
        state["phase"]="verifying"
        journal(path,state)
        probe()
        if candidate_source_digest(root)!=plan["source_sha256"]:
            raise ValueError("Installed source differs from candidate")
        state["phase"]="promoted"
        journal(path,state)
    except Exception:
        if state["phase"] in {"starting_candidate","verifying"} and state.get("checkpoint"):
            try:rollback_disposable_promotion(root,candidate,state,plan,retained,production=production)
            except Exception:
                state["resume_phase"]=state["phase"]
                state["phase"]="promotion_requires_inspection"
                journal(path,state)
                raise
        else:
            state["phase"]="promotion_requires_inspection"
            journal(path,state)
        raise
    return state


def resume_disposable_rollback(root,candidate):
    """Resume interrupted canonical restoration before prior startup only."""
    root,candidate=disposable_trial_scope(root,candidate)
    plan=read_json_private(candidate/"candidate.json")
    retained=verify_retention(candidate,plan)
    check_candidate_source(candidate,plan)
    if plan["root"]!=str(root) or check_scope(root,candidate/"source")!=plan["configuration"] or assets.local_docker()!=plan["platform"]:
        raise ValueError("Installed configuration or platform changed")
    path=candidate/"promotion.json"
    state=read_json_private(path)
    digest=retained["candidate_sha256"]
    if (state.get("format")!=1 or state.get("disposable_only") is not True
        or state.get("candidate_sha256")!=digest
        or state.get("source_stage")!=str(root/(".core-update-source-"+digest[:20]))):
        raise ValueError("Invalid promotion journal")
    if state["phase"]=="promotion_requires_inspection":state["phase"]=state.get("resume_phase")
    if state["phase"] not in {"starting_candidate","verifying","restoring_canonical_state","restoring_worker_state","restoring_source"}:
        raise ValueError("No resumable canonical restoration; inspect manually")
    return rollback_disposable_promotion(root,candidate,state,plan,retained)


def finish_disposable_promotion(root,candidate,*,production=False,detached=False):
    """Reconcile the maintenance hold only after a terminal, verified outcome."""
    root,candidate=transaction_scope(root,candidate,production)
    plan=read_json_private(candidate/"candidate.json")
    retained=verify_retention(candidate,plan)
    path=candidate/"promotion.json"
    state=read_json_private(path)
    digest=retained["candidate_sha256"]
    if (state.get("format")!=1 or state.get("disposable_only") is not (not production)
        or state.get("candidate_sha256")!=digest or state.get("phase") not in {"promoted","rolled_back"}):
        raise ValueError("Verified terminal promotion outcome required")
    if check_scope(root,candidate/"source")!=plan["configuration"] or assets.local_docker()!=plan["platform"]:
        raise ValueError("Installed configuration changed")
    check_candidate_source(candidate,plan)
    source_stage=Path(state["source_stage"])
    if source_stage!=root/(".core-update-source-"+digest[:20]):
        raise ValueError("Unexpected source transition")
    transition=read_json_private(source_stage/"source-transition.json")
    promoted=state["phase"]=="promoted"
    if transition.get("candidate_sha256")!=digest or transition.get("phase")!=("promoted" if promoted else "restored"):
        raise ValueError("Source transition not confirmed")
    for name in ("core","worker"):
        if source_tree_digest(root/name)!=transition["sources"][name]["candidate" if promoted else "previous"]:
            raise ValueError("Installed source identity mismatch")
    actual=live_core(root)
    expected=plan["candidate"] if promoted else retained["previous"]
    if any(actual[name]["image"]!=expected[name]["image"] for name in expected):
        raise ValueError("Running images do not match terminal outcome")
    marker=root/"data/core/recovery-maintenance.json"
    seal=read_json_private(marker,8192)
    if seal.get("phase")!="updating" or seal.get("candidate_sha256")!=digest:
        raise ValueError("Matching maintenance claim required")
    # Preserve ownership because the unprivileged core must read the marker.
    info=marker.stat()
    value={key:seal[key] for key in ("format","modules","inventory_sha256","manifest_job")}
    value["phase"]="sealed"
    if production:
        value["core_update_outcome"]=state["phase"]
        value["core_update_candidate_sha256"]=digest
    if detached:
        if not production:raise ValueError("Detached finalization requires reviewed production scope")
        # Core owns its private data; the executor keeps the host root read-only.
        trial_container_inventory(root,candidate,plan,canonical_candidate=True)
        assets.docker("exec","--user","10001:10001",actual["core"]["container"],"python3","-I","-B","-c",
                      FINALIZE_MARKER,json.dumps(seal),json.dumps(value),timeout=30)
        if read_json_private(marker,8192)!=value or live_core(root)!=actual:
            raise ValueError("Maintenance or core changed during finalization")
        return {"outcome":state["phase"],"maintenance_phase":"sealed","production_activation":promoted}
    fd,tmp=tempfile.mkstemp(prefix=".core-update-finish-",dir=marker.parent)
    try:
        with os.fdopen(fd,"w") as out:
            os.fchown(out.fileno(),info.st_uid,info.st_gid)
            os.fchmod(out.fileno(),0o600)
            json.dump(value,out)
            out.flush()
            os.fsync(out.fileno())
        if read_json_private(marker,8192)!=seal or live_core(root)!=actual:
            raise ValueError("Maintenance or core changed during finalization")
        os.replace(tmp,marker)
        sync_directory(marker.parent)
    finally:Path(tmp).unlink(missing_ok=True)
    return {"outcome":state["phase"],"maintenance_phase":"sealed","production_activation":production and promoted}


# Fixed compare-and-replace on the already verified core's private bind.
FINALIZE_MARKER=r"""
import json,os,sys,tempfile
from pathlib import Path
path=Path("/data/recovery-maintenance.json")
expected,value=map(json.loads,sys.argv[1:])
if json.loads(path.read_text())!=expected or expected.get("phase")!="updating":
    raise RuntimeError("Maintenance hold changed")
fd,tmp=tempfile.mkstemp(prefix=".core-update-finish-",dir=path.parent)
try:
    with os.fdopen(fd,"w") as out:
        json.dump(value,out)
        out.flush()
        os.fsync(out.fileno())
    if json.loads(path.read_text())!=expected:
        raise RuntimeError("Maintenance hold changed")
    os.replace(tmp,path)
    directory=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(directory)
    finally:os.close(directory)
finally:Path(tmp).unlink(missing_ok=True)
"""


# Fixed read-only probe in the actual core/worker containers, not a caller
# supplied shell command. Compose health and exact image checks are separate.
PRODUCTION_PROBE=r"""
import json,sqlite3,sys
from pathlib import Path
service,digest=sys.argv[1:]
if service=="core":
    data=Path("/data")
    marker=json.loads((data/"recovery-maintenance.json").read_text())
    if marker.get("phase")!="updating" or marker.get("candidate_sha256")!=digest:
        raise RuntimeError("Maintenance hold mismatch")
    import urllib.request
    with urllib.request.urlopen("http://127.0.0.1:8080/health",timeout=3) as res:
        if res.status!=200 or json.load(res).get("status")!="ok":
            raise RuntimeError("Core health mismatch")
    db=data/"core.sqlite3"
    tables={"admin","sessions","first_run"}
elif service=="worker":
    db=Path("/worker-state/jobs.sqlite3")
    tables={"jobs","sharing","batches"}
else:
    raise RuntimeError("Unexpected service")
with sqlite3.connect(db.as_uri()+"?mode=ro",uri=True,timeout=3) as con:
    con.execute("PRAGMA trusted_schema=OFF")
    if con.execute("PRAGMA quick_check").fetchmany(2)!=[("ok",)]:
        raise RuntimeError("Database integrity check failed")
    if not tables<={r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}:
        raise RuntimeError("Expected application schema unavailable")
"""


def probe_reviewed_update(root,candidate,images,override=None):
    actual=live_core(root,override)
    if any(actual[name]["image"]!=images[name]["image"] for name in ("core","worker")):
        raise ValueError("Candidate image identity changed")
    digest=assets.sha256_file(candidate/"candidate.json")
    for name in ("core","worker"):
        assets.docker("exec",actual[name]["container"],"python3","-I","-B","-c",
                      PRODUCTION_PROBE,name,digest,timeout=45)
    if live_core(root,override)!=actual:
        raise ValueError("Candidate container identity changed")


def execute_reviewed_update(root,candidate,expected_digest,*,detached=False):
    """One explicitly approved host-owned transaction, no automatic retry.

    Run outside both core services. A failed or ambiguous operation leaves
    the durable hold for inspection; only a validated terminal outcome may
    return it to sealed maintenance.
    """
    root,candidate=production_scope(root,candidate)
    if not isinstance(expected_digest,str) or not SHA.fullmatch(expected_digest):
        raise ValueError("Exact confirmed candidate digest required")
    if assets.sha256_file(candidate/"candidate.json")!=expected_digest:
        raise ValueError("Confirmed candidate changed")
    plan=read_json_private(candidate/"candidate.json")
    for name in ("activation.json","promotion.json","production-dispatch.json"):
        path=candidate/name
        if path.exists() or path.is_symlink():
            raise ValueError("Update already attempted; inspect its outcome")
    check_activation(root,candidate)
    dispatch=candidate/"production-dispatch.json"
    state={"format":1,"phase":"starting","candidate_sha256":expected_digest}
    # Exclusive file creation is the no-replay admission boundary. Persist
    # before the first service stop; never automatically remove this receipt.
    write_private_json(dispatch,state)
    sync_directory(candidate)
    try:
        state["phase"]="trial"
        journal(dispatch,state)
        candidate_trial(root,candidate,lambda:probe_reviewed_update(
            root,candidate,plan["candidate"],candidate/"trial-compose.json"),production=True)
        state["phase"]="promotion"
        journal(dispatch,state)
        try:
            promote_disposable(root,candidate,lambda:probe_reviewed_update(
                root,candidate,plan["candidate"]),production=True,**({"container_mutations":True} if detached else {}))
        except Exception:
            # Only the verified terminal rollback can be finalized. Other
            # phases remain held for explicit support reconciliation.
            result=read_json_private(candidate/"promotion.json")
            if result.get("phase")!="rolled_back":
                raise
        result=finish_disposable_promotion(root,candidate,production=True,**({"detached":True} if detached else {}))
        state["phase"]=result["outcome"]
        journal(dispatch,state)
        return result
    except Exception:
        state["phase"]="requires_inspection"
        journal(dispatch,state)
        raise


# Browser requests select an approved commit or the exact prepared digest,
# never a path, archive URL, image, Docker flag or command.
def browser_releases():
    if PRODUCTION_EXECUTION_ENABLED is not True:
        return []
    return sorted(commit for commit,record in APPROVED_CORE_RELEASES.items()
                  if COMMIT.fullmatch(commit) and isinstance(record,dict)
                  and set(record)=={"archive_sha256","source_sha256"}
                  and all(isinstance(v,str) and SHA.fullmatch(v) for v in record.values()))


def browser_staging():
    staging=assets.real_directory(STAGING)
    info=staging.stat()
    if info.st_uid!=0 or stat.S_IMODE(info.st_mode)!=0o700:
        raise ValueError("Private update staging required")
    return staging


def browser_candidate():
    staging=browser_staging()
    receipt=read_json_private(staging/"browser-candidate.json",4096)
    name=receipt.get("candidate")
    digest=receipt.get("candidate_sha256")
    if (set(receipt)!={"candidate","candidate_sha256"} or not isinstance(name,str)
        or not re.fullmatch(r"[a-f0-9]{40}-[a-f0-9]{12}",name)
        or not isinstance(digest,str) or not SHA.fullmatch(digest)):
        raise ValueError("Invalid reviewed candidate receipt")
    candidate=staging/name
    production_scope(ROOT,candidate)
    if assets.sha256_file(candidate/"candidate.json")!=digest:
        raise ValueError("Reviewed candidate changed")
    return candidate,digest


def browser_prepare(commit):
    if commit not in browser_releases():
        raise ValueError("Release is not approved")
    staging=browser_staging()
    receipt=staging/"browser-candidate.json"
    if receipt.exists() or receipt.is_symlink():
        raise ValueError("Existing candidate requires inspection")
    import urllib.request
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):
            return None
    fd,path=tempfile.mkstemp(prefix=".reviewed-archive-",dir=staging)
    archive=Path(path)
    try:
        client=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
        url="https://codeload.github.com/ramseys1990/AfterGrid/tar.gz/"+commit
        deadline=time.monotonic()+120
        with os.fdopen(fd,"wb") as out,client.open(url,timeout=10) as response:
            size=0
            while True:
                if time.monotonic()>deadline:raise ValueError("Release download timed out")
                chunk=response.read(1024*1024)
                if not chunk:break
                size+=len(chunk)
                if size>SOURCE_LIMIT:raise ValueError("Release archive too large")
                out.write(chunk)
        candidate=prepare(ROOT,staging,archive,commit,APPROVED_CORE_RELEASES[commit]["archive_sha256"])
        production_scope(ROOT,candidate)
        retain_previous(ROOT,candidate)
        digest=assets.sha256_file(candidate/"candidate.json")
        write_private_json(receipt,{"candidate":candidate.name,"candidate_sha256":digest})
        sync_directory(staging)
    finally:archive.unlink(missing_ok=True)


def browser_status():
    releases=browser_releases()
    result={"activation_enabled":bool(releases),"releases":releases,"candidate":None,"outcome":None}
    if not releases:return result
    try:candidate,digest=browser_candidate()
    except FileNotFoundError:return result
    result["candidate"]={"commit":candidate.name.split("-")[0],"candidate_sha256":digest}
    path=candidate/"production-dispatch.json"
    if path.exists() or path.is_symlink():
        record=read_json_private(path)
        if record.get("candidate_sha256")!=digest:raise ValueError("Dispatch receipt changed")
        result["outcome"]=record.get("phase")
    return result


def browser_apply(digest):
    candidate,expected=browser_candidate()
    if digest!=expected:raise ValueError("Confirmed candidate changed")
    return execute_reviewed_update(ROOT,candidate,digest,detached=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive",type=Path,nargs="?",help="Local reviewed GitHub commit tar.gz")
    parser.add_argument("--commit")
    parser.add_argument("--sha256",help="Independently reviewed archive SHA-256")
    modes=parser.add_mutually_exclusive_group()
    modes.add_argument("--check-backups",type=Path,metavar="CANDIDATE",help="Read-only live recovery evidence check")
    modes.add_argument("--retain-previous",type=Path,metavar="CANDIDATE",help="Retain exact prior images without activation")
    modes.add_argument("--check-activation",type=Path,metavar="CANDIDATE",help="Read-only activation prerequisites")
    modes.add_argument("--cancel-claim",type=Path,metavar="CANDIDATE",help="Cancel an unactivated update claim")
    modes.add_argument("--trial-status",type=Path,metavar="CANDIDATE",help="Read-only disposable trial journal status")
    modes.add_argument("--apply-reviewed",type=Path,metavar="CANDIDATE",help="Host-only reviewed production transaction (release-gated)")
    parser.add_argument("--candidate-sha256",help="Exact confirmed candidate digest for apply-reviewed")
    modes.add_argument("--browser-prepare",metavar="COMMIT")
    modes.add_argument("--browser-apply",metavar="DIGEST")
    modes.add_argument("--browser-status",action="store_true")
    args=parser.parse_args()
    if os.geteuid()!=0:parser.error("Run as root on the installed Linux guest")
    if Path("/etc/pve").exists() or shutil.which("pveversion"):parser.error("Do not run on the Proxmox hypervisor")
    try:
        if args.browser_status or args.browser_prepare is not None or args.browser_apply is not None:
            if any((args.archive,args.commit,args.sha256,args.candidate_sha256)):parser.error("Browser operation takes no other arguments")
            if args.browser_status:print(json.dumps(browser_status()))
            elif args.browser_prepare is not None:browser_prepare(args.browser_prepare)
            else:print(json.dumps(browser_apply(args.browser_apply)))
            return
        if args.apply_reviewed is not None:
            if any((args.archive,args.commit,args.sha256)) or not args.candidate_sha256:
                parser.error("Apply requires only a prepared candidate and confirmed candidate digest")
            print(json.dumps(execute_reviewed_update(ROOT,args.apply_reviewed,args.candidate_sha256),indent=2))
            return
        if args.candidate_sha256 is not None:parser.error("Candidate digest is only for apply-reviewed")
        if args.trial_status is not None:
            if any((args.archive,args.commit,args.sha256)):parser.error("Use trial status separately")
            print(json.dumps(inspect_trial(args.trial_status),indent=2))
            return
        if args.check_activation is not None or args.cancel_claim is not None:
            if any((args.archive,args.commit,args.sha256)):parser.error("Use claim commands separately")
            result=check_activation(ROOT,args.check_activation) if args.check_activation is not None else cancel_claim(ROOT,args.cancel_claim)
            print(json.dumps(result,indent=2))
            return
        if args.retain_previous is not None:
            if any((args.archive,args.commit,args.sha256)):parser.error("Use retain-previous separately")
            print(json.dumps(retain_previous(ROOT,args.retain_previous),indent=2))
            return
        if args.check_backups is not None:
            if any((args.archive,args.commit,args.sha256)):parser.error("Use check-backups separately")
            print(json.dumps(check_backups(ROOT,args.check_backups),indent=2))
            return
        if not all((args.archive,args.commit,args.sha256)):parser.error("Archive, exact commit and checksum required")
        destination=prepare(ROOT,STAGING,args.archive,args.commit,args.sha256)
    except (OSError,ValueError,TypeError,KeyError,subprocess.SubprocessError,tarfile.TarError) as exc:
        parser.exit(1,"Core update preparation failed: "+str(exc)+"\n")
    print("Candidate prepared:",destination)
    print("No live containers replaced. Production activation requires a separately approved release.")


if __name__=="__main__":main()

