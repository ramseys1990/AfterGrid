#!/usr/bin/env python3
"""Prepare recovered core/worker state in a new private installation root.

A separate explicit core-only start uses exact imported images and local Compose.
Application data must be restored separately; no optional applications are started.
"""
import argparse
import json
import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import recovery_assets as assets
import recovery_prepare as preparation
from worker import worker

def validate_root(destination):
    destination=Path(destination).absolute()
    assets.real_directory(destination.parent)
    if not re.fullmatch(r"/[a-zA-Z0-9_./-]+",str(destination)) or ".." in destination.parts or destination==Path("/"):
        raise ValueError("Invalid recovery root")
    if destination.exists() or destination.is_symlink():
        raise ValueError("Recovery root must not exist")
    return destination

def copy_release(verified,root):
    source=verified/"release"
    # Asset verification already rejects symlinks and unexpected file types.
    for path in sorted(source.rglob("*")):
        relative=path.relative_to(source)
        target=root/relative
        if path.is_dir():
            target.mkdir(mode=0o700,parents=True,exist_ok=True)
        else:
            assets.copy_file(path,target)
    # Preserve original host settings privately but never activate old addresses.
    (root/".env").rename(root/"recovery-original.env")
    preparation.private_write(root/".env",(
        "AFTERGRID_BIND=127.0.0.1\nAFTERGRID_PORT=8080\n"
        "AFTERGRID_ORIGIN=http://127.0.0.1:8080\nAFTERGRID_SECURE_COOKIE=false\n"
        "AFTERGRID_LAN_BIND=\nAFTERGRID_LAN_DOMAIN=\n"
        "AFTERGRID_ROOT="+str(root)+"\n").encode("ascii"))

def stage(assets_dir,core_dir,worker_dir,destination,core_job,worker_job,worker_sha256):
    if os.geteuid()!=0:raise ValueError("Root required to set recovered file ownership")
    assets_dir=assets.real_directory(assets_dir)
    destination=validate_root(destination)
    if assets_dir==destination or assets_dir in destination.parents:
        raise ValueError("Choose a root separate from the asset archive")
    value=assets.verify(assets_dir)
    rows=assets.recovery_image_rows(value)
    destination.mkdir(mode=0o700)
    try:
        copy_release(assets_dir,destination)
        # Validate secret names against the captured reviewed release.
        old_modules=worker.MODULES
        worker.MODULES=destination/"modules"
        try:
            metadata=preparation.prepare(core_dir,worker_dir,destination/"recovery-prepared",
                                         core_job,worker_job,worker_sha256)
        finally:worker.MODULES=old_modules
        prepared=destination/"recovery-prepared"
        (destination/"data").mkdir(mode=0o700)
        (prepared/"core").rename(destination/"data/core")
        (prepared/"worker-state").rename(destination/"recovery-worker-state")
        (prepared/"recovery-metadata.json").rename(destination/"recovery-metadata.json")
        prepared.rmdir()
        # Core runs as UID/GID 10001; worker state remains root-only.
        data=destination/"data/core"
        os.chown(data,10001,10001)
        for path in data.iterdir():
            if not stat.S_ISREG(path.lstat().st_mode):raise ValueError("Unexpected core recovery file")
            os.chown(path,10001,10001)
        for name in ("kiwix","maps","routing","media"):
            path=destination/"content"/name
            path.mkdir(parents=True,mode=0o755)
            path.chmod(0o755)
            os.chown(path,10001,10001)
        # This is a placeholder for core-only acceptance, not recovered content.
        # Never substitute it for the original library during application recovery.
        library=destination/"content/kiwix/library.xml"
        assets.copy_file(destination/"modules/kiwix/library.xml",library)
        library.chmod(0o644)
        os.chown(library,10001,10001)
        overrides=destination/"recovery-overrides"
        assets.write_overrides(value,overrides)
        override=overrides/"aftergrid-core.json"
        config=json.loads(override.read_text())
        for service in ("core","worker"):
            config["services"][service]["environment"]={"AFTERGRID_RECOVERY_CORE_ONLY":"1"}
        # Compose merges volumes by target, replacing the named worker-state
        # mount with the private recovered directory. No volume seeding container.
        config["services"]["worker"]["volumes"]=[
            {"type":"bind","source":str(destination/"recovery-worker-state"),
             "target":"/worker-state","bind":{"create_host_path":False}}]
        override.write_text(json.dumps(config,indent=2))
        plan={"format":1,"platform":value["platform"],"root":str(destination),
              "assets_manifest_sha256":assets.sha256_file(assets_dir/"assets-manifest.json"),
              "images":rows,"core_job":core_job,"worker_job":worker_job,
              "content_metadata_included":metadata["content_metadata_included"],
              "core_only":True,"application_data_restored":False,"complete_recovery":False}
        preparation.private_write(destination/"recovery-install-plan.json",json.dumps(plan,indent=2).encode())
        return plan
    except Exception:
        # This path was exclusively created by this function.
        shutil.rmtree(destination)
        raise

def compose_command(root):
    return ["docker","compose","--project-name","aftergrid-core","--project-directory",str(root),
            "--env-file",str(root/".env"),"--file",str(root/"compose.yaml"),
            "--file",str(root/"recovery-overrides/aftergrid-core.json")]

