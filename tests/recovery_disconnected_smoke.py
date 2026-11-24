"""Disposable isolated CI target: actual image import and native offline recovery.

Run only inside an empty Docker-in-Docker test container with network=none.
The source fixture is read-only; no host daemon, host networking or secrets
are supplied. The entire target is discarded by the outer CI runner.
"""
import json
import os
import re
import socket
import sys
from pathlib import Path

def assert_disconnected():
    # Docker's outer network namespace must not have an external default route.
    for line in Path("/proc/net/route").read_text().splitlines()[1:]:
        if line.split()[1]=="00000000":raise RuntimeError("Unexpected external default route")
    try:
        with socket.create_connection(("1.1.1.1",443),timeout=3):
            raise RuntimeError("Unexpected external connectivity")
    except OSError:
        pass

def main(folder):
    if (os.geteuid()!=0 or os.environ.get("AFTERGRID_DISPOSABLE_DISCONNECTED_TEST")!="1"
        or not Path("/.dockerenv").is_file()):
        raise RuntimeError("Disposable isolated CI container only")
    folder=Path(folder).resolve(strict=True)
    assert_disconnected()
    package=folder/"package"
    sys.path.insert(0,str(package/"assets/release"))
    import recover
    import recovery_assets as assets
    from recovery_guided_smoke import call,client,post_job,reader_fixture

    assets.local_docker()
    if assets.docker("ps","--all","--quiet") or assets.docker("image","ls","--all","--quiet"):
        raise RuntimeError("Replacement daemon must start empty; no pruning permitted")
    root=Path("/tmp/aftergrid-disconnected-target")
    if root.exists():raise RuntimeError("Replacement root must not exist")
    packed=recover.verify_package(package)
    assert packed["selected"]==["kiwix"] and not packed["omitted_captured"]
    fixture=json.loads(recover.prep.read_private(folder/"acceptance.json",65536))
    # Actual native Docker archive load; no patched import or preloaded images.
    report=recover.restore_package(root,package,fixture["repository_password"])
    assert report["guarded"] and report["repository_readonly"] and not report["complete_recovery"]
    fresh=client()
    status=call(fresh,"/api/status")
    assert status["recovery_core_only"] and not status["admin"] and not status["recovery_maintenance"]
    call(fresh,"/api/login",fixture["credentials"])
    assert call(fresh,"/api/households")["households"][0]["name"]=="Guided household"
    assert assets.sha256_file(root/"content/kiwix/fixture.zim")==fixture["fixture_sha256"]
    assert reader_fixture()
    assert call(fresh,"/api/admin/kopia/status")["connection"]=="connected"
    bundle=package/"assets"
    inventory=package/"inventory.json"
    recover.enable_backups(root,bundle,inventory)
    recover.activate(root,bundle,inventory)
    assert call(fresh,"/api/status")["recovery_offline"]
    post_job(fresh,"/api/admin/modules/kiwix/stop")
    post_job(fresh,"/api/admin/modules/kiwix/start")
    assert reader_fixture()
    post_job(fresh,"/api/admin/backups/core/snapshot",{"confirmed":True})
    post_job(fresh,"/api/admin/backups/core/verify-snapshot",{"confirmed":True})
    for path in ("/api/admin/modules/kiwix/update","/api/admin/modules/maps/install","/api/admin/content/downloads"):
        assert call(fresh,path,{},409)["detail"]
    core=assets.docker("ps","--quiet","--filter","label=com.docker.compose.project=aftergrid-core",
                       "--filter","label=com.docker.compose.service=core")
    if not re.fullmatch(r"[a-f0-9]{12,64}",core):raise RuntimeError("Recovered core container missing")
    assets.docker("exec",core,"python","-c",
                  "import socket,sys\ntry:\n socket.create_connection(('1.1.1.1',443),timeout=3).close()\nexcept OSError:\n sys.exit(0)\nsys.exit(1)")
    assert_disconnected()
    assert recover.verify_package(package)==packed
    print("Disconnected replacement acceptance passed: empty daemon, actual archive import, recovered native content, local lifecycle, writable backup verification and unchanged package.",flush=True)

if __name__=="__main__":
    if len(sys.argv)!=2:raise SystemExit("Private disposable fixture directory required")
    main(sys.argv[1])
