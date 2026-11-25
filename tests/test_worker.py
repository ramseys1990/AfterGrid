import sqlite3
import pytest
from worker import worker

def test_scope_and_queue(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(worker, "MODULES", Path(__file__).resolve().parents[1] / "modules")
    monkeypatch.setattr(worker, "STATE", tmp_path)
    worker.init()
    assert worker.command("kiwix","down")[:4] == ["docker","compose","--project-name","aftergrid-kiwix"]
    with pytest.raises(ValueError):
        worker.enqueue("../core","install")
    with pytest.raises(ValueError):
        worker.enqueue("kiwix","exec")
    job = worker.enqueue("kiwix","install")
    with pytest.raises(sqlite3.IntegrityError):
        worker.enqueue("kiwix","stop")
    monkeypatch.setattr(worker, "run", lambda *a: None)
    monkeypatch.setattr(worker, "wait_ready", lambda *a: None)
    worker.execute(worker.jobs()[0])
    row=worker.jobs()[0]
    assert row["id"]==job and row["state"]=="succeeded" and row["completed"]==row["total"]==4
    assert worker.stages("uninstall")[-1][1]==("down",)
    worker.enqueue("kiwix","stop")

def test_interrupted(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(worker,"MODULES",Path(__file__).resolve().parents[1]/"modules")
    monkeypatch.setattr(worker,"STATE",tmp_path)
    worker.init()
    job=worker.enqueue("kiwix","install")
    worker.change(job,state="running")
    worker.init()
    assert worker.jobs()[0]["state"]=="interrupted"


def test_generated_secrets(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(worker,"MODULES",Path(__file__).resolve().parents[1]/"modules")
    monkeypatch.setattr(worker,"STATE",tmp_path)
    worker.init()
    assert worker.module_secrets("homebox")["HBOX_AUTH_API_KEY_PEPPER"]=="not-configured-read-only-placeholder"
    assert not (tmp_path/"secrets").exists()
    a=worker.module_secrets("homebox",create=True)
    assert len(a["HBOX_AUTH_API_KEY_PEPPER"])==64
    assert worker.module_secrets("homebox",create=True)==a
    assert (tmp_path/"secrets"/"homebox.json").stat().st_mode & 0o777 == 0o600
    b=worker.module_secrets("kopia",create=True)
    assert b["KOPIA_PASSWORD"]!=b["KOPIA_UI_PASSWORD"]
    assert worker.compose_env("kopia")["KOPIA_PASSWORD"]==b["KOPIA_PASSWORD"]


def test_batch_atomic_and_idempotent(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(worker,"MODULES",Path(__file__).resolve().parents[1]/"modules")
    monkeypatch.setattr(worker,"STATE",tmp_path)
    worker.init()
    token="a"*48
    with pytest.raises(ValueError):
        worker.enqueue_batch(token,["kiwix","unknown"])
    assert worker.jobs()==[]
    first=worker.enqueue_batch(token,["homebox","kiwix"])
    assert len(first)==2
    assert worker.enqueue_batch(token,["kiwix","homebox"])==first
    with pytest.raises(sqlite3.IntegrityError):
        worker.enqueue_batch("b"*48,["grocy","kiwix"])
    assert len(worker.jobs())==2
    with pytest.raises(sqlite3.IntegrityError):
        worker.enqueue_batch(token,["grocy"])


def test_lan_sharing_configuration(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(worker,"MODULES",Path(__file__).resolve().parents[1]/"modules")
    monkeypatch.setattr(worker,"STATE",tmp_path)
    monkeypatch.setattr(worker,"LAN_BIND","192.168.10.4")
    monkeypatch.setattr(worker,"LAN_DOMAIN","aftergrid.home.arpa")
    worker.init()
    assert worker.lan_available()
    assert worker.sharing_env("homebox")["AFTERGRID_MODULE_BIND"]=="127.0.0.1"
    assert worker.sharing_env("homebox")["AFTERGRID_HOMEBOX_REGISTRATION"]=="true"
    assert worker.enqueue("kopia","share") > 0
    assert worker.sharing_env("kopia")["AFTERGRID_MODULE_BIND"]=="127.0.0.1"
    worker.set_sharing("kopia",True)
    assert worker.sharing_env("kopia")["AFTERGRID_MODULE_BIND"]=="192.168.10.4"
    worker.set_sharing("homebox",True)
    env=worker.sharing_env("homebox")
    assert env["AFTERGRID_MODULE_BIND"]=="192.168.10.4"
    assert env["AFTERGRID_MODULE_URL"]=="http://homebox.aftergrid.home.arpa:8082"
    assert env["AFTERGRID_HOMEBOX_REGISTRATION"]=="false"
    worker.set_sharing("homebox",False)
    assert worker.sharing_env("homebox")["AFTERGRID_MODULE_BIND"]=="127.0.0.1"
    assert worker.sharing_env("homebox")["AFTERGRID_HOMEBOX_REGISTRATION"]=="false"
    monkeypatch.setattr(worker,"LAN_BIND","8.8.8.8")
    assert not worker.lan_available()
    with pytest.raises(ValueError):
        worker.enqueue("homebox","share")
    monkeypatch.setattr(worker,"LAN_BIND","192.168.10.4")
    monkeypatch.setattr(worker,"LAN_DOMAIN","")
    assert worker.lan_available()
    assert worker.lan_url("homebox",worker.catalog()["homebox"])=="http://192.168.10.4:8082"
    monkeypatch.setattr(worker,"LAN_DOMAIN","example.com")
    assert not worker.lan_available()


def test_routing_switch_failure_restores_previous_selection(tmp_path,monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(worker,"MODULES",Path(__file__).resolve().parents[1]/"modules")
    monkeypatch.setattr(worker,"STATE",tmp_path)
    worker.init()
    with pytest.raises(ValueError):worker.enqueue("kiwix","activate-graph")
    worker.enqueue("routing","activate-graph")
    commands=[]
    monkeypatch.setattr(worker,"state",lambda ident:"running")
    monkeypatch.setattr(worker,"run",lambda job,ident,*args:commands.append(args))
    checks=[]
    def probe(ident):
        checks.append(ident)
        if len(checks)==1:raise RuntimeError("test readiness failure")
    monkeypatch.setattr(worker,"wait_ready",probe)
    worker.execute(worker.jobs()[0])
    assert worker.jobs()[0]["state"]=="failed"
    assert ("run","--rm","--no-deps","-T","--pull","never","--entrypoint","/bin/sh","routing","/aftergrid/switch.sh","select","tiles-next") in commands
    assert commands[-2][-2:]==("select","tiles")
    assert "Previous graph ready again" in worker.jobs()[0]["log"]


def test_archive_is_routing_only():
    with pytest.raises(ValueError):worker.enqueue("kiwix","archive-original")
    assert worker.routing_steps("archive-original")[1][1][-2:]==("/aftergrid/archive.sh","tiles")
    assert worker.routing_steps("archive-replacement")[1][1][-2:]==("/aftergrid/archive.sh","tiles-next")


def test_local_version_report_and_update_gate(tmp_path,monkeypatch):
    import json
    from pathlib import Path
    from types import SimpleNamespace
    monkeypatch.setattr(worker,"MODULES",Path(__file__).resolve().parents[1]/"modules")
    monkeypatch.setattr(worker,"STATE",tmp_path)
    worker.init()
    with pytest.raises(ValueError):worker.enqueue("kiwix","update")
    with pytest.raises(ValueError):worker.enqueue("routing","update",True)
    job=worker.enqueue("kiwix","update",True)
    installed="sha256:"+"a"*64
    target="sha256:"+"b"*64
    def docker(argv,**kwargs):
        if "config" in argv:out={"services":{"kiwix":{"image":"example/image:1.2","environment":{"SECRET":"private-value"}}}}
        elif "ps" in argv:out=[{"Service":"kiwix","ID":"a"*64}]
        elif argv[:3]==["docker","container","inspect"]:out=installed
        elif argv[:3]==["docker","image","inspect"]:out=target
        else:raise AssertionError(argv)
        return SimpleNamespace(stdout=json.dumps(out))
    monkeypatch.setattr(worker.subprocess,"run",docker)
    r=worker.version_report("kiwix")
    assert r["registry_checked"] is False and r["history"][0]["id"]==job
    assert r["services"][0]["comparison"]=="differs from local target"
    assert r["services"][0]["installed_image_ids"]==[installed]
    assert "private-value" not in json.dumps(r)
    monkeypatch.setattr(worker,"state",lambda ident:"stopped")
    monkeypatch.setattr(worker,"run",lambda *args:pytest.fail("Stopped module must not be updated"))
    worker.execute(worker.jobs()[0])
    assert worker.jobs()[0]["state"]=="failed"


def test_registry_manifest_platform_and_digest_selection():
    import json
    import pytest
    manifest="sha256:"+"a"*64
    config="sha256:"+"b"*64
    other="sha256:"+"c"*64
    target="registry.example:5000/team/app:1.2"
    child={"schemaVersion":2,"config":{"digest":config,"mediaType":"application/vnd.oci.image.config.v1+json"}}
    index={"schemaVersion":2,"manifests":[{"digest":manifest,"platform":{"os":"linux","architecture":"amd64"}},
          {"digest":other,"platform":{"os":"linux","architecture":"arm64"}},
          {"digest":other,"platform":{"os":"unknown","architecture":"unknown"}}]}
    calls=[]
    def read(argv):
        assert argv[:5]==["docker","buildx","imagetools","inspect","--raw"]
        calls.append(argv[-1])
        return json.dumps(index if argv[-1]==target else child)
    assert worker.registry_config_digest(target,"linux/amd64",read)==(config,manifest)
    assert calls==[target,"registry.example:5000/team/app@"+manifest]
    with pytest.raises(ValueError):worker.registry_config_digest(target,"linux/386",read)
    index["manifests"].append({"digest":other,"platform":{"os":"linux","architecture":"amd64"}})
    with pytest.raises(ValueError):worker.registry_config_digest(target,"linux/amd64",read)
    assert worker.registry_config_digest(target,"linux/amd64",lambda argv:json.dumps(child))==(config,None)

def test_registry_comparison_read_only_and_failure(monkeypatch,tmp_path):
    import json
    import subprocess
    from pathlib import Path
    from types import SimpleNamespace
    monkeypatch.setattr(worker,"MODULES",Path(__file__).resolve().parents[1]/"modules")
    monkeypatch.setattr(worker,"STATE",tmp_path)
    worker.init()
    digest="sha256:"+"a"*64
    pinned="example/app:1.0@sha256:"+"b"*64
    monkeypatch.setattr(worker,"version_report",lambda ident:{"services":[{"configured_image":pinned,"installed_image_ids":[digest]}]})
    def run(argv,**kwargs):
        if argv[1]=="version":return SimpleNamespace(stdout="linux/amd64")
        assert argv[:5]==["docker","buildx","imagetools","inspect","--raw"]
        return SimpleNamespace(stdout=json.dumps({"schemaVersion":2,"config":{"digest":digest,"mediaType":"application/vnd.docker.container.image.v1+json"}}))
    monkeypatch.setattr(worker.subprocess,"run",run)
    result=worker.registry_report("kiwix")
    assert result["digest_pinned"] and result["comparison"]=="matches configured registry image"
    assert worker.jobs()==[]
    def offline(argv,**kwargs):raise subprocess.TimeoutExpired(argv,6)
    monkeypatch.setattr(worker.subprocess,"run",offline)
    result=worker.registry_report("kiwix")
    assert result["comparison"]=="unavailable" and result["registry_config_digest"] is None
    assert worker.jobs()==[]


def test_backup_sources_classify_mounts_without_host_reads():
    config={"services":{"app":{"volumes":[
        {"type":"bind","source":"/opt/aftergrid/data/media/config","target":"/config"},
        {"type":"bind","source":"/opt/aftergrid/data/media/cache","target":"/cache"},
        {"type":"bind","source":"/opt/aftergrid/content/media","target":"/media","read_only":True},
        {"type":"bind","source":"/opt/aftergrid/modules/media/config","target":"/settings"},
        {"type":"bind","source":"/opt/aftergrid-other/data/private","target":"/other"},
        {"type":"bind","source":"/opt/aftergrid/data/../../etc","target":"/escape"},
        {"type":"volume","source":"secret-volume","target":"/volume"},
        {"type":"bind","source":"/opt/aftergrid/data/kopia/config","target":"/kopia"}
    ]}}}
    rows=worker.backup_sources(config,"/opt/aftergrid")
    assert [r["kopia_path"] for r in rows]==["/source/data/media/config",None,"/source/content/media","/source/modules/media/config",None,None,None,None]
    assert rows[1]["role"]=="regenerable cache" and rows[2]["read_only"]
    assert "secret-volume" not in str(rows) and "aftergrid-other" not in str(rows)

def test_backup_plan_never_claims_snapshot_or_exposes_secrets(tmp_path,monkeypatch):
    import json
    from pathlib import Path
    from types import SimpleNamespace
    monkeypatch.setattr(worker,"MODULES",Path(__file__).resolve().parents[1]/"modules")
    monkeypatch.setattr(worker,"STATE",tmp_path)
    worker.init()
    def read(argv,**kwargs):
        assert argv[-3:]==["config","--format","json"]
        return SimpleNamespace(stdout=json.dumps({"services":{"app":{"environment":{"SECRET":"private-value"},"volumes":[{"type":"bind","source":worker.ROOT+"/data/homebox","target":"/data"}]}}}))
    monkeypatch.setattr(worker.subprocess,"run",read)
    result=worker.backup_plan("homebox")
    assert result["worker_secrets_required"] and not result["snapshot_verified"]
    assert result["sources"][0]["kopia_path"]=="/source/data/homebox"
    assert "private-value" not in str(result)
    assert all(s["kopia_path"] is None for s in worker.backup_plan("kopia")["sources"])
    assert worker.jobs()==[]


def test_kopia_initialization_is_scoped_and_empty_only(tmp_path,monkeypatch):
    import subprocess
    from pathlib import Path
    monkeypatch.setattr(worker,"MODULES",Path(__file__).resolve().parents[1]/"modules")
    monkeypatch.setattr(worker,"STATE",tmp_path)
    worker.init()
    with pytest.raises(ValueError):worker.enqueue("homebox","initialize-repository")
    created=[]
    class Client:
        def status(self):
            return {"connection":"connected" if created else "not connected","storage_type":"filesystem" if created else None}
        def create_local(self):created.append(True)
    monkeypatch.setattr(worker,"KopiaClient",Client)
    def nonempty(argv,**kwargs):raise subprocess.CalledProcessError(1,argv)
    monkeypatch.setattr(worker.subprocess,"run",nonempty)
    worker.enqueue("kopia","initialize-repository")
    worker.execute(worker.jobs()[0])
    assert worker.jobs()[0]["state"]=="failed" and not created
    monkeypatch.setattr(worker.subprocess,"run",lambda *args,**kwargs:None)
    worker.enqueue("kopia","initialize-repository")
    worker.execute(worker.jobs()[0])
    assert worker.jobs()[0]["state"]=="succeeded" and created==[True]
    worker.enqueue("kopia","initialize-repository")
    worker.execute(worker.jobs()[0])
    assert worker.jobs()[0]["state"]=="failed" and created==[True]

def test_native_kopia_status_filters_response(monkeypatch):
    import json
    client=worker.KopiaClient.__new__(worker.KopiaClient)
    monkeypatch.setattr(client,"read",lambda path:json.dumps({"connected":True,"storage":"filesystem","configFile":"private-path","password":"private-secret"}).encode())
    assert client.status()=={"connection":"connected","storage_type":"filesystem","snapshot_verified":False}
    monkeypatch.setattr(client,"read",lambda path:b'{"connected":false,"initTaskID":"some-task"}')
    assert client.status()["connection"]=="initializing"
    monkeypatch.setattr(client,"read",lambda path:b'{"connected":"true"}')
    with pytest.raises(RuntimeError):client.status()


def test_snapshot_quiesces_and_restores_running_application(tmp_path,monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(worker,"MODULES",Path(__file__).resolve().parents[1]/"modules")
    monkeypatch.setattr(worker,"STATE",tmp_path)
    worker.init()
    with pytest.raises(ValueError):worker.enqueue("routing","snapshot")
    commands=[]
    monkeypatch.setattr(worker,"kopia_status",lambda:{"connection":"connected"})
    monkeypatch.setattr(worker,"state",lambda ident:"running")
    monkeypatch.setattr(worker,"cleanly_stopped",lambda ident:True)
    monkeypatch.setattr(worker,"run",lambda job,ident,*args:commands.append(args))
    monkeypatch.setattr(worker,"wait_ready",lambda ident:commands.append(("ready",)))
    def snap(ident):
        commands.append(("snapshot",))
        return "a"*32
    monkeypatch.setattr(worker,"native_snapshot",snap)
    worker.enqueue("grocy","snapshot")
    worker.execute(worker.jobs()[0])
    assert commands==[("stop","--timeout","60"),("snapshot",),("start",),("ready",)]
    assert worker.jobs()[0]["state"]=="succeeded" and "a"*32 in worker.jobs()[0]["log"]
    assert "restore not verified" in worker.jobs()[0]["stage"]
    commands.clear()
    def fail(ident):raise RuntimeError("fixture failure")
    monkeypatch.setattr(worker,"native_snapshot",fail)
    worker.enqueue("grocy","snapshot")
    worker.execute(worker.jobs()[0])
    assert commands==[("stop","--timeout","60"),("start",),("ready",)]
    assert worker.jobs()[0]["state"]=="failed"
    commands.clear()
    monkeypatch.setattr(worker,"cleanly_stopped",lambda ident:False)
    worker.enqueue("grocy","snapshot")
    worker.execute(worker.jobs()[0])
    assert commands==[("stop","--timeout","60"),("start",),("ready",)]
    assert worker.jobs()[0]["state"]=="failed"
    commands.clear()
    monkeypatch.setattr(worker,"state",lambda ident:"stopped")
    monkeypatch.setattr(worker,"cleanly_stopped",lambda ident:True)
    monkeypatch.setattr(worker,"native_snapshot",snap)
    worker.enqueue("grocy","snapshot")
    worker.execute(worker.jobs()[0])
    assert commands==[("snapshot",)] and worker.jobs()[0]["state"]=="succeeded"

def test_snapshot_rejects_partial_or_excluded_manifest(monkeypatch):
    import json
    from types import SimpleNamespace
    monkeypatch.setattr(worker,"compose_env",lambda ident:{})
    monkeypatch.setattr(worker,"command",lambda ident,*args:list(args))
    value={"id":"a"*32,"source":{"path":"/source/data/grocy"},"rootEntry":{"obj":"fixture"},
           "stats":{"errorCount":0,"ignoredErrorCount":0,"excludedFileCount":0,"excludedDirCount":0,"fileCount":1}}
    def native(argv,**kwargs):
        if "snapshot" in argv:
            assert "--json-verbose" in argv and "--json" in argv
        return SimpleNamespace(stdout=json.dumps(value))
    monkeypatch.setattr(worker.subprocess,"run",native)
    assert worker.native_snapshot("grocy")=="a"*32
    stats=value.pop("stats")
    with pytest.raises(RuntimeError,match="omitted required snapshot statistics"):
        worker.native_snapshot("grocy")
    value["stats"]=stats
    for field in ("errorCount","ignoredErrorCount","excludedFileCount","excludedDirCount"):
        value["stats"][field]=1
        with pytest.raises(RuntimeError):worker.native_snapshot("grocy")
        value["stats"][field]=0
    value["incomplete"]="checkpoint"
    with pytest.raises(RuntimeError):worker.native_snapshot("grocy")


def test_restored_grocy_database_integrity(tmp_path):
    import sqlite3
    path=tmp_path/"grocy.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE products(id INTEGER PRIMARY KEY)")
        db.execute("CREATE TABLE users(id INTEGER PRIMARY KEY)")
    worker.check_restored_grocy(path.read_bytes())
    with pytest.raises(RuntimeError):worker.check_restored_grocy(b"invalid")
    with sqlite3.connect(path) as db:db.execute("DROP TABLE users")
    with pytest.raises(RuntimeError):worker.check_restored_grocy(path.read_bytes())

def test_restore_uses_latest_successful_managed_snapshot(tmp_path,monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(worker,"MODULES",Path(__file__).resolve().parents[1]/"modules")
    monkeypatch.setattr(worker,"STATE",tmp_path)
    worker.init()
    j=worker.enqueue("grocy","snapshot")
    worker.log(j,"Native snapshot reported complete: "+"a"*32+"; restore not verified.")
    worker.change(j,state="succeeded")
    newer=worker.enqueue("grocy","snapshot")
    worker.change(newer,state="failed")
    assert worker.latest_managed_snapshot("grocy")=="a"*32
    with pytest.raises(ValueError):worker.enqueue("routing","verify-snapshot")
    with pytest.raises(RuntimeError):worker.latest_managed_snapshot("homebox")


def test_restore_manifest_requires_verbose_and_exact_id(monkeypatch):
    import json
    from types import SimpleNamespace
    monkeypatch.setattr(worker,"compose_env",lambda ident:{})
    monkeypatch.setattr(worker,"command",lambda ident,*args:list(args))
    manifest={"id":"a"*32,"source":{"path":"/source/data/grocy"},"rootEntry":{"obj":"k"+"b"*32},
              "stats":{"errorCount":0,"ignoredErrorCount":0,"excludedFileCount":0,"excludedDirCount":0,
                       "fileCount":1,"totalSize":100}}
    def native(argv,**kwargs):
        assert "--json-verbose" in argv and "--manifest-id" in argv
        return SimpleNamespace(stdout=json.dumps([manifest]))
    monkeypatch.setattr(worker.subprocess,"run",native)
    assert worker.restore_manifest("grocy","a"*32)=="k"+"b"*32
    with pytest.raises(RuntimeError):worker.restore_manifest("grocy","c"*32)
    manifest["stats"]["ignoredErrorCount"]=1
    with pytest.raises(RuntimeError,match="ignoredErrorCount=1"):worker.restore_manifest("grocy","a"*32)


def test_homebox_restore_schema_and_reviewed_sources(tmp_path):
    import sqlite3
    assert worker.SNAPSHOT_SOURCES=={"grocy":"/source/data/grocy","homebox":"/source/data/homebox","notes":"/source/data/notes","meshmonitor":"/source/data/meshmonitor","tak":"/source/data/tak","kolibri":"/source/data/kolibri","media":"/source/data/media/config"}
    path=tmp_path/"homebox.db"
    with sqlite3.connect(path) as db:
        for table in ("groups","users","attachments"):
            db.execute("CREATE TABLE "+table+"(id INTEGER PRIMARY KEY)")
    worker.check_restored_homebox(path.read_bytes())
    with sqlite3.connect(path) as db:db.execute("DROP TABLE attachments")
    with pytest.raises(RuntimeError):worker.check_restored_homebox(path.read_bytes())


def test_core_snapshot_scoped_and_cleans_after_failure(tmp_path,monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(worker,"MODULES",Path(__file__).resolve().parents[1]/"modules")
    monkeypatch.setattr(worker,"STATE",tmp_path)
    worker.init()
    with pytest.raises(ValueError):worker.enqueue("grocy","core-snapshot")
    monkeypatch.setattr(worker,"kopia_status",lambda:{"connection":"connected"})
    monkeypatch.setattr(worker,"core_container",lambda:"a"*64)
    calls=[]
    monkeypatch.setattr(worker.subprocess,"run",lambda argv,**kwargs:calls.append(argv))
    def failure(source):
        assert source=="/source/data/core/recovery-export"
        raise RuntimeError("fixture failure")
    monkeypatch.setattr(worker,"native_snapshot_source",failure)
    worker.enqueue("kopia","core-snapshot")
    worker.execute(worker.jobs()[0])
    assert worker.jobs()[0]["state"]=="failed"
    assert [argv[-2] for argv in calls]==["create","clear"]
    calls.clear()
    monkeypatch.setattr(worker,"native_snapshot_source",lambda source:"b"*32)
    worker.enqueue("kopia","core-snapshot")
    worker.execute(worker.jobs()[0])
    assert worker.jobs()[0]["state"]=="succeeded"
    assert [argv[-2] for argv in calls]==["create","clear"]
    assert "b"*32 in worker.jobs()[0]["log"]


def test_core_restored_database_schema_admin_and_sessions(tmp_path):
    import sqlite3
    path=tmp_path/"core.sqlite3"
    with sqlite3.connect(path) as db:
        for table in worker.CORE_TABLES-{"admin","sessions"}:
            db.execute("CREATE TABLE "+table+"(id INTEGER PRIMARY KEY)")
        db.execute("CREATE TABLE admin(id INTEGER PRIMARY KEY,username TEXT,salt TEXT,password_hash TEXT,server_name TEXT)")
        db.execute("CREATE TABLE sessions(token_hash TEXT)")
        db.execute("INSERT INTO admin VALUES(1,'admin','salt',?,'fixture')",("a"*128,))
    worker.check_restored_core(path.read_bytes())
    with sqlite3.connect(path) as db:db.execute("INSERT INTO sessions VALUES('fixture')")
    with pytest.raises(RuntimeError,match="session records"):worker.check_restored_core(path.read_bytes())
    with sqlite3.connect(path) as db:
        db.execute("DELETE FROM sessions")
        db.execute("DELETE FROM admin")
    with pytest.raises(RuntimeError,match="administrator"):worker.check_restored_core(path.read_bytes())

def test_core_restore_selects_only_successful_core_snapshot(tmp_path,monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(worker,"MODULES",Path(__file__).resolve().parents[1]/"modules")
    monkeypatch.setattr(worker,"STATE",tmp_path)
    worker.init()
    with pytest.raises(ValueError):worker.enqueue("grocy","core-verify-snapshot")
    j=worker.enqueue("kopia","core-snapshot")
    worker.log(j,"Core database export snapshot: "+"a"*32+"; restore not verified.")
    worker.change(j,state="succeeded")
    newer=worker.enqueue("kopia","core-snapshot")
    worker.change(newer,state="failed")
    assert worker.managed_snapshot_record("core")== (j,"a"*32)
    verify=worker.enqueue("kopia","core-verify-snapshot")
    observed=[]
    monkeypatch.setattr(worker,"verify_snapshot",lambda job,ident:observed.append((job,ident)))
    worker.execute(worker.jobs()[0])
    assert observed==[(verify,"core")]


def test_worker_recovery_export_preserves_secrets_and_disables_pending_jobs(tmp_path,monkeypatch):
    import base64,json,sqlite3
    from pathlib import Path
    monkeypatch.setattr(worker,"MODULES",Path(__file__).resolve().parents[1]/"modules")
    monkeypatch.setattr(worker,"STATE",tmp_path)
    worker.init()
    kopia=worker.module_secrets("kopia",create=True)
    homebox=worker.module_secrets("homebox",create=True)
    j=worker.enqueue("kopia","worker-snapshot")
    worker.change(j,state="running")
    pending=worker.enqueue("grocy","install")
    payload,count=worker.worker_recovery_payload(j)
    value=json.loads(payload)
    assert count==2 and value["job"]==j and value["format"]==1
    assert value["secrets"]=={"kopia":kopia,"homebox":homebox}
    restored=tmp_path/"restored.db"
    restored.write_bytes(base64.b64decode(value["jobs_sqlite3"],validate=True))
    with sqlite3.connect(restored) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()==("ok",)
        assert conn.execute("SELECT state FROM jobs ORDER BY id").fetchall()==[("interrupted",),("interrupted",)]
    assert {row["id"]:row["state"] for row in worker.jobs()}=={j:"running",pending:"queued"}
    (tmp_path/"secrets"/"unknown.json").write_text("{}")
    with pytest.raises(RuntimeError):worker.worker_recovery_payload(j)

def test_worker_snapshot_uses_private_stdin_and_cleans_on_failure(tmp_path,monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(worker,"MODULES",Path(__file__).resolve().parents[1]/"modules")
    monkeypatch.setattr(worker,"STATE",tmp_path)
    worker.init()
    with pytest.raises(ValueError):worker.enqueue("grocy","worker-snapshot")
    monkeypatch.setattr(worker,"kopia_status",lambda:{"connection":"connected"})
    monkeypatch.setattr(worker,"worker_recovery_payload",lambda job:(b"fixture-private-bytes",1))
    monkeypatch.setattr(worker,"compose_env",lambda ident:{})
    calls=[]
    monkeypatch.setattr(worker.subprocess,"run",lambda argv,**kwargs:calls.append((argv,kwargs)))
    def failure(source):
        assert source==worker.WORKER_EXPORT_SOURCE
        raise RuntimeError("fixture failure")
    monkeypatch.setattr(worker,"native_snapshot_source",failure)
    worker.enqueue("kopia","worker-snapshot")
    worker.execute(worker.jobs()[0])
    assert worker.jobs()[0]["state"]=="failed"
    assert len(calls)==2 and calls[0][1]["input"]==b"fixture-private-bytes" and calls[1][1]["input"] is None
    assert all("fixture-private-bytes" not in arg for argv,_ in calls for arg in argv)
    assert "fixture-private-bytes" not in worker.jobs()[0]["log"]


def test_worker_restore_envelope_exact_and_safe(tmp_path,monkeypatch):
    import hashlib,json,base64,sqlite3
    from pathlib import Path
    monkeypatch.setattr(worker,"MODULES",Path(__file__).resolve().parents[1]/"modules")
    monkeypatch.setattr(worker,"STATE",tmp_path)
    worker.init()
    worker.module_secrets("kopia",create=True)
    worker.module_secrets("homebox",create=True)
    j=worker.enqueue("kopia","worker-snapshot")
    worker.change(j,state="running")
    payload,count=worker.worker_recovery_payload(j)
    digest=hashlib.sha256(payload).hexdigest()
    assert worker.check_restored_worker(payload,j,digest)==count==2
    with pytest.raises(RuntimeError):worker.check_restored_worker(payload+b" ",j,digest)
    with pytest.raises(RuntimeError):worker.check_restored_worker(payload,j+1,digest)
    value=json.loads(payload)
    value["secrets"]["homebox"]["HBOX_AUTH_API_KEY_PEPPER"]="invalid"
    bad=json.dumps(value).encode()
    with pytest.raises(RuntimeError):worker.check_restored_worker(bad,j,hashlib.sha256(bad).hexdigest())
    value=json.loads(payload)
    path=tmp_path/"restored-worker.db"
    path.write_bytes(base64.b64decode(value["jobs_sqlite3"]))
    with sqlite3.connect(path) as conn:conn.execute("UPDATE jobs SET state='queued'")
    value["jobs_sqlite3"]=base64.b64encode(path.read_bytes()).decode()
    bad=json.dumps(value).encode()
    with pytest.raises(RuntimeError):worker.check_restored_worker(bad,j,hashlib.sha256(bad).hexdigest())
    worker.log(j,"Worker state export snapshot: "+"a"*32+"; 2 secret sets; restore not verified.")
    worker.change(j,state="succeeded")
    assert worker.managed_snapshot_record("worker")== (j,"a"*32)
    with pytest.raises(RuntimeError):worker.worker_export_checksum(j)
    worker.log(j,"Worker recovery envelope SHA-256: "+digest)
    assert worker.worker_export_checksum(j)==digest
    with pytest.raises(ValueError):worker.enqueue("grocy","worker-verify-snapshot")


def test_content_snapshot_and_native_verification(tmp_path,monkeypatch):
    import json
    from pathlib import Path
    from types import SimpleNamespace
    monkeypatch.setattr(worker,"MODULES",Path(__file__).resolve().parents[1]/"modules")
    monkeypatch.setattr(worker,"STATE",tmp_path)
    worker.init()
    monkeypatch.setattr(worker,"kopia_status",lambda:{"connection":"connected"})
    calls=[]
    monkeypatch.setattr(worker,"content_guard",lambda action,job:calls.append(action))
    def fail(source,seconds):
        assert source=="/source/content/maps"
        raise RuntimeError("fixture failure")
    monkeypatch.setattr(worker,"native_snapshot_source",fail)
    worker.enqueue("maps","content-snapshot")
    worker.execute(worker.jobs()[0])
    assert calls==["begin","end"] and worker.jobs()[0]["state"]=="failed"
    monkeypatch.setattr(worker,"native_snapshot_source",lambda source,seconds:"a"*32)
    worker.enqueue("maps","content-snapshot")
    worker.execute(worker.jobs()[0])
    assert worker.latest_content_snapshot("maps")=="a"*32
    monkeypatch.setattr(worker,"read_snapshot_manifest",lambda source,ident:("root",{"fileCount":2}))
    monkeypatch.setattr(worker,"compose_env",lambda ident:{})
    def native(argv,**kwargs):
        assert "--verify-files-percent=100" in argv and argv[-1]=="a"*32
        return SimpleNamespace(stdout=json.dumps({"errorCount":0,"stats":{"readFileCount":1,"processedObjectCount":2,"expectedTotalFileCount":2}}))
    monkeypatch.setattr(worker.subprocess,"run",native)
    worker.enqueue("maps","content-verify")
    worker.execute(worker.jobs()[0])
    assert worker.jobs()[0]["state"]=="succeeded"
    assert "No files restored" in worker.jobs()[0]["log"]
    with pytest.raises(ValueError):worker.enqueue("grocy","content-snapshot")


def test_recovery_inventory_exact_snapshot_evidence(tmp_path,monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(worker,"MODULES",Path(__file__).resolve().parents[1]/"modules")
    monkeypatch.setattr(worker,"STATE",tmp_path)
    worker.init()
    old=worker.enqueue("grocy","snapshot")
    worker.log(old,"Native snapshot reported complete: "+"a"*32+"; restore not verified.")
    worker.change(old,state="succeeded")
    v=worker.enqueue("grocy","verify-snapshot")
    worker.log(v,"Snapshot "+"a"*32+" restored; SQLite integrity passed.")
    worker.change(v,state="succeeded")
    newer=worker.enqueue("grocy","snapshot")
    worker.log(newer,"Native snapshot reported complete: "+"b"*32+"; restore not verified.")
    worker.change(newer,state="succeeded")
    c=worker.enqueue("kopia","worker-snapshot")
    worker.log(c,"Worker state export snapshot: "+"c"*32+"; 2 secret sets; restore not verified.")
    worker.log(c,"Worker recovery envelope SHA-256: "+"d"*64)
    worker.change(c,state="succeeded")
    record={x["key"]:x for x in worker.recovery_manifest_records()}
    assert record["application/grocy"]["snapshot_id"]=="b"*32
    assert record["application/grocy"]["verification"]=="not recorded"
    assert record["worker"]["envelope_sha256"]=="d"*64
    assert record["content/maps"]["snapshot_id"] is None
    with pytest.raises(RuntimeError):worker.load_recovery_manifest()
    monkeypatch.setattr(worker,"kopia_status",lambda:{"connection":"connected"})
    def native(source,sid):
        if sid=="b"*32:return "root",{"totalSize":123,"fileCount":2}
        raise RuntimeError("fixture missing")
    monkeypatch.setattr(worker,"read_snapshot_manifest",native)
    job=worker.enqueue("kopia","recovery-manifest")
    worker.execute(worker.jobs()[0])
    value=worker.load_recovery_manifest()
    assert value["manifest_job"]==job and value["atomic"] is False and value["complete_system_recovery"] is False
    record={x["key"]:x for x in value["records"]}
    assert record["application/grocy"]["repository_status"]=="present"
    assert record["worker"]["repository_status"]=="unavailable"
    assert record["content/maps"]["repository_status"]=="no managed snapshot"
    assert (tmp_path/"recovery-manifest.json").stat().st_mode&0o777==0o600
    with pytest.raises(ValueError):worker.enqueue("grocy","recovery-manifest")


def test_recovery_core_only_refuses_jobs(tmp_path,monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(worker,"STATE",tmp_path)
    monkeypatch.setattr(worker,"MODULES",Path(__file__).resolve().parents[1]/"modules")
    worker.init()
    monkeypatch.setattr(worker,"RECOVERY_CORE_ONLY",True)
    with pytest.raises(ValueError):worker.enqueue("kiwix","install")
    with pytest.raises(ValueError):worker.enqueue_batch("a"*48,["kiwix"])
    worker.process()
    assert worker.jobs()==[]


def test_offline_worker_uses_exact_reviewed_override(tmp_path,monkeypatch):
    import json
    from pathlib import Path
    from types import SimpleNamespace
    monkeypatch.setattr(worker,"MODULES",Path(__file__).resolve().parents[1]/"modules")
    monkeypatch.setattr(worker,"STATE",tmp_path)
    monkeypatch.setattr(worker,"RECOVERY_OFFLINE",True)
    worker.init()
    folder=tmp_path/"offline-images"
    folder.mkdir()
    image="sha256:"+"a"*64
    tag="aftergrid-recovery/aftergrid-kiwix-kiwix:"+"a"*64
    (folder/"mapping.json").write_text(json.dumps({"kiwix":{"image_id":image,"recovery_tag":tag}}))
    override=folder/"kiwix.json"
    override.write_text(json.dumps({"services":{"kiwix":{"image":tag,"pull_policy":"never"}}}))
    monkeypatch.setattr(worker.subprocess,"run",lambda *a,**k:SimpleNamespace(stdout=json.dumps(image)))
    cmd=worker.command("kiwix","up","-d","--pull","never")
    assert cmd[-1]=="--no-build" and str(override) in cmd
    assert worker.enqueue("kiwix","start")>0
    with pytest.raises(ValueError):worker.enqueue("kiwix","update",True)
    with pytest.raises(ValueError):worker.enqueue("kiwix","install")
    with pytest.raises(ValueError):worker.enqueue("maps","start")
    with pytest.raises(ValueError):worker.command("kiwix","pull")
    with pytest.raises(RuntimeError):worker.registry_report("kiwix")
    override.write_text(json.dumps({"services":{"kiwix":{"image":tag,"pull_policy":"always"}}}))
    with pytest.raises(ValueError):worker.command("kiwix","ps")

def test_native_policy_summary_allowlisted_and_redacted(monkeypatch):
    import json
    from types import SimpleNamespace
    calls=[]
    monkeypatch.setattr(worker,"RECOVERY_CORE_ONLY",False)
    monkeypatch.setattr(worker,"kopia_status",lambda:{"connection":"connected"})
    monkeypatch.setattr(worker,"command",lambda ident,*args:[ident,*args])
    monkeypatch.setattr(worker,"compose_env",lambda ident:{})
    def run(args,**kwargs):
        calls.append(args)
        return SimpleNamespace(stdout=json.dumps({
            "scheduling":{"intervalSeconds":3600,"timeOfDay":[{"hour":2,"min":30}],"cron":["0 3 * * * # private"],"runMissed":True},
            "retention":{"keepLatest":10,"keepDaily":7,"ignoreIdenticalSnapshots":False},
            "actions":{"beforeSnapshotRoot":{"command":"secret-command"}}
        }))
    monkeypatch.setattr(worker.subprocess,"run",run)
    result=worker.native_policy_summary("content/kiwix")
    assert calls[0][-4:]==["policy","show","--json","/source/content/kiwix"]
    assert result["policy"]["schedule"]["times_utc"]==["02:30"]
    assert result["policy"]["schedule"]["automatic_policy"] is True
    assert result["policy"]["retention"]["keepDaily"]==7
    assert result["managed_scheduling_enabled"] is False
    assert "secret-command" not in json.dumps(result) and "private" not in json.dumps(result)
    worker.native_policy_summary("global")
    assert calls[-1][-1]=="--global"
    for key in ("application/tak","/repository","../../etc","content/unknown"):
        with pytest.raises(ValueError):worker.native_policy_summary(key)
    assert len(calls)==2


@pytest.mark.parametrize("value",[{"scheduling":{"manual":"true"}},{"scheduling":{"intervalSeconds":-1}},
    {"scheduling":{"timeOfDay":[{"hour":24,"min":0}]}},{"retention":{"keepDaily":True}}])
def test_native_policy_rejects_malformed_values(value):
    with pytest.raises(ValueError):worker.summarize_native_policy(value)

def test_exact_verification_uses_requested_successful_source(tmp_path,monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(worker,"MODULES",Path(__file__).resolve().parents[1]/"modules")
    monkeypatch.setattr(worker,"STATE",tmp_path)
    worker.init()
    old=worker.enqueue("kopia","core-snapshot")
    worker.change(old,state="succeeded")
    worker.log(old,"Core database export snapshot: "+"a"*32+";")
    new=worker.enqueue("kopia","core-snapshot")
    worker.change(new,state="succeeded")
    worker.log(new,"Core database export snapshot: "+"b"*32+";")
    assert worker.managed_snapshot_record("core")== (new,"b"*32)
    assert worker.managed_snapshot_record("core",old)== (old,"a"*32)
    with pytest.raises(ValueError):worker.enqueue("kopia","worker-verify-snapshot",source_job=old)
    with pytest.raises(ValueError):worker.enqueue("kopia","core-verify-snapshot",source_job=999999)
    with pytest.raises(ValueError):worker.enqueue("kopia","stop",source_job=old)
    job=worker.enqueue("kopia","core-verify-snapshot",source_job=old)
    observed=[]
    monkeypatch.setattr(worker,"verify_snapshot",lambda *args:observed.append(args))
    worker.execute(worker.jobs()[0])
    assert observed==[(job,"core",old)]

def test_native_protected_capture_preserves_manifest_identity(monkeypatch):
    import json
    from types import SimpleNamespace
    monkeypatch.setattr(worker,"compose_env",lambda ident:{})
    monkeypatch.setattr(worker,"command",lambda ident,*args:list(args))
    source="/source/data/grocy"
    manifest={"id":"a"*32,"source":{"path":source},"rootEntry":{"obj":"k"+"b"*32},
              "stats":{"errorCount":0,"ignoredErrorCount":0,"excludedFileCount":0,"excludedDirCount":0,
                       "fileCount":1,"totalSize":100},"pins":[worker.RECOVERY_PIN]}
    calls=[]
    def run(argv,**kwargs):
        calls.append(argv)
        if "create" in argv:
            assert argv[argv.index("--pin")+1]==worker.RECOVERY_PIN
            return SimpleNamespace(stdout=json.dumps(manifest))
        if "list" in argv:return SimpleNamespace(stdout=json.dumps([manifest]))
        return SimpleNamespace(stdout="")
    monkeypatch.setattr(worker.subprocess,"run",run)
    assert worker.native_snapshot_source(source,protect=True)=="a"*32
    assert not any("pin" in argv for argv in calls)
    manifest["pins"]=[]
    with pytest.raises(RuntimeError,match="protected snapshot not confirmed"):worker.native_snapshot_source(source,protect=True)
    with pytest.raises(ValueError):worker.native_snapshot_source("/repository",protect=True)

def test_protected_capture_job_is_fixed_scope(tmp_path,monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(worker,"STATE",tmp_path)
    monkeypatch.setattr(worker,"MODULES",Path(__file__).resolve().parents[1]/"modules")
    worker.init()
    for module,action in (("tak","snapshot"),("kopia","core-verify-snapshot"),("grocy","stop")):
        with pytest.raises(ValueError):worker.enqueue(module,action,protect=True)
    job=worker.enqueue("kopia","core-snapshot",protect=True)
    seen=[]
    monkeypatch.setattr(worker,"core_snapshot",lambda j,protect=False:seen.append((j,protect)))
    worker.execute(worker.jobs()[0])
    assert seen==[(job,True)]

def test_retention_requires_verified_native_pin_and_exact_readback(tmp_path,monkeypatch):
    from pathlib import Path
    import copy
    monkeypatch.setattr(worker,"STATE",tmp_path)
    monkeypatch.setattr(worker,"MODULES",Path(__file__).resolve().parents[1]/"modules")
    monkeypatch.setattr(worker,"RECOVERY_CORE_ONLY",False)
    monkeypatch.setattr(worker,"RECOVERY_OFFLINE",False)
    worker.init()
    old={k:10 for k in worker.RETENTION_FLAGS}
    counts={**old,"keepLatest":5}
    value={"key":"core","expected":old,"counts":counts}
    policy={"retention":old,"schedule":{"automatic_policy":False},"ignore_identical":False}
    monkeypatch.setattr(worker,"native_policy_summary",lambda key:{"policy":copy.deepcopy(policy)})
    calls=[]
    monkeypatch.setattr(worker,"command",lambda ident,*args:list(args))
    monkeypatch.setattr(worker,"compose_env",lambda ident:{})
    def run(argv,**kwargs):
        calls.append(argv)
        policy["retention"]=counts
    monkeypatch.setattr(worker.subprocess,"run",run)
    with pytest.raises(ValueError):worker.enqueue_retention({**value,"key":"global"})
    with pytest.raises(ValueError):worker.enqueue_retention({**value,"counts":{**counts,"keepLatest":2}})
    j=worker.enqueue_retention(value)
    worker.execute(worker.jobs()[0])
    assert worker.jobs()[0]["state"]=="failed" and not calls
    snapshot=worker.enqueue("kopia","core-snapshot",protect=True)
    worker.log(snapshot,"Core database export snapshot: "+"a"*32+";")
    worker.change(snapshot,state="succeeded")
    verify=worker.enqueue("kopia","core-verify-snapshot")
    worker.log(verify,"Snapshot "+"a"*32+" restored; fixture")
    worker.change(verify,state="succeeded")
    monkeypatch.setattr(worker,"read_snapshot_manifest",lambda source,sid:("root",{"aftergrid_pinned":False}))
    worker.enqueue_retention(value)
    worker.execute(worker.jobs()[0])
    assert worker.jobs()[0]["state"]=="failed" and not calls
    monkeypatch.setattr(worker,"read_snapshot_manifest",lambda source,sid:("root",{"aftergrid_pinned":True}))
    worker.enqueue_retention(value)
    worker.execute(worker.jobs()[0])
    assert worker.jobs()[0]["state"]=="succeeded"
    assert len(calls)==1 and "--keep-latest=5" in calls[0] and calls[0][-1]=="/source/data/core/recovery-export"
    worker.enqueue_retention(value)
    worker.execute(worker.jobs()[0])
    assert worker.jobs()[0]["state"]=="failed" and len(calls)==1

def test_backup_health_distinguishes_history_and_matching_inventory(tmp_path,monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(worker,"STATE",tmp_path)
    monkeypatch.setattr(worker,"MODULES",Path(__file__).resolve().parents[1]/"modules")
    worker.init()
    old=worker.enqueue("kopia","core-snapshot",protect=True)
    worker.log(old,"Core database export snapshot: "+"a"*32+"; private fixture")
    worker.change(old,state="succeeded")
    v=worker.enqueue("kopia","core-verify-snapshot")
    worker.log(v,"Snapshot "+"a"*32+" restored; fixture")
    worker.change(v,state="succeeded")
    newest=worker.enqueue("kopia","core-snapshot")
    worker.log(newest,"Core database export snapshot: "+"b"*32+";")
    worker.change(newest,state="succeeded")
    failed=worker.enqueue("kopia","core-verify-snapshot")
    worker.change(failed,state="failed")
    monkeypatch.setattr(worker,"kopia_status",lambda:{"connection":"connected","storage_type":"filesystem"})
    monkeypatch.setattr(worker,"load_recovery_manifest",lambda:{"manifest_job":99,"created":123,"records":[
        {"key":"core","snapshot_id":"a"*32,"snapshot_job":old,"repository_status":"present","aftergrid_pinned":True}]})
    report=worker.backup_health()
    record=next(r for r in report["sources"] if r["key"]=="core")
    assert record["snapshot_job"]==newest and record["verified"] is None
    assert record["latest_verification_attempt"]["id"]==failed
    assert record["repository_at_inventory"]=="not checked"
    assert record["latest_protected_capture"]["verification"]["id"]==v
    assert record["latest_protected_capture"]["pin_at_inventory"] is True
    assert not report["live_manifest_verification"]
    assert "private fixture" not in str(report)
    assert not next(r for r in report["sources"] if r["key"]=="application/tak")["supported"]

def test_approved_update_eligibility_requires_exact_reviewed_transition(tmp_path,monkeypatch):
    import json
    from types import SimpleNamespace
    from pathlib import Path
    monkeypatch.setattr(worker,"STATE",tmp_path)
    monkeypatch.setattr(worker,"MODULES",Path(__file__).resolve().parents[1]/"modules")
    monkeypatch.setattr(worker,"RECOVERY_CORE_ONLY",False)
    monkeypatch.setattr(worker,"RECOVERY_OFFLINE",False)
    worker.init()
    assert worker.update_eligibility("kiwix",True)["status"]=="no approved update"
    assert not worker.update_eligibility("grocy",True)["pilot_supported"]
    old="sha256:"+"a"*64
    new="sha256:"+"b"*64
    target="ghcr.io/kiwix/kiwix-serve:3.8.2@sha256:"+"c"*64
    candidate={"image":target,"platforms":{"linux/amd64":{"from":[old],"to":new}}}
    monkeypatch.setattr(worker,"approved_update_candidate",lambda ident:candidate)
    service={"service":"kiwix","configured_image":target,"installed_image_ids":[old],"local_target_image_id":None}
    monkeypatch.setattr(worker,"version_report",lambda ident:{"services":[service]})
    monkeypatch.setattr(worker,"state",lambda ident:"running")
    monkeypatch.setattr(worker,"kopia_status",lambda:{"connection":"connected"})
    monkeypatch.setattr(worker.subprocess,"run",lambda *a,**kw:SimpleNamespace(stdout="linux/amd64"))
    registry={"configured_image":target,"platform":"linux/amd64","installed_image_ids":[old],
              "registry_config_digest":new,"platform_manifest_digest":"sha256:"+"d"*64}
    calls=[]
    def report(ident):
        calls.append(ident)
        return registry
    monkeypatch.setattr(worker,"registry_report",report)
    assert worker.update_eligibility("kiwix")["status"]=="registry check required"
    assert not calls
    result=worker.update_eligibility("kiwix",True)
    assert result["status"]=="reviewed candidate confirmed" and not result["automatic_execution_enabled"]
    registry["registry_config_digest"]=old
    assert worker.update_eligibility("kiwix",True)["status"]=="blocked"
    service["installed_image_ids"]=["sha256:"+"f"*64]
    assert worker.update_eligibility("kiwix",True)["status"]=="blocked"
    assert len(calls)==2
    service["installed_image_ids"]=[new]
    assert worker.update_eligibility("kiwix",True)["status"]=="matches approved target"
    monkeypatch.setattr(worker,"RECOVERY_OFFLINE",True)
    assert worker.update_eligibility("kiwix",True)["status"]=="blocked"


def test_candidate_validation_is_narrow_and_fail_closed(tmp_path,monkeypatch):
    import json
    monkeypatch.setattr(worker,"MODULES",tmp_path)
    folder=tmp_path/"kiwix"
    folder.mkdir()
    path=folder/"update-candidate.json"
    assert worker.approved_update_candidate("kiwix") is None
    candidate={"image":"ghcr.io/kiwix/kiwix-serve:3.8.2@sha256:"+"a"*64,
               "platforms":{"linux/amd64":{"from":["sha256:"+"b"*64],"to":"sha256:"+"c"*64}}}
    path.write_text(json.dumps({"format":1,"candidate":candidate}))
    assert worker.approved_update_candidate("kiwix")==candidate
    candidate["image"]="ghcr.io/kiwix/kiwix-serve:latest"
    path.write_text(json.dumps({"format":1,"candidate":candidate}))
    with pytest.raises(ValueError):worker.approved_update_candidate("kiwix")

def test_preupdate_preparation_reuses_exact_native_read_and_guard(tmp_path,monkeypatch):
    from pathlib import Path
    import json
    monkeypatch.setattr(worker,"STATE",tmp_path)
    monkeypatch.setattr(worker,"MODULES",Path(__file__).resolve().parents[1]/"modules")
    monkeypatch.setattr(worker,"RECOVERY_CORE_ONLY",False)
    monkeypatch.setattr(worker,"RECOVERY_OFFLINE",False)
    worker.init()
    old="sha256:"+"a"*64
    new="sha256:"+"b"*64
    target="ghcr.io/kiwix/kiwix-serve:3.8.2@sha256:"+"c"*64
    request={"candidate":target,"platform":"linux/amd64","previous_image_id":old,"target_image_id":new}
    with pytest.raises(ValueError):worker.enqueue_update_preparation(request)
    monkeypatch.setattr(worker,"approved_update_candidate",lambda ident:{"image":target,"platforms":{"linux/amd64":{"from":[old],"to":new}}})
    seen=[]
    monkeypatch.setattr(worker,"check_preparation_identity",lambda job,expected,online:seen.append(("identity",online)))
    monkeypatch.setattr(worker,"native_policy_summary",lambda key:{"policy":{"schedule":{"automatic_policy":False},"ignore_identical":False}})
    monkeypatch.setattr(worker,"content_guard",lambda action,job:seen.append((action,job)))
    def snap(source,seconds,protect):
        assert source==worker.CONTENT_SOURCES["kiwix"] and protect is True
        seen.append(("snapshot",source))
        return "a"*32
    monkeypatch.setattr(worker,"native_snapshot_source",snap)
    monkeypatch.setattr(worker,"read_snapshot_manifest",lambda source,sid:("root",{"aftergrid_pinned":True,"fileCount":3}))
    monkeypatch.setattr(worker,"verify_content_manifest",lambda job,sid,stats:seen.append(("verify",sid)) or 3)
    monkeypatch.setattr(worker,"preserve_previous_image",lambda image:seen.append(("archive",image)) or {"image_id":image,"sha256":"e"*64,"bytes":100,"format":1})
    job=worker.enqueue_update_preparation(request)
    worker.execute(worker.jobs()[0])
    assert worker.jobs()[0]["state"]=="succeeded"
    assert seen==[("identity",True),("begin",job),("identity",False),("snapshot",worker.CONTENT_SOURCES["kiwix"]),("verify","a"*32),("identity",False),("archive",old),("identity",False),("end",job)]
    evidence=worker.latest_update_preparation()["evidence"]
    assert evidence["snapshot_id"]=="a"*32 and evidence["pin_confirmed"] and not evidence["reusable_authorization"] and not evidence["update_performed"]
    assert evidence["previous_image_archive"]["image_id"]==old
    def fail(*args):raise RuntimeError("verification failure")
    monkeypatch.setattr(worker,"verify_content_manifest",fail)
    job=worker.enqueue_update_preparation(request)
    worker.execute(worker.jobs()[0])
    assert worker.jobs()[0]["state"]=="failed" and seen[-1]==("end",job)
    assert worker.latest_update_preparation()["evidence"] is None


def test_previous_image_archive_validation_and_reuse(tmp_path,monkeypatch):
    import hashlib,io,json,tarfile
    from types import SimpleNamespace
    monkeypatch.setattr(worker,"STATE",tmp_path)
    config=b'{"fixture":true}'
    digest=hashlib.sha256(config).hexdigest()
    image="sha256:"+digest
    buffer=io.BytesIO()
    with tarfile.open(fileobj=buffer,mode="w") as tar:
        for name,data in (("manifest.json",json.dumps([{"Config":digest+".json","Layers":[]}]).encode()),(digest+".json",config)):
            member=tarfile.TarInfo(name)
            member.size=len(data)
            tar.addfile(member,io.BytesIO(data))
    payload=buffer.getvalue()
    calls=[]
    def run(argv,**kwargs):
        calls.append(argv)
        assert argv==["docker","image","inspect","--format","{{json .Size}}",image]
        return SimpleNamespace(stdout="1024")
    class Proc:
        def __init__(self,argv,**kwargs):
            calls.append(argv)
            assert argv==["docker","image","save",image]
            self.stdout=io.BytesIO(payload)
        def __enter__(self):return self
        def __exit__(self,*args):self.stdout.close()
        def wait(self):return 0
        def poll(self):return 0
        def kill(self):pass
    monkeypatch.setattr(worker.subprocess,"run",run)
    monkeypatch.setattr(worker.subprocess,"Popen",Proc)
    monkeypatch.setattr(worker.shutil,"disk_usage",lambda path:SimpleNamespace(free=2*1024**3))
    result=worker.preserve_previous_image(image)
    assert result["sha256"]==hashlib.sha256(payload).hexdigest() and len(calls)==2
    folder=tmp_path/"previous-images"/("kiwix-"+digest)
    assert worker.preserve_previous_image(image)==result and len(calls)==2
    assert (folder/"image.tar").stat().st_mode&0o777==0o600
    with (folder/"image.tar").open("ab") as out:out.write(b"corruption")
    with pytest.raises(RuntimeError,match="Existing previous image archive invalid"):worker.preserve_previous_image(image)
    assert len(calls)==2
    with pytest.raises(ValueError):worker.preserve_previous_image("latest")


def test_guarded_compose_update_records_boundary_and_checks_target(tmp_path,monkeypatch):
    from pathlib import Path
    import json
    monkeypatch.setattr(worker,"STATE",tmp_path)
    monkeypatch.setattr(worker,"MODULES",Path(__file__).resolve().parents[1]/"modules")
    monkeypatch.setattr(worker,"RECOVERY_CORE_ONLY",False)
    monkeypatch.setattr(worker,"RECOVERY_OFFLINE",False)
    worker.init()
    old="sha256:"+"a"*64
    new="sha256:"+"b"*64
    target="ghcr.io/kiwix/kiwix-serve:3.8.2@sha256:"+"c"*64
    request={"candidate":target,"platform":"linux/amd64","previous_image_id":old,"target_image_id":new}
    monkeypatch.setattr(worker,"approved_update_candidate",lambda ident:{"image":target,"platforms":{"linux/amd64":{"from":[old],"to":new}}})
    job=worker.enqueue_update_preparation(request,guarded=True)
    seen=[]
    monkeypatch.setattr(worker,"kiwix_catalog_sample",lambda:["fixture"])
    monkeypatch.setattr(worker,"check_preparation_identity",lambda j,e,online:{"local_target_image_id":new})
    monkeypatch.setattr(worker,"wait_ready",lambda ident:seen.append("ready"))
    monkeypatch.setattr(worker,"version_report",lambda ident:{"services":[{"service":"kiwix","configured_image":target,"installed_image_ids":[new]}]})
    def run(j,ident,*args):
        seen.append(args[0])
        if args[0]=="up":
            assert worker.latest_update_preparation()["evidence"]["recreation_attempted"] is True
            assert "--pull" in args and "never" in args and "--no-build" in args
    monkeypatch.setattr(worker,"run",run)
    evidence={"snapshot_id":"d"*32,"update_performed":False}
    worker.guarded_compose_update(job,request,evidence)
    assert seen==["config","pull","up","ready"]
    assert evidence["update_performed"] and evidence["catalog_sample_matched"] and evidence["result_image_id"]==new
    seen.clear()
    monkeypatch.setattr(worker,"check_preparation_identity",lambda j,e,online:{"local_target_image_id":old})
    with pytest.raises(RuntimeError,match="Pulled image ID"):worker.guarded_compose_update(job,request,{})
    assert seen==["config","pull"]
    worker.change(job,state="failed")
    with pytest.raises(ValueError,match="Unresolved update"):worker.enqueue_update_preparation(request,guarded=True)


def test_reader_rollback_override_persists_and_blocks_pull(tmp_path,monkeypatch):
    import json
    from pathlib import Path
    monkeypatch.setattr(worker,"STATE",tmp_path)
    monkeypatch.setattr(worker,"MODULES",Path(__file__).resolve().parents[1]/"modules")
    monkeypatch.setattr(worker,"RECOVERY_OFFLINE",False)
    image="sha256:"+"a"*64
    seen=[]
    monkeypatch.setattr(worker,"exact_local_image",lambda ref,i:seen.append((ref,i)))
    hold=worker.publish_reader_rollback(image)
    assert hold[1]==image and hold[0].stat().st_mode&0o777==0o600
    assert worker.publish_reader_rollback(image)==hold
    with pytest.raises(RuntimeError):worker.publish_reader_rollback("sha256:"+"b"*64)
    args=worker.command("kiwix","up","-d","--pull","never")
    assert str(hold[0]) in args and "--no-build" in args and seen==[(hold[2],image)]
    with pytest.raises(ValueError):worker.command("kiwix","pull")
    with pytest.raises(ValueError):worker.command("kiwix","restart")
    with pytest.raises(ValueError):worker.kiwix_lifecycle_admission("kiwix","update")
    assert worker.update_eligibility("kiwix")["status"]=="blocked"
    assert str(hold[0]) not in worker.command("grocy","config","-q")
    hold[0].write_text(json.dumps({"services":{"kiwix":{"image":hold[2],"pull_policy":"always"}}}))
    with pytest.raises(ValueError):worker.command("kiwix","config","-q")


def test_reader_rollback_checks_archive_pin_and_catalog(tmp_path,monkeypatch):
    import hashlib,json
    from types import SimpleNamespace
    monkeypatch.setattr(worker,"STATE",tmp_path)
    monkeypatch.setattr(worker,"RECOVERY_OFFLINE",False)
    monkeypatch.setattr(worker,"RECOVERY_CORE_ONLY",False)
    image="sha256:"+"a"*64
    expected={"previous_image_id":image}
    sample=["fixture"]
    evidence={"recreation_attempted":True,"compose_sha256":"fingerprint","previous_image_archive":{"image_id":image},
              "snapshot_id":"b"*32,"catalog_sample_sha256":hashlib.sha256(json.dumps(sample).encode()).hexdigest()}
    monkeypatch.setattr(worker,"reader_compose_fingerprint",lambda:"fingerprint")
    monkeypatch.setattr(worker,"verify_previous_archive",lambda folder,i:{"image_id":i})
    monkeypatch.setattr(worker,"read_snapshot_manifest",lambda source,sid:("root",{"aftergrid_pinned":True}))
    calls=[]
    monkeypatch.setattr(worker,"exact_local_image",lambda ref,i:None)
    tag=worker.rollback_tag(image)
    monkeypatch.setattr(worker.subprocess,"run",lambda argv,**kw:SimpleNamespace(stdout=json.dumps(image)))
    monkeypatch.setattr(worker,"publish_reader_rollback",lambda i:calls.append("hold"))
    monkeypatch.setattr(worker,"change",lambda *a,**kw:None)
    monkeypatch.setattr(worker,"run",lambda j,i,*a:calls.append(a[0]))
    monkeypatch.setattr(worker,"wait_ready",lambda i:calls.append("ready"))
    monkeypatch.setattr(worker,"version_report",lambda i:{"services":[{"service":"kiwix","configured_image":tag,"installed_image_ids":[image]}]})
    monkeypatch.setattr(worker,"kiwix_catalog_sample",lambda:sample)
    worker.rollback_reader(1,expected,evidence)
    assert calls==["hold","config","up","ready"] and evidence["rollback_status"]=="restored"
    calls.clear()
    monkeypatch.setattr(worker,"read_snapshot_manifest",lambda source,sid:("root",{"aftergrid_pinned":False}))
    with pytest.raises(RuntimeError,match="Protected recovery snapshot"):worker.rollback_reader(1,expected,evidence)
    assert not calls

def test_reader_update_health_keeps_failed_update_separate_from_preparation(tmp_path,monkeypatch):
    import json
    from pathlib import Path
    monkeypatch.setattr(worker,"STATE",tmp_path)
    monkeypatch.setattr(worker,"MODULES",Path(__file__).resolve().parents[1]/"modules")
    monkeypatch.setattr(worker,"RECOVERY_OFFLINE",False)
    monkeypatch.setattr(worker,"RECOVERY_CORE_ONLY",False)
    worker.init()
    monkeypatch.setattr(worker,"state",lambda i:"running")
    monkeypatch.setattr(worker,"version_report",lambda i:{"services":[]})
    image="sha256:"+"a"*64
    worker.publish_reader_rollback(image)
    with worker.db() as conn:
        for action,state,evidence in (("guarded-update","failed",{"rollback_status":"restored","snapshot_id":"b"*32,"secret":"not exposed"}),
                ("prepare-update","succeeded",{"snapshot_id":"c"*32})):
            row=conn.execute("INSERT INTO jobs(module,action,state,stage,created) VALUES ('kiwix',?,?,?,1)",(action,state,"Fixture"))
            conn.execute("INSERT INTO update_preparations(job,request,evidence) VALUES (?,'{}',?)",(row.lastrowid,json.dumps(evidence)))
    report=worker.reader_update_health()
    assert report["latest_guarded_update"]["state"]=="failed"
    assert report["latest_preparation"]["state"]=="succeeded"
    assert report["rollback_hold"]=={"status":"active","image_id":image}
    assert "Unresolved guarded update; no automatic retry" in report["blockers"]
    assert "not exposed" not in str(report)
    assert not report["registry_checked"] and not report["archive_reverified"] and not report["automatic_execution_enabled"]


def test_reader_update_health_reports_missing_image_evidence(tmp_path,monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(worker,"STATE",tmp_path)
    monkeypatch.setattr(worker,"MODULES",Path(__file__).resolve().parents[1]/"modules")
    monkeypatch.setattr(worker,"RECOVERY_OFFLINE",False)
    monkeypatch.setattr(worker,"RECOVERY_CORE_ONLY",False)
    worker.init()
    monkeypatch.setattr(worker,"state",lambda i:"running")
    def unavailable(i):
        raise RuntimeError("Docker unavailable")
    monkeypatch.setattr(worker,"version_report",unavailable)
    report=worker.reader_update_health()
    assert report["reader_state"]=="running" and report["local_images"] is None
    assert "Local reader image identity unavailable" in report["blockers"]
    monkeypatch.setattr(worker,"version_report",lambda i:{"services":[{"service":"kiwix","installed_image_ids":[]}]})
    report=worker.reader_update_health()
    assert "Running reader image identity not confirmed" in report["blockers"]