def start_core(root,assets_dir,confirmed=False):
    if os.geteuid()!=0 or confirmed is not True:raise ValueError("Confirm core-only recovery on replacement host as root")
    root=assets.real_directory(root)
    assets_dir=assets.real_directory(assets_dir)
    value=assets.verify(assets_dir)
    plan=json.loads(preparation.read_private(root/"recovery-install-plan.json",65536))
    rows=assets.recovery_image_rows(value)
    if plan.get("format")!=1 or plan.get("root")!=str(root) or plan.get("images")!=rows or plan.get("assets_manifest_sha256")!=assets.sha256_file(assets_dir/"assets-manifest.json") or plan.get("core_only") is not True:
        raise ValueError("Recovery plan mismatch")
    if assets.local_docker()!=value["platform"]:raise ValueError("Architecture mismatch")
    # Refuse existing containers, AfterGrid volumes and network; do not
    # replace or attach to resources from a previous installation.
    if assets.docker("ps","--all","--quiet"):
        raise ValueError("Replacement host contains existing containers")
    if any(name.startswith("aftergrid-") for name in assets.docker("volume","ls","--format","{{.Name}}").splitlines()):
        raise ValueError("Existing AfterGrid volume")
    if any(name.startswith("aftergrid-") for name in assets.docker("network","ls","--format","{{.Name}}").splitlines()):
        raise ValueError("Existing AfterGrid network")
    expected={r["service"]:r for r in rows if r["project"]=="aftergrid-core"}
    for r in expected.values():
        if json.loads(assets.docker("image","inspect","--format","{{json .Id}}",r["recovery_tag"]))!=r["image_id"]:
            raise ValueError("Imported core image mismatch")
        if assets.docker("image","inspect","--format",'{{index .Config.Labels "org.aftergrid.recovery-core-only"}}',r["recovery_tag"])!="1":
            raise ValueError("Captured core images lack recovery-only write protection; capture compatible images first")
    # The original release and generated override must still resolve to
    # the exact local images and expected bind mounts. Ignore caller env.
    env={"PATH":os.environ["PATH"],"HOME":"/root","DOCKER_HOST":"unix:///var/run/docker.sock"}
    cmd=compose_command(root)
    def run(*args,timeout=30):
        return subprocess.run([*cmd,*args],env=env,capture_output=True,text=True,timeout=timeout,check=True).stdout
    config=json.loads(run("config","--format","json"))
    services=config["services"]
    if set(services)!=set(expected):raise ValueError("Unexpected recovery services")
    for name,definition in services.items():
        if definition.get("image")!=expected[name]["recovery_tag"] or definition.get("pull_policy")!="never":
            raise ValueError("Recovery Compose image policy mismatch")
        if definition.get("environment",{}).get("AFTERGRID_RECOVERY_CORE_ONLY")!="1":
            raise ValueError("Recovery-only write guard missing")
    volumes=[v for v in services["worker"]["volumes"] if v.get("target")=="/worker-state"]
    if len(volumes)!=1 or volumes[0].get("type")!="bind" or volumes[0].get("source")!=str(root/"recovery-worker-state"):
        raise ValueError("Recovery worker bind mismatch")
    ports=services["core"].get("ports",[])
    if len(ports)!=1 or ports[0].get("host_ip")!="127.0.0.1" or str(ports[0].get("published"))!="8080":
        raise ValueError("Recovery portal must be loopback only")
    run("up","-d","--no-build","--pull","never","--wait","--wait-timeout","120",timeout=180)
    # Compare actual running image IDs, not just tags or configuration.
    for name,row in expected.items():
        cid=run("ps","-q",name).strip()
        if not re.fullmatch(r"[a-f0-9]{12,64}",cid):raise ValueError("Recovered container missing")
        if json.loads(assets.docker("container","inspect","--format","{{json .Image}}",cid))!=row["image_id"]:
            raise ValueError("Recovered container image mismatch")
    return plan

def main():
    os.umask(0o077)
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="action",required=True)
    prepare=sub.add_parser("stage")
    prepare.add_argument("--assets",required=True,type=Path)
    prepare.add_argument("--core-dir",required=True,type=Path)
    prepare.add_argument("--worker-dir",required=True,type=Path)
    prepare.add_argument("--destination",required=True,type=Path)
    prepare.add_argument("--core-job",required=True,type=int)
    prepare.add_argument("--worker-job",required=True,type=int)
    prepare.add_argument("--worker-sha256",required=True)
    start=sub.add_parser("start-core")
    start.add_argument("--root",required=True,type=Path)
    start.add_argument("--assets",required=True,type=Path)
    start.add_argument("--confirm-core-only",action="store_true")
    args=parser.parse_args()
    try:
        if args.action=="stage":
            stage(args.assets,args.core_dir,args.worker_dir,args.destination,args.core_job,args.worker_job,args.worker_sha256)
            print("Private replacement core and worker staged. No services started; application data not restored.")
        else:
            start_core(args.root,args.assets,args.confirm_core_only)
            print("Recovered core healthy on http://127.0.0.1:8080. Optional applications are not restored or started.")
    except Exception:
        parser.exit(1,"Recovery operation refused or failed. Check inputs, ownership, local Docker, image IDs and existing resources. A failed start may leave replacement containers; inspect manually.\n")

if __name__=="__main__":
    main()
