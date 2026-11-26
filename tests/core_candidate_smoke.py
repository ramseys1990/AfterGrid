"""Opt-in Linux smoke for source-built images; never replaces installed services.

Usage: AFTERGRID_CANDIDATE_BUILD_TEST=1 python3 -B tests/core_candidate_smoke.py CANDIDATE
CANDIDATE contains source/ and build.json from the reviewed source build.
Private fixture directories and stopped containers are retained for inspection.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path


IMAGE = re.compile(r"sha256:[a-f0-9]{64}")


def run(*args, timeout=180):
    env = {"PATH": os.environ["PATH"], "HOME": "/root",
           "DOCKER_HOST": "unix:///var/run/docker.sock"}
    result = subprocess.run(args, env=env, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError("Candidate acceptance command failed: " + result.stderr[-8192:])
    return result.stdout


def inventory():
    ids = run("docker", "ps", "-aq", "--no-trunc").split()
    if not ids:
        return {}
    rows = json.loads(run("docker", "inspect", *ids))
    return {r["Id"]: (r["Image"], r["State"]["StartedAt"], r["State"]["Status"])
            for r in rows}


def smoke(candidate):
    if (os.geteuid() != 0 or os.environ.get("AFTERGRID_CANDIDATE_BUILD_TEST") != "1"
            or Path("/etc/pve").exists() or shutil.which("pveversion")):
        raise RuntimeError("Opt-in Linux guest acceptance only; never the hypervisor")
    candidate = candidate.resolve(strict=True)
    report = json.loads((candidate / "build.json").read_text())
    if (set(report["images"]) != {"core", "worker"}
            or not re.fullmatch(r"[a-f0-9]{40}", report["commit"])):
        raise ValueError("Expected reviewed source build report")
    for row in report["images"].values():
        if not IMAGE.fullmatch(row["image"]):
            raise ValueError("Exact local image IDs required")
        if run("docker", "image", "inspect", "--format", "{{.Id}}", row["image"]).strip() != row["image"]:
            raise ValueError("Built image unavailable")
    before = inventory()
    suffix = uuid.uuid4().hex[:12]
    project = "aftergrid-candidate-smoke-" + suffix
    fixture = candidate / project
    fixture.mkdir(mode=0o700)
    for folder in ("core", "worker", "socket", "kiwix", "maps", "routing"):
        p = fixture / folder
        p.mkdir(mode=0o700)
        if folder in {"core", "kiwix", "maps", "routing"}:
            os.chown(p, 10001, 10001)
    envfile = fixture / ".env"
    envfile.write_text("AFTERGRID_BIND=127.0.0.1\nAFTERGRID_PORT=18080\n"
                       "AFTERGRID_ROOT=" + str(fixture) + "\n")
    base = json.loads(run("docker", "compose", "--project-name", project,
                         "--project-directory", str(candidate / "source"),
                         "--env-file", str(envfile), "--file",
                         str(candidate / "source/compose.yaml"), "config", "--format", "json"))
    if set(base["services"]) != {"core", "worker"}:
        raise ValueError("Expected only core and worker")
    mounts = {"core": [("core", "/data", False), ("socket", "/run/aftergrid", True),
                       ("kiwix", "/content/kiwix", False), ("maps", "/content/maps", False),
                       ("routing", "/content/routing", False)],
              "worker": [("worker", "/worker-state", False), ("socket", "/run/aftergrid", False)]}
    for name, definition in base["services"].items():
        for field in ("build", "ports", "networks", "container_name"):
            definition.pop(field, None)
        definition.update(image=report["images"][name]["image"], pull_policy="never",
                          network_mode="none", restart="no")
        definition["volumes"] = [{"type": "bind", "source": str(fixture / folder),
                                  "target": target, "read_only": readonly,
                                  "bind": {"create_host_path": False}}
                                 for folder, target, readonly in mounts[name]]
        if name == "worker":
            definition["volumes"].append({"type": "bind", "source": str(candidate / "source/modules"),
                                           "target": "/modules", "read_only": True,
                                           "bind": {"create_host_path": False}})
    config = fixture / "compose.json"
    config.write_text(json.dumps({"name": project, "services": base["services"]}))
    cmd = ["docker", "compose", "--project-name", project, "--project-directory", str(fixture),
           "--file", str(config)]
    outcome = {"commit": report["commit"], "project": project, "images": report["images"],
               "source_built_boot": False, "installed_unchanged": False}
    try:
        run(*cmd, "up", "-d", "--no-build", "--pull", "never", "--wait", "--wait-timeout", "120")
        ids = run(*cmd, "ps", "-aq").split()
        rows = json.loads(run("docker", "inspect", *ids))
        assert len(rows) == 2
        for row in rows:
            name = row["Config"]["Labels"]["com.docker.compose.service"]
            assert row["Config"]["Labels"]["com.docker.compose.project"] == project
            assert row["Image"] == report["images"][name]["image"]
            assert row["State"]["Health"]["Status"] == "healthy"
            assert row["HostConfig"]["NetworkMode"] == "none"
            assert not row["HostConfig"]["PortBindings"]
            assert not any(m["Destination"] == "/var/run/docker.sock" for m in row["Mounts"])
            filename = "app.py" if name == "core" else "worker.py"
            expected = hashlib.sha256((candidate / "source" / name / filename).read_bytes()).hexdigest()
            actual = run(*cmd, "exec", "-T", name, "python" if name == "core" else "python3", "-c",
                         "import pathlib,hashlib; print(hashlib.sha256(pathlib.Path('/app/" + filename + "').read_bytes()).hexdigest())").strip()
            assert expected == actual
        probe = '''import urllib.request,urllib.error,json
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
with opener.open("http://127.0.0.1:8080/health") as r:assert json.load(r)=={"status":"ok"}
with opener.open("http://127.0.0.1:8080/api/status") as r:
    value=json.load(r); assert value["setup_required"] and not value["admin"]
with opener.open("http://127.0.0.1:8080/") as r:assert b"AfterGrid" in r.read()
try:opener.open("http://127.0.0.1:8080/api/admin/jobs")
except urllib.error.HTTPError as e:assert e.code==401
else:raise AssertionError("Anonymous administrative access")
import native_setup
assert set(native_setup.BASE)=={"homebox","grocy"}
'''
        run(*cmd, "exec", "-T", "core", "python", "-c", probe)
        outcome["source_built_boot"] = True
    finally:
        run(*cmd, "stop", "--timeout", "30", "core", "worker")
        after = inventory()
        outcome["installed_unchanged"] = all(after.get(cid) == value for cid, value in before.items())
        (fixture / "result.json").write_text(json.dumps(outcome, indent=2))
    assert outcome["source_built_boot"] and outcome["installed_unchanged"]
    print(json.dumps(outcome), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path)
    smoke(parser.parse_args().candidate)

