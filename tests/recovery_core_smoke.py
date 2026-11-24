"""Disposable CI only: native core export -> asset capture -> replacement startup.

Reuses locally built images in the disposable runner. The separate native
archive fixture tests Docker load; this test does not clear the runner daemon.
"""
import hashlib
import http.cookiejar
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import urllib.error
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import recovery_assets as assets
import recovery_install as recovery

BASE="http://127.0.0.1:8080"

def call(client,path,payload=None,status=200):
    req=urllib.request.Request(BASE+path,
        data=None if payload is None else json.dumps(payload).encode(),
        headers={"Origin":BASE,"Content-Type":"application/json"})
    try:
        with client.open(req,timeout=30) as res:
            assert res.status==status
            return json.load(res)
    except urllib.error.HTTPError as exc:
        if exc.code!=status:raise
        return json.load(exc)

def client():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}),
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

def main():
    if os.geteuid()!=0 or os.environ.get("AFTERGRID_DISPOSABLE_RECOVERY_TEST")!="1":
        raise RuntimeError("Disposable CI only")
    if assets.docker("ps","--all","--quiet"):raise RuntimeError("Expected no containers")
    if any(x.startswith("aftergrid-") for x in assets.docker("network","ls","--format","{{.Name}}").splitlines()):raise RuntimeError("Existing AfterGrid network")
    if any(x.startswith("aftergrid-") for x in assets.docker("volume","ls","--format","{{.Name}}").splitlines()):raise RuntimeError("Existing AfterGrid volume")
    source=Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="aftergrid-recovery-ci-") as tmp:
        tmp=Path(tmp)
        original=tmp/"original"
        original.mkdir()
        for name in assets.SOURCE_DIRS:shutil.copytree(source/name,original/name)
        for name in assets.TOP_FILES:
            if (source/name).is_file():shutil.copy2(source/name,original/name)
        (original/".env").write_text("AFTERGRID_BIND=127.0.0.1\nAFTERGRID_PORT=8080\nAFTERGRID_ORIGIN="+BASE+"\nAFTERGRID_ROOT="+str(original)+"\n")
        for name in ("data/core","content/kiwix","content/maps","content/routing"):
            p=original/name
            p.mkdir(parents=True)
            p.chmod(0o700 if name=="data/core" else 0o755)
            os.chown(p,10001,10001)
        token=secrets.token_hex(24)
        p=original/"data/core/setup-token"
        p.write_text(token)
        p.chmod(0o600)
        os.chown(p,10001,10001)
        creds={"username":"admin","password":secrets.token_hex(24)}
        original_cmd=["docker","compose","--project-name","aftergrid-core",
                      "--project-directory",str(original),"--file",str(original/"compose.yaml"),
                      "--env-file",str(original/".env")]
        recovered=tmp/"replacement"
        def run(cmd,*args,timeout=180):
            return subprocess.run([*cmd,*args],check=True,capture_output=True,timeout=timeout).stdout
        try:
            run(original_cmd,"up","-d","--no-build","--pull","never","--wait","--wait-timeout","120")
            old=client()
            call(old,"/api/setup",{**creds,"token":token,"server_name":"Recovery fixture"},201)
            call(old,"/api/admin/first-run",{"modules":[]},202)
            call(old,"/api/admin/households",{"name":"Recovered household"})
            # Use the actual private export functions. A synthetic interrupted
            # backup job is inserted without queueing a real native repository job.
            run(original_cmd,"exec","-T","core","python","/app/backup_export.py","create","101")
            raw=run(original_cmd,"exec","-T","worker","python3","-c",
                "import worker,sys; worker.module_secrets('kopia',create=True); worker.module_secrets('homebox',create=True); "
                "c=worker.db(); db=c.__enter__(); j=db.execute(\"INSERT INTO jobs(module,action,state,stage,created) VALUES('kopia','worker-snapshot','interrupted','fixture',1)\").lastrowid; "
                "db.execute(\"INSERT INTO sharing VALUES('homebox',1,1)\"); c.__exit__(None,None,None); "
                "payload,_=worker.worker_recovery_payload(j); sys.stdout.buffer.write(payload)")
            payload=json.loads(raw)
            wid=payload["job"]
            worker_dir=tmp/"worker-export"
            worker_dir.mkdir(mode=0o700)
            (worker_dir/"job-id").write_text(str(wid))
            (worker_dir/"worker-recovery.json").write_bytes(raw)
            bundle=tmp/"assets"
            metadata=assets.capture(original,bundle)
            assert assets.verify(bundle)==metadata
            run(original_cmd,"down","-v")
            # Use exact already-local IDs instead of deleting unrelated runner
            # images. The separate archive load fixture covers Docker import.
            for row in assets.recovery_image_rows(metadata):
                assets.docker("image","tag",row["image_id"],row["recovery_tag"])
            plan=recovery.stage(bundle,original/"data/core/recovery-export",worker_dir,
                                recovered,101,wid,hashlib.sha256(raw).hexdigest())
            assert plan["content_metadata_included"]
            recovery.start_core(recovered,bundle,True)
            # The old authenticated cookie must not survive recovery.
            assert call(old,"/api/status")["admin"] is False
            fresh=client()
            status=call(fresh,"/api/status")
            assert not status["setup_required"] and status["server_name"]=="Recovery fixture" and status["recovery_core_only"]
            call(fresh,"/api/login",creds)
            assert call(fresh,"/api/households")["households"][0]["name"]=="Recovered household"
            assert call(fresh,"/api/admin/status")["core"]=="running"
            assert call(fresh,"/api/admin/modules/kiwix/install",{},409)["detail"]
            jobs=call(fresh,"/api/admin/jobs")
            assert any(j["id"]==wid and j["state"]=="interrupted" for j in jobs)
            # Compare secrets and sharing inside the restored worker without
            # printing values or passing them on the command line.
            result=subprocess.run([*recovery.compose_command(recovered),"exec","-T","worker","python3","-c",
                "import worker,json,sys,hmac; expected=json.load(sys.stdin); "
                "assert all(hmac.compare_digest(v,worker.module_secrets(m)[k]) for m,fields in expected.items() for k,v in fields.items()); "
                "c=worker.db(); db=c.__enter__(); assert tuple(db.execute(\"SELECT shared,registration_closed FROM sharing WHERE module='homebox'\").fetchone())==(1,1); c.__exit__(None,None,None); "
                "assert worker.RECOVERY_CORE_ONLY"],input=json.dumps(payload["secrets"]).encode(),capture_output=True,timeout=30)
            assert result.returncode==0,"Recovered worker credential or sharing check failed"
            print("Recovered core startup, original login, household, session exclusion, worker credentials and sharing, no-pull configuration and mutation guard passed.",flush=True)
        finally:
            if (recovered/"recovery-overrides/aftergrid-core.json").is_file():
                subprocess.run([*recovery.compose_command(recovered),"down","-v"],capture_output=True,timeout=90)
            subprocess.run([*original_cmd,"down","-v"],capture_output=True,timeout=90)

if __name__=="__main__":
    main()
