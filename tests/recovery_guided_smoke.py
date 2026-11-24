"""Disposable CI: actual managed Kopia snapshots -> guided recovery -> activation.

The archive import fixture separately tests Docker load. Here reuse exact
local image IDs, never remove or prune images from the runner.
"""
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import recover
import recovery_assets as assets
import recovery_install as install
from recovery_core_smoke import BASE,call,client

def wait_job(c,job):
    deadline=time.monotonic()+240
    while time.monotonic()<deadline:
        row=next(j for j in call(c,"/api/admin/jobs") if j["id"]==job)
        if row["state"]=="succeeded":
            assert row["completed"]==row["total"]
            return row
        if row["state"] in {"failed","interrupted"}:
            # Do not print native job output (may include private diagnostics).
            raise RuntimeError("Managed fixture job failed: "+row["module"]+"/"+row["action"])
        time.sleep(1)
    raise RuntimeError("Managed fixture job timed out")

def post_job(c,path,payload=None):
    return wait_job(c,call(c,path,payload if payload is not None else {},202)["id"])

def repository_digest(root):
    return {p.relative_to(root).as_posix():assets.sha256_file(p)
            for p in root.rglob("*") if p.is_file()}

def reader_fixture():
    with urllib.request.urlopen("http://127.0.0.1:8081/catalog/v2/entries",timeout=10) as response:
        return ET.fromstring(response.read()).findall("{http://www.w3.org/2005/Atom}entry")

