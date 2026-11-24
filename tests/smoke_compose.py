"""Disposable CI integration test. Never run on an existing AfterGrid host."""
import http.cookiejar
import json
import os
import time
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8080"
client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

def api(path, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(BASE + path, data=data, headers={"Origin": BASE, "Content-Type": "application/json"})
    with client.open(req, timeout=30) as res:
        return json.load(res)

def module(ident="kiwix"):
    return next(m for m in api("/api/modules") if m["id"]==ident)

def action(name, ident="kiwix"):
    job_id=api("/api/admin/modules/"+ident+"/"+name,{})["id"]
    wait_job(job_id,name)

def wait_job(job_id,name):
    deadline=time.monotonic()+240
    while time.monotonic()<deadline:
        job=next(j for j in api("/api/admin/jobs") if j["id"]==job_id)
        if job["state"]=="succeeded":
            assert job["completed"]==job["total"],job
            return
        if job["state"] in ("failed","interrupted"):
            raise AssertionError(job)
        time.sleep(2)
    raise AssertionError("Timed out waiting for "+name)

assert api("/api/status")["setup_required"]
api("/api/setup",{"token":os.environ["SMOKE_TOKEN"],"username":"admin","password":"a disposable test password","server_name":"CI"})
assert module()["status"]=="not installed"
batch=api("/api/admin/first-run",{"modules":["kiwix","homebox"]})
assert len(batch["ids"])==2
assert not api("/api/status")["selection_pending"]
assert api("/api/admin/first-run",{"modules":["homebox","kiwix"]})==batch
wait_job(batch["ids"][0],"kiwix initial install")
assert module()["status"]=="running"
with urllib.request.urlopen("http://127.0.0.1:8081/",timeout=10) as response:
    assert response.status==200
action("stop")
assert module()["status"]=="stopped"
action("start")
assert module()["status"]=="running"
action("restart")
assert module()["status"]=="running"
action("uninstall")
assert module()["status"]=="not installed"
assert Path("content/kiwix/library.xml").is_file()
print("Kiwix Compose lifecycle passed; content preserved.")

# Exercise the same lifecycle for the new inventory and backup services.
for ident, port in [("homebox",8082),("grocy",8083),("kopia",51515)]:
    if ident=="homebox":
        wait_job(batch["ids"][1],"homebox initial install")
    else:
        assert module(ident)["status"]=="not installed"
        action("install",ident)
    assert module(ident)["status"]=="running"
    if ident=="kopia":
        import base64
        credentials=api("/api/admin/kopia/credentials")
        auth=base64.b64encode((credentials["username"]+":"+credentials["ui_password"]).encode()).decode()
        req=urllib.request.Request("http://127.0.0.1:51515/",headers={"Authorization":"Basic "+auth})
        with urllib.request.urlopen(req,timeout=10) as response:
            assert response.status==200
    else:
        with urllib.request.urlopen("http://127.0.0.1:"+str(port)+"/",timeout=10) as response:
            assert response.status==200
    action("stop",ident)
    assert module(ident)["status"]=="stopped"
    action("start",ident)
    assert module(ident)["status"]=="running"
    action("uninstall",ident)
    assert module(ident)["status"]=="not installed"
    assert Path("data",ident).is_dir()
    print(ident+" lifecycle passed; data directory retained.")
