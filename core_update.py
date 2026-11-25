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
              "activated":False,"rollback_ready":False}
        with (stage/"candidate.json").open("x") as out:json.dump(plan,out,indent=2)
        (stage/"candidate.json").chmod(0o600)
        stage.rename(destination)
        return destination
    finally:
        if stage.exists():shutil.rmtree(stage)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive",type=Path,help="Local reviewed GitHub commit tar.gz")
    parser.add_argument("--commit",required=True)
    parser.add_argument("--sha256",required=True,help="Independently reviewed archive SHA-256")
    args=parser.parse_args()
    if os.geteuid()!=0:parser.error("Run as root on the installed Linux guest")
    if Path("/etc/pve").exists() or shutil.which("pveversion"):parser.error("Do not run on the Proxmox hypervisor")
    try:
        destination=prepare(ROOT,STAGING,args.archive,args.commit,args.sha256)
    except (OSError,ValueError,TypeError,KeyError,subprocess.SubprocessError,tarfile.TarError) as exc:
        parser.exit(1,"Core update preparation failed: "+str(exc)+"\n")
    print("Candidate prepared:",destination)
    print("No live containers replaced. Activation and rollback are not yet enabled.")


if __name__=="__main__":main()
