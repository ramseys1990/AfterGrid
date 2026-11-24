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

def module():
    return next(m for m in api("/api/modules") if m["id"]=="kiwix")

def action(name):
    job_id=api("/api/admin/modules/kiwix/"+name,{})["id"]
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
action("install")
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
