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
            keys=call(old,"/api/admin/backups/policy-sources")
            assert "core" in keys and "content/kiwix" in keys and "application/tak" not in keys
            for key in ("global","content/kiwix"):
                policy=call(old,"/api/admin/backups/effective-policy/"+key)
                assert policy["key"]==key and policy["managed_scheduling_enabled"] is False
                assert policy["policy"]["retention"]["keepLatest"] is not None
            # Exercise real scheduler admission and exact native verification
            # without waiting an entire day. Only the disposable fixture changes
            # the due timestamp on disk; the production API has no force-due knob.
            call(old,"/api/admin/backups/schedules",{"key":"core","interval":"daily","enabled":True,"confirmed":True})
            schedule_path=original/"data/core/backup-schedules.json"
            schedule_state=json.loads(schedule_path.read_text())
            schedule_state["sources"]["core"]["next_due"]=0
            schedule_path.write_text(json.dumps(schedule_state))
            deadline=time.monotonic()+150
            while time.monotonic()<deadline:
                row=call(old,"/api/admin/backups/schedules")["sources"]["core"]
                if row["verification"]=="succeeded":break
                if not row["enabled"]:raise RuntimeError("Scheduled native verification failed or ambiguous")
                time.sleep(2)
            else:raise RuntimeError("Scheduled native verification timed out")
            assert row["source_job"]<row["job"]
            assert not any("aftergrid-core-"+str(row["job"])+"-" in p.name for p in (original/"restore").iterdir())
            call(old,"/api/admin/backups/schedules",{"key":"core","interval":"daily","enabled":False,"confirmed":True})
            # Explicit protected capture: native pin at creation and exact ID
            # remains valid for subsequent verification and inventory lookup.
            protected=post_job(old,"/api/admin/backups/protected-snapshot",{"key":"core","confirmed":True})
            post_job(old,"/api/admin/backups/core/verify-snapshot",{"confirmed":True})
            post_job(old,"/api/admin/backups/recovery-manifest",{"confirmed":True})
            protected_record=next(r for r in call(old,"/api/admin/backups/recovery-manifest")["records"] if r["key"]=="core")
            assert protected_record["snapshot_job"]==protected["id"]
            assert protected_record["aftergrid_pinned"] is True and protected_record["verification"]=="isolated"
            # Change one source only after fresh protected verification.
            effective=call(old,"/api/admin/backups/effective-policy/core")["policy"]
            expected=effective["retention"]
            counts={**expected,"keepLatest":expected["keepLatest"]+1}
            post_job(old,"/api/admin/backups/retention",{"key":"core","expected":expected,"counts":counts,"confirmed":True})
            assert call(old,"/api/admin/backups/effective-policy/core")["policy"]["retention"]==counts
            post_job(old,"/api/admin/backups/recovery-manifest",{"confirmed":True})
            retained=next(r for r in call(old,"/api/admin/backups/recovery-manifest")["records"] if r["key"]=="core")
            assert retained["snapshot_id"]==protected_record["snapshot_id"] and retained["aftergrid_pinned"] is True
            health=call(old,"/api/admin/backups/health")
            core_health=next(r for r in health["sources"] if r["key"]=="core")
            assert health["repository"]["connection"]=="connected" and not health["complete_recovery_certified"]
            assert core_health["snapshot_job"]==protected["id"] and core_health["verified"]
            assert core_health["pin_at_inventory"] is True and core_health["repository_at_inventory"]=="present"
            assert core_health["schedule"]["status"]=="disabled"
            eligibility=call(old,"/api/admin/modules/kiwix/update-eligibility")
            assert eligibility["status"]=="no approved update" and not eligibility["automatic_execution_enabled"]
            update_health=call(old,"/api/admin/updates/health")
            assert update_health["approved_candidate"] is None and update_health["reader_state"]=="running"
            assert update_health["rollback_hold"]["status"]=="none" and update_health["latest_guarded_update"] is None
            assert not update_health["registry_checked"] and not update_health["automatic_execution_enabled"]
            assert call(old,"/api/admin/modules/kiwix/update-preparation")["latest"] is None
            call(old,"/api/admin/modules/kiwix/update-preparation",{"candidate":"ghcr.io/kiwix/kiwix-serve:3.8.2@sha256:"+"c"*64,
                 "platform":"linux/amd64","previous_image_id":"sha256:"+"a"*64,"target_image_id":"sha256:"+"b"*64,"confirmed":True},400)
            call(old,"/api/admin/modules/kiwix/guarded-update",{"candidate":"ghcr.io/kiwix/kiwix-serve:3.8.2@sha256:"+"c"*64,
                 "platform":"linux/amd64","previous_image_id":"sha256:"+"a"*64,"target_image_id":"sha256:"+"b"*64,"confirmed":True},400)
            # Exercise the local image preservation helper in the disposable
            # worker against the real running reader, without approving a
            # production update candidate or deleting any image.
            saved=json.loads(run(cmd,"exec","-T","worker","python3","-c",
                "import worker,json; i=worker.version_report('kiwix')['services'][0]['installed_image_ids'][0]; print(json.dumps(worker.preserve_previous_image(i)))",
                timeout=180))
            assert saved["image_id"] in {r["image_id"] for r in recover.source_containers(original).values()}
            assert saved["bytes"]>0 and re.fullmatch(r"[a-f0-9]{64}",saved["sha256"])
            # Load the exact saved archive without deleting or pruning anything.
            run(cmd,"exec","-T","worker","python3","-c",
                "import worker,sys,subprocess; i=sys.argv[1]; p=worker.STATE/'previous-images'/('kiwix-'+i.split(':')[1]); worker.verify_previous_archive(p,i); subprocess.run(['docker','image','load','--input',str(p/'image.tar')],check=True); assert subprocess.check_output(['docker','image','inspect','--format','{{.Id}}',i],text=True).strip()==i",
                saved["image_id"],timeout=180)
            # Test native local reader restoration and the persistent override
            # in a disposable installation only; no production candidate.
            # Use the existing verified Kiwix content record or generate one.
            rollback_capture=post_job(old,"/api/admin/backups/protected-snapshot",{"key":"content/kiwix","confirmed":True})
            post_job(old,"/api/admin/backups/content/kiwix/verify",{"confirmed":True})
            post_job(old,"/api/admin/backups/recovery-manifest",{"confirmed":True})
            rb=next(r for r in call(old,"/api/admin/backups/recovery-manifest")["records"] if r["key"]=="content/kiwix")
            assert rb["snapshot_job"]==rollback_capture["id"] and rb["aftergrid_pinned"] is True and rb["verification"]=="read-only"
            # Native helper exercised with actual preserved image and catalog.
            run(cmd,"exec","-T","worker","python3","-c",
                "import worker,json,sys,hashlib; a=json.loads(sys.argv[1]); i=a['image_id']; sample=worker.kiwix_catalog_sample(); e={'recreation_attempted':True,'compose_sha256':worker.reader_compose_fingerprint(),'previous_image_archive':a,'snapshot_id':sys.argv[2],'catalog_sample_sha256':hashlib.sha256(json.dumps(sample).encode()).hexdigest()}; worker.rollback_reader(999999,{'previous_image_id':i},e); assert e['rollback_status']=='restored'; assert worker.kiwix_rollback_override()[1]==i",
                json.dumps(saved),rb["snapshot_id"],timeout=240)
            assert reader_fixture()
            # Fixture-only cleanup: restore unchanged reviewed config before
            # recovery package acceptance. No production hold-clear endpoint.
            run(cmd,"exec","-T","worker","python3","-c","import worker; worker.kiwix_rollback_override()[0].unlink()")
            post_job(old,"/api/admin/modules/kiwix/start")
            assert reader_fixture()
            # Positive version transition on this exclusive disposable host.
            # The repository's production candidate remains null. Resolve the
            # fixed older test release to its actual local identity and use a
            # temporary override only to start the old container. The normal
            # guarded job must use the original reviewed digest-pinned target.
            module_dir=original/"modules/kiwix"
            candidate_path=module_dir/"update-candidate.json"
            original_candidate=candidate_path.read_bytes()
            assert json.loads(original_candidate)["candidate"] is None
            override=module_dir/"ci-prior-image.json"
            versions=call(old,"/api/admin/modules/kiwix/versions")["services"]
            assert len(versions)==1 and versions[0]["service"]=="kiwix"
            target=versions[0]["configured_image"]
            target_id=versions[0]["installed_image_ids"][0]
            assert re.fullmatch(r"ghcr[.]io/kiwix/kiwix-serve:3[.]8[.]2@sha256:[a-f0-9]{64}",target)
            prior="ghcr.io/kiwix/kiwix-serve:3.8.1"
            run(["docker"],"pull",prior,timeout=180)
            prior_info=json.loads(run(["docker"],"image","inspect",prior))[0]
            prior_id=prior_info["Id"]
            prior_refs=[ref for ref in prior_info["RepoDigests"] if re.fullmatch(
                r"ghcr[.]io/kiwix/kiwix-serve@sha256:[a-f0-9]{64}",ref)]
            assert len(prior_refs)==1 and prior_id!=target_id
            assert re.fullmatch(r"sha256:[a-f0-9]{64}",prior_id)
            platform=run(["docker"],"version","--format","{{.Server.Os}}/{{.Server.Arch}}").decode().strip()
            assert platform in {"linux/amd64","linux/arm64"}
            content_root=original/"content/kiwix"
            before_content={name:assets.sha256_file(content_root/name) for name in ("fixture.zim","library.xml")}
            before_catalog=sorted(entry.findtext("{http://www.w3.org/2005/Atom}id") for entry in reader_fixture())
            assert before_catalog
            try:
                override.write_text(json.dumps({"services":{"kiwix":{"image":prior_refs[0],"pull_policy":"never"}}}))
                run(["docker","compose","--project-name","aftergrid-kiwix","--project-directory",str(module_dir),
                     "--env-file",str(original/".env"),"--file",str(module_dir/"compose.yaml"),"--file",str(override)],
                    "up","-d","--no-build","--pull","never","--wait","--wait-timeout","90")
                deadline=time.monotonic()+90
                while time.monotonic()<deadline:
                    try:
                        if reader_fixture():break
                    except OSError:pass
                    time.sleep(2)
                else:raise RuntimeError("Prior version reader not ready")
                override.unlink()
                local=call(old,"/api/admin/modules/kiwix/versions")["services"][0]
                assert local["configured_image"]==target and local["installed_image_ids"]==[prior_id]
                candidate_path.write_text(json.dumps({"format":1,"candidate":{"image":target,
                    "platforms":{platform:{"from":[prior_id],"to":target_id}}}}))
                eligibility=call(old,"/api/admin/modules/kiwix/update-eligibility",{})
                assert eligibility["status"]=="reviewed candidate confirmed" and eligibility["platform"]==platform
                assert eligibility["installed_image_ids"]==[prior_id] and eligibility["expected_target_image_id"]==target_id
                guarded=post_job(old,"/api/admin/modules/kiwix/guarded-update",{"candidate":target,
                    "platform":platform,"previous_image_id":prior_id,"target_image_id":target_id,"confirmed":True})
                history=call(old,"/api/admin/updates/health")
                attempt=history["latest_guarded_update"]
                assert attempt["id"]==guarded["id"] and attempt["state"]=="succeeded"
                evidence=attempt["evidence"]
                assert evidence["pin_confirmed"] and evidence["verification"]=="read-only"
                assert evidence["previous_image_archive"]["image_id"]==prior_id
                assert evidence["update_performed"] and evidence["catalog_sample_matched"]
                assert evidence["result_image_id"]==target_id and history["rollback_hold"]["status"]=="none"
                assert history["local_images"][0]["installed_image_ids"]==[target_id]
                assert sorted(entry.findtext("{http://www.w3.org/2005/Atom}id") for entry in reader_fixture())==before_catalog
                assert {name:assets.sha256_file(content_root/name) for name in before_content}==before_content
                print("Positive native Kiwix version transition and exact recovery evidence passed.",flush=True)
            finally:
                override.unlink(missing_ok=True)
                candidate_path.write_bytes(original_candidate)
            # Exercise the real fresh-capture coordinator through the authenticated portal.
            other=client()
            call(other,"/api/login",creds)
            # Report only fixed diagnostic categories for failed capture jobs.
            # Never emit raw worker logs, paths, native credentials or snapshots.
            reported_failures=set()
            def capture_call(path,payload=None):
                status=202 if payload is not None and "/recovery-maintenance/" not in path else 200
                result=call(old,path,payload,status)
                if path=="/api/admin/jobs" and payload is None:
                    for row in result:
                        if row["state"] not in {"failed","interrupted"} or row["id"] in reported_failures:
                            continue
                        reported_failures.add(row["id"])
                        output=row.get("log","") or ""
                        categories=(("Content maintenance guard refused","content guard"),
                            ("Connect Kopia repository first","repository connection"),
                            ("Reviewed source directory unavailable in Kopia","source directory"),
                            ("Native Kopia snapshot exited with code","native snapshot exit"),
                            ("Native Kopia snapshot timed out","native snapshot timeout"),
                            ("Native Kopia snapshot JSON missing or invalid","snapshot JSON"),
                            ("Kopia manifest omitted required snapshot statistics","snapshot statistics"),
                            ("Kopia reported an incomplete snapshot","incomplete snapshot"),
                            ("Kopia snapshot source did not match","snapshot source"),
                            ("Kopia snapshot ID missing or invalid","snapshot ID"),
                            ("Kopia snapshot root missing","snapshot root"),
                            ("Kopia snapshot counter unavailable","snapshot counter"),
                            ("Kopia snapshot reports","snapshot completeness"),
                            ("Kopia snapshot is empty or file count unavailable","snapshot file count"),
                            ("Native content verification failed or incomplete","content verification"))
                        category=next((label for marker,label in categories if marker in output),"unclassified")
                        print(f"Capture failure: job {row['id']} {row['module']}/{row['action']} "
                              f"progress {row['completed']}/{row['total']}; category={category}",flush=True)
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
