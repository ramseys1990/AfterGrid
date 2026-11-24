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
    assert worker.SNAPSHOT_SOURCES=={"grocy":"/source/data/grocy","homebox":"/source/data/homebox","notes":"/source/data/notes"}
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