def main(fixture,exported=None):
    if os.geteuid()!=0 or os.environ.get("AFTERGRID_DISPOSABLE_RECOVERY_TEST")!="1":
        raise RuntimeError("Disposable CI only")
    if assets.docker("ps","--all","--quiet"):raise RuntimeError("Expected no containers")
    for kind in ("network","volume"):
        if any(x.startswith("aftergrid-") for x in assets.docker(kind,"ls","--format","{{.Name}}").splitlines()):
            raise RuntimeError("Existing AfterGrid resources")
    fixture=Path(fixture).resolve(strict=True)
    if exported is not None:
        exported=install.validate_root(Path(exported))
        exported.mkdir(mode=0o700)
    original_source=Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="aftergrid-guided-ci-") as tmp:
        tmp=Path(tmp)
        original=tmp/"original"
        root=tmp/"replacement"
        original.mkdir(mode=0o700)
        for name in assets.SOURCE_DIRS:shutil.copytree(original_source/name,original/name)
        for name in assets.TOP_FILES:
            if (original_source/name).is_file():shutil.copy2(original_source/name,original/name)
        (original/".env").write_text("AFTERGRID_BIND=127.0.0.1\nAFTERGRID_PORT=8080\nAFTERGRID_ORIGIN="+BASE+"\nAFTERGRID_ROOT="+str(original)+"\n")
        for relative in ("data/core","content/kiwix","content/maps","content/routing","content/media"):
            p=original/relative
            p.mkdir(parents=True)
            p.chmod(0o700 if relative=="data/core" else 0o755)
            os.chown(p,10001,10001)
        for source,name in ((fixture,"fixture.zim"),(original/"modules/kiwix/library.xml","library.xml")):
            target=original/"content/kiwix"/name
            shutil.copyfile(source,target)
            os.chown(target,10001,10001)
            target.chmod(0o644)
        token=secrets.token_hex(24)
        setup=original/"data/core/setup-token"
        setup.write_text(token)
        setup.chmod(0o600)
        os.chown(setup,10001,10001)
        creds={"username":"admin","password":secrets.token_hex(24)}
        cmd=["docker","compose","--project-name","aftergrid-core","--project-directory",str(original),
             "--file",str(original/"compose.yaml"),"--env-file",str(original/".env")]
        def run(argv,*args,timeout=180):
            return subprocess.run([*argv,*args],check=True,capture_output=True,timeout=timeout).stdout
        def cleanup_modules():
            # Only fixed, reviewed project/service labels in this exclusive CI fixture.
            for ident in ("kiwix","kopia"):
                ids=assets.docker("ps","--all","--quiet","--filter","label=com.docker.compose.project=aftergrid-"+ident).splitlines()
                for cid in ids:
                    if re.fullmatch(r"[a-f0-9]{12,64}",cid):
                        subprocess.run(["docker","rm","-f",cid],check=True,capture_output=True,timeout=60)
        try:
            run(cmd,"up","-d","--no-build","--pull","never","--wait","--wait-timeout","120")
            old=client()
            call(old,"/api/setup",{**creds,"token":token,"server_name":"Guided recovery fixture"},201)
            call(old,"/api/admin/first-run",{"modules":[]},202)
            call(old,"/api/admin/households",{"name":"Guided household"})
            # Images are pre-pulled by CI. Start uses normal native lifecycle
            # without another registry pull.
            for ident in ("kiwix","kopia"):post_job(old,"/api/admin/modules/"+ident+"/start")
            call(old,"/api/admin/content/local",{"name":"fixture.zim","action":"index"})
            deadline=time.monotonic()+60
            while not reader_fixture():
                if time.monotonic()>deadline:raise RuntimeError("Original reader did not index fixture")
                time.sleep(1)
            password=call(old,"/api/admin/kopia/credentials",{})["repository_password"]
            post_job(old,"/api/admin/kopia/initialize",{"confirmed":True})
            # Exercise the real fresh-capture coordinator through the authenticated portal.
            other=client()
            call(other,"/api/login",creds)
            def capture_call(path,payload=None):
                status=202 if payload is not None and "/recovery-maintenance/" not in path else 200
                result=call(old,path,payload,status)
                if path.endswith("/recovery-maintenance/begin"):
                    assert call(other,"/api/admin/backups/core/snapshot",{"confirmed":True},409)["detail"]
                    assert call(old,"/api/admin/households",{"name":"Must be blocked"},409)["detail"]
                return result
            repository=original/"backups"
            package=(exported if exported is not None else tmp)/"package"
            packed=recover.create_package(capture_call,original,package,["kiwix"],password,job_timeout=240)
            assert recover.verify_package(package)==packed and packed["omitted_captured"]==[]
            assert not (original/"recovery-source-restart.json").exists()
            assert all(row["state"]=="running" for row in recover.source_containers(original).values())
            # Wait for original source portal and reader to be available again.
            deadline=time.monotonic()+60
            while True:
                try:
                    if call(old,"/api/admin/recovery-maintenance")["phase"]=="sealed" and reader_fixture():break
                except OSError:pass
                if time.monotonic()>deadline:raise RuntimeError("Original source restart not ready")
                time.sleep(1)
            assert call(old,"/api/admin/households",{"name":"Must be blocked"},409)["detail"]
            assert call(old,"/api/admin/modules/kiwix/stop",{},409)["detail"]
            inventory=package/"inventory.json"
            capture=json.loads(inventory.read_text())
            assert capture["atomic"] is False
            assert recover.core_records(inventory)["worker"]["verification_job"]>recover.core_records(inventory)["worker"]["snapshot_job"]
            # Release explicitly after source readiness; stop again for the
            # separate clean replacement drill. Do not assume native Kopia
            # maintenance cannot change the restarted original repository.
            call(old,"/api/admin/recovery-maintenance/release",{"confirmed":True})
            assert not call(old,"/api/status")["recovery_maintenance"]
            for ident in ("kiwix","kopia"):post_job(old,"/api/admin/modules/"+ident+"/stop")
            run(cmd,"stop")
            before=repository_digest(repository)
            assert before
            # A modified inventory must be rejected before any replacement actions.
            packaged_inventory=package/"inventory.json"
            saved_inventory=packaged_inventory.read_bytes()
            try:
                packaged_inventory.write_bytes(saved_inventory+b"\n")
                try:
                    recover.verify_package(package)
                except ValueError as exc:
                    assert "checksum mismatch" in str(exc)
                else:
                    raise AssertionError("Tampered package accepted")
            finally:
                packaged_inventory.write_bytes(saved_inventory)
            assert recover.verify_package(package)==packed
            assert repository_digest(repository)==before
            bundle=package/"assets"
            inventory=package/"inventory.json"
            # Original is quiescent, and the recovery command reads only the copy.
            cleanup_modules()
            run(cmd,"down","-v")
            def reuse_exact_images(directory,confirmed):
                assert confirmed is True and not assets.docker("ps","--all","--quiet")
                rows=assets.recovery_image_rows(assets.verify(directory))
                for row in rows:
                    assert json.loads(assets.docker("image","inspect","--format","{{json .Id}}",row["image_id"]))==row["image_id"]
                    assets.docker("image","tag",row["image_id"],row["recovery_tag"])
                return rows
            with patch.object(assets,"import_images",reuse_exact_images):
                report=recover.restore_package(root,package,password)
            assert report["guarded"] and not report["complete_recovery"] and report["repository_readonly"]
            assert report["omitted_captured"]==[]
            assert not call(old,"/api/status")["admin"]
            fresh=client()
            assert call(fresh,"/api/status")["recovery_core_only"]
            assert not call(fresh,"/api/status")["recovery_maintenance"]
            call(fresh,"/api/login",creds)
            assert call(fresh,"/api/households")["households"][0]["name"]=="Guided household"
            assert call(fresh,"/api/admin/kopia/status")["connection"]=="connected"
            assert (root/"content/kiwix/fixture.zim").read_bytes()==fixture.read_bytes()
            assert reader_fixture()
            assert repository_digest(repository)==before
            assert call(fresh,"/api/admin/modules/kiwix/stop",{},409)["detail"]
            # Native writable opt-in is only allowed on the independent copy
            # while the guarded core is still active.
            recover.enable_backups(root,bundle,inventory)
            assert repository_digest(repository)==before
            recover.activate(root,bundle,inventory)
            status=call(fresh,"/api/status")
            assert status["recovery_offline"] and not status["recovery_core_only"]
            post_job(fresh,"/api/admin/modules/kiwix/stop")
            post_job(fresh,"/api/admin/modules/kiwix/start")
            assert reader_fixture()
            assert call(fresh,"/api/admin/kopia/status")["connection"]=="connected"
            for path in ("/api/admin/modules/kiwix/update","/api/admin/modules/maps/install","/api/admin/content/downloads"):
                assert call(fresh,path,{},409)["detail"]
            post_job(fresh,"/api/admin/backups/core/snapshot",{"confirmed":True})
            post_job(fresh,"/api/admin/backups/core/verify-snapshot",{"confirmed":True})
            assert repository_digest(repository)==before
            assert recover.verify_package(package)==packed
            if exported is not None:
                recover.prep.private_write(exported/"acceptance.json",json.dumps({
                    "credentials":creds,"repository_password":password,
                    "fixture_sha256":assets.sha256_file(fixture)
                }).encode())
            print("Portable package verified before and after recovery; snapshot capture points remain independent.",flush=True)
            print("Recovered writable copy: new managed core snapshot and isolated restore passed.",flush=True)
            print("Guided recovery passed: real native snapshots, exact local images, original login, household, Kiwix bytes and catalog, read-only Kopia reconnect, offline activation and lifecycle, original repository unchanged.",flush=True)
        finally:
            cleanup_modules()
            if (root/"recovery-overrides/aftergrid-core.json").is_file():
                subprocess.run([*install.compose_command(root),"down","-v"],capture_output=True,timeout=90)
            subprocess.run([*cmd,"down","-v"],capture_output=True,timeout=90)

if __name__=="__main__":
    if len(sys.argv) not in (2,3):raise SystemExit("Pinned ZIM fixture and optional private CI export path required")
    main(sys.argv[1],sys.argv[2] if len(sys.argv)==3 else None)
